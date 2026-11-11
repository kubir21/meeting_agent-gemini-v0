"""Central configuration. All tunables and secrets are loaded here.

Secrets come from a `.env` file in the project root (see `.env.example`).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Paths -------------------------------------------------------------------
TEMP_DIR = BASE_DIR / "temp"          # all temporary copies / PDFs live here
STATIC_DIR = BASE_DIR / "static"      # frontend files
FONTS_DIR = BASE_DIR / "fonts"        # bundled Unicode fonts for the PDF
TEMP_DIR.mkdir(exist_ok=True)

# --- Secrets (from .env) -----------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()       # Gemini API key
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()                # Brevo API key
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()  # Gmail App Password

# --- Gemini ------------------------------------------------------------------
# Change the model here (or set GEMINI_MODEL in .env).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
FILE_PROCESSING_TIMEOUT_S = 300   # max wait for uploaded video to become ACTIVE
POLL_INTERVAL_S = 3

# --- Email -------------------------------------------------------------------
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "brevo").strip().lower()   # brevo | gmail
# Sender address (BREVO_SENDER_EMAIL is accepted as a legacy alias).
SENDER_EMAIL = (os.getenv("SENDER_EMAIL") or os.getenv("BREVO_SENDER_EMAIL") or "rk26.ftw@gmail.com").strip()
SENDER_NAME = (os.getenv("SENDER_NAME") or os.getenv("BREVO_SENDER_NAME") or "Video Insights").strip()
EMAIL_SUBJECT = "Your Video Analysis Report"
MAX_ATTACHMENT_MB = 5
SEND_LIMIT_PER_MINUTE = 10

# --- Uploads -----------------------------------------------------------------
MAX_UPLOAD_MB = 500
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
VIDEO_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
}

# --- The fixed questions -----------------------------------------------------
QUESTIONS = [
    "Employee Experience: What initiatives have been implemented to improve employee satisfaction, engagement, and overall workplace experience?",
    "Performance and Impact: What measurable improvements have resulted from the initiatives discussed?",
    "Growth and Development: How does the organisation support continuous learning, professional development, and employee growth?",
    "Feedback and Improvement: How is feedback collected, evaluated, and translated into meaningful improvements?",
    "Effectiveness and Sustainability: How does the organisation ensure that its initiatives deliver long-term results and remain effective over time?",
]
