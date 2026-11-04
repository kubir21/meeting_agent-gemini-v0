"""Shared pipeline: Gemini analysis -> PDF -> email -> cleanup (always)."""
from __future__ import annotations

import logging
from pathlib import Path

import config
from emailer import send_report
from gemini_client import analyze_video, delete_remote_file
from pdf_report import build_pdf

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


def run_pipeline(video_path: Path, source_name: str, send_email: bool = True, keep_pdf: bool = False) -> dict:
    """Run the full pipeline on a *temporary copy* of a video inside temp/.

    The temp video, the PDF (unless keep_pdf) and the Gemini remote file are
    always cleaned up, even if a step fails.
    """
    gemini_ref: dict = {"name": None}
    pdf_path: Path | None = None
    try:
        analysis = analyze_video(Path(video_path), gemini_ref)
        pdf_path = build_pdf(analysis, source_name)
        if send_email:
            send_report(pdf_path, source_name)
        return {
            "analysis": analysis,
            "pdf_path": str(pdf_path) if keep_pdf else None,
            "emailed": send_email,
            "recipient": config.RECIPIENT_EMAIL if send_email else None,
        }
    finally:
        safe_delete_temp(Path(video_path))
        if pdf_path and not keep_pdf:
            safe_delete_temp(pdf_path)
        delete_remote_file(gemini_ref["name"])
