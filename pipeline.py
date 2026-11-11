"""Shared pipeline: Gemini analysis -> PDF -> cleanup (always).

Emailing is a separate, user-triggered step (see /send-report in app.py).
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime
from pathlib import Path

import config
from gemini_client import analyze_video, delete_remote_file
from pdf_report import build_pdf, clean_company

log = logging.getLogger(__name__)


def safe_delete_temp(path: Path | None) -> None:
    """Delete `path` ONLY if it lives directly inside temp/. Never touches anything else."""
    if not path:
        return
    try:
        resolved = Path(path).resolve()
        if resolved.parent != config.TEMP_DIR.resolve():
            log.warning("Refusing to delete non-temp path: %s", resolved)
            return
        resolved.unlink(missing_ok=True)
        log.info("Deleted temp file %s", resolved.name)
    except Exception as exc:  # cleanup must never raise
        log.warning("Could not delete %s: %s", path, exc)


def make_report_id(now: datetime) -> str:
    return f"VAR-{now:%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"


def run_pipeline(video_path: Path, source_name: str, keep_pdf: bool = False) -> dict:
    """Run analysis + PDF on a *temporary copy* of a video inside temp/.

    The temp video, the PDF (unless keep_pdf) and the Gemini remote file are
    always cleaned up, even if a step fails.
    """
    gemini_ref: dict = {"name": None}
    pdf_path: Path | None = None
    try:
        analysis = analyze_video(Path(video_path), gemini_ref)
        generated_at = datetime.now().astimezone()
        report_id = make_report_id(generated_at)
        pdf_path = build_pdf(analysis, source_name, report_id, generated_at)
        pdf_bytes = pdf_path.read_bytes()
        return {
            "analysis": analysis,
            "report_id": report_id,
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "company": clean_company(analysis.get("company_name", "")),
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "pdf_path": str(pdf_path) if keep_pdf else None,
        }
    finally:
        safe_delete_temp(Path(video_path))
        if pdf_path and not keep_pdf:
            safe_delete_temp(pdf_path)
        delete_remote_file(gemini_ref["name"])
