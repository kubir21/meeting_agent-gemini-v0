"""FastAPI backend: serves the UI, /generate-report and /send-report.

Run:  python app.py      (then open http://localhost:8000)
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
import time
import uuid
from collections import deque
from pathlib import Path

from typing import Any

import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

import config
from emailer import EmailError, is_valid_email, send_report
from gemini_client import ConfigError, GeminiProcessingError
from pipeline import run_pipeline, run_pipeline_s3, safe_delete_temp
import s3_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = FastAPI(title="Video Analysis Report Generator")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.middleware("http")
async def fix_vercel_path(request: Request, call_next):
    # Normalize paths rewritten by Vercel serverless functions
    path = request.scope.get("path", "")
    for prefix in ("/api/index.py", "/api/index", "/api"):
        if path.startswith(prefix):
            sub = path[len(prefix):]
            new_path = sub if sub.startswith("/") else ("/" + sub if sub else "/")
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("ascii")
            break
    return await call_next(request)


@app.middleware("http")
async def no_cache_ui(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response

CHUNK = 1024 * 1024


def error(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"status": "error", "detail": detail})


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": config.GEMINI_MODEL, "s3_enabled": config.S3_ENABLED}


@app.get("/app-config")
def app_config() -> dict:
    return {
        "s3_enabled": config.S3_ENABLED,
        "max_upload_mb": config.MAX_UPLOAD_MB,
        "allowed_extensions": sorted(list(config.VIDEO_EXTENSIONS)),
    }


# --- S3 Direct Upload Endpoints ----------------------------------------------
class S3InitiateRequest(BaseModel):
    filename: str
    content_type: str = "video/mp4"


class S3SignPartRequest(BaseModel):
    key: str
    upload_id: str
    part_number: int


class S3CompletePartItem(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    PartNumber: int = Field(default=0, alias="part_number")
    ETag: str = Field(default="", alias="etag")

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            pn = data.get("PartNumber") or data.get("part_number") or data.get("partNumber") or 0
            et = data.get("ETag") or data.get("etag") or ""
            return {"PartNumber": int(pn), "ETag": str(et)}
        return data


class S3CompleteRequest(BaseModel):
    key: str
    upload_id: str
    parts: list[S3CompletePartItem]


class S3AbortRequest(BaseModel):
    key: str
    upload_id: str


class S3AnalyzeRequest(BaseModel):
    key: str
    original_filename: str


@app.post("/s3/initiate-upload")
def s3_initiate_upload(req: S3InitiateRequest):
    if not config.S3_ENABLED:
        return error(503, "AWS S3 storage is not configured on the server.")
    ext = Path(req.filename).suffix.lower()
    if ext not in config.VIDEO_EXTENSIONS:
        return error(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(config.VIDEO_EXTENSIONS))}")
    try:
        data = s3_client.initiate_multipart_upload(req.filename, req.content_type)
        return {"status": "success", **data}
    except Exception as exc:
        log.exception("Error initiating S3 upload")
        return error(500, str(exc))


@app.post("/s3/sign-part")
def s3_sign_part(req: S3SignPartRequest):
    if not config.S3_ENABLED:
        return error(503, "AWS S3 storage is not configured on the server.")
    try:
        url = s3_client.sign_part_upload(req.key, req.upload_id, req.part_number)
        return {"status": "success", "url": url, "part_number": req.part_number}
    except Exception as exc:
        log.exception("Error signing S3 part")
        return error(500, str(exc))


@app.post("/s3/complete-upload")
def s3_complete_upload(req: S3CompleteRequest):
    if not config.S3_ENABLED:
        return error(503, "AWS S3 storage is not configured on the server.")
    try:
        log.info("Completing S3 upload for key %s with %d parts", req.key, len(req.parts))
        parts_dicts = [p.model_dump() for p in req.parts]
        res = s3_client.complete_multipart_upload(req.key, req.upload_id, parts_dicts)
        return {"status": "success", "key": res.get("key"), "location": res.get("location")}
    except Exception as exc:
        log.exception("Error completing S3 upload for key %s: %s", req.key, exc)
        return error(500, str(exc))


@app.post("/s3/abort-upload")
def s3_abort_upload(req: S3AbortRequest):
    if not config.S3_ENABLED:
        return error(503, "AWS S3 storage is not configured on the server.")
    s3_client.abort_multipart_upload(req.key, req.upload_id)
    return {"status": "success", "message": "Upload aborted."}


@app.post("/analyze-s3-video")
async def analyze_s3_video(req: S3AnalyzeRequest):
    if not config.S3_ENABLED:
        return error(503, "AWS S3 storage is not configured on the server.")
    original_name = Path(req.original_filename or "video.mp4").name
    ext = Path(original_name).suffix.lower()
    if ext not in config.VIDEO_EXTENSIONS:
        return error(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(config.VIDEO_EXTENSIONS))}")

    try:
        result = await run_in_threadpool(run_pipeline_s3, req.key, original_name, False)
        analysis = result["analysis"]
        return {
            "status": "success",
            "report_id": result["report_id"],
            "generated_at": result["generated_at"],
            "company": result["company"],
            "category": result.get("category") or analysis.get("company_category", "Not mentioned"),
            "source_file": original_name,
            "meta": {
                "duration": analysis.get("video_duration", ""),
                "language": analysis.get("language", ""),
            },
            "summary": analysis.get("summary", ""),
            "timeline": analysis.get("timeline", []),
            "qa": analysis["qa"],
            "transcript": analysis.get("transcript", ""),
            "pdf_base64": result["pdf_base64"],
        }
    except ValueError as exc:
        return error(400, str(exc))
    except ConfigError as exc:
        return error(500, str(exc))
    except TimeoutError as exc:
        return error(504, str(exc))
    except GeminiProcessingError as exc:
        return error(502, str(exc))
    except Exception as exc:
        log.exception("Unexpected error analyzing S3 video")
        return error(500, f"Unexpected error: {exc}")


@app.post("/generate-report")
async def generate_report(file: UploadFile = File(...)):
    original_name = Path(file.filename or "video.mp4").name
    ext = Path(original_name).suffix.lower()
    if ext not in config.VIDEO_EXTENSIONS:
        return error(400, f"Unsupported file type '{ext or 'unknown'}'. Allowed: "
                          f"{', '.join(sorted(config.VIDEO_EXTENSIONS))}")

    temp_path = config.TEMP_DIR / f"{uuid.uuid4().hex}{ext}"
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    try:
        # Stream the upload to temp/ in chunks (unique name per request).
        size = 0
        with temp_path.open("wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"File exceeds the {config.MAX_UPLOAD_MB} MB limit.")
                out.write(chunk)
        if size == 0:
            raise ValueError("The uploaded file is empty.")
        log.info("Received %s (%.1f MB) -> %s", original_name, size / 1e6, temp_path.name)

        result = await run_in_threadpool(run_pipeline, temp_path, original_name, False)
        analysis = result["analysis"]
        return {
            "status": "success",
            "report_id": result["report_id"],
            "generated_at": result["generated_at"],
            "company": result["company"],
            "category": result.get("category") or analysis.get("company_category", "Not mentioned"),
            "source_file": original_name,
            "meta": {
                "duration": analysis.get("video_duration", ""),
                "language": analysis.get("language", ""),
            },
            "summary": analysis.get("summary", ""),
            "timeline": analysis.get("timeline", []),
            "qa": analysis["qa"],
            "transcript": analysis.get("transcript", ""),
            "pdf_base64": result["pdf_base64"],
        }
    except ValueError as exc:
        return error(400, str(exc))
    except ConfigError as exc:
        return error(500, str(exc))
    except TimeoutError as exc:
        return error(504, str(exc))
    except GeminiProcessingError as exc:
        return error(502, str(exc))
    except Exception as exc:
        log.exception("Unexpected error")
        return error(500, f"Unexpected error: {exc}")
    finally:
        await file.close()
        safe_delete_temp(temp_path)  # no-op if the pipeline already removed it


class SendRequest(BaseModel):
    email: str
    report_id: str
    pdf_base64: str
    company: str = "Video Analysis Report"
    source_file: str = ""


_recent_sends: deque[float] = deque()


def _rate_limited() -> bool:
    now = time.monotonic()
    while _recent_sends and now - _recent_sends[0] > 60:
        _recent_sends.popleft()
    if len(_recent_sends) >= config.SEND_LIMIT_PER_MINUTE:
        return True
    _recent_sends.append(now)
    return False


@app.post("/send-report")
async def send_report_endpoint(req: SendRequest):
    recipient = req.email.strip()
    if not is_valid_email(recipient):
        return error(400, "Please enter a valid email address.")
    try:
        pdf = base64.b64decode(req.pdf_base64, validate=True)
    except (binascii.Error, ValueError):
        return error(400, "The report data is invalid. Please generate the report again.")
    if not pdf.startswith(b"%PDF-"):
        return error(400, "The report data is not a valid PDF. Please generate the report again.")
    if len(pdf) > config.MAX_ATTACHMENT_MB * 1024 * 1024:
        return error(400, f"The report is larger than {config.MAX_ATTACHMENT_MB} MB and cannot be emailed.")
    if _rate_limited():
        return error(429, "Too many emails sent. Please wait a minute and try again.")

    safe_id = re.sub(r"[^\w\-]+", "_", req.report_id)[:40] or "report"
    safe_company = re.sub(r"[^\w\-]+", "_", req.company).strip("_")[:40] or "Report"
    try:
        await run_in_threadpool(
            send_report, recipient, pdf, f"Report_{safe_company}_{safe_id}.pdf",
            req.company[:120], req.report_id[:60], req.source_file[:200],
        )
    except EmailError as exc:
        return error(502, str(exc))
    except Exception:
        log.exception("Unexpected error while sending email")
        return error(500, "Something went wrong while sending the email.")
    return {"status": "success", "recipient": recipient}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
