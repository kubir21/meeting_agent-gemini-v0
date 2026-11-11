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

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from emailer import EmailError, is_valid_email, send_report
from gemini_client import ConfigError, GeminiProcessingError
from pipeline import run_pipeline, safe_delete_temp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = FastAPI(title="Video Analysis Report Generator")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

CHUNK = 1024 * 1024


def error(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"status": "error", "detail": detail})


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": config.GEMINI_MODEL}


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
            "source_file": original_name,
            "meta": {
                "duration": analysis.get("video_duration", ""),
                "language": analysis.get("language", ""),
            },
            "summary": analysis.get("summary", ""),
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
