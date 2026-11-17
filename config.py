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
TEMP_DIR = Path("/tmp") if os.getenv("VERCEL") else BASE_DIR / "temp"  # on Vercel /tmp is writable
STATIC_DIR = BASE_DIR / "static"      # frontend files
FONTS_DIR = BASE_DIR / "fonts"        # bundled Unicode fonts for the PDF
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# --- Secrets (from .env) -----------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()       # Gemini API key
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()                # Brevo API key
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()  # Gmail App Password

# --- AWS S3 (Direct Storage) -------------------------------------------------
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1").strip()
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "eventyst-videos").strip()
S3_PREFIX = os.getenv("S3_PREFIX", "uploads/").strip()
S3_ENABLED = bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and S3_BUCKET_NAME)

# --- Gemini ------------------------------------------------------------------
# Change the model here (or set GEMINI_MODEL in .env).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite").strip()
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
    "Six Pillars of Wellbeing: What are the six pillars of employee wellbeing identified or referenced in the presentation, and what is the organisation's core philosophy on each?",
    "Initiatives Implemented: What specific programmes, initiatives, or workplace policies have been implemented to support employee wellbeing across these pillars?",
    "Key Findings & Impact: What measurable improvements, metrics, survey feedback, or notable findings resulted from the initiatives discussed?",
    "Growth & Professional Development: How does the organisation foster continuous learning, skill enhancement, and career growth within its employee wellbeing framework?",
    "Feedback & Long-term Sustainability: How is employee feedback gathered and evaluated, and how does leadership ensure these initiatives remain effective and sustainable over time?",
]
