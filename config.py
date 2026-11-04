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
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "").strip()      # verified sender in Brevo
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Video Analysis Bot").strip()

# --- Gemini ------------------------------------------------------------------
# Change the model here (or set GEMINI_MODEL in .env).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
FILE_PROCESSING_TIMEOUT_S = 300   # max wait for uploaded video to become ACTIVE
POLL_INTERVAL_S = 3

# --- Email -------------------------------------------------------------------
RECIPIENT_EMAIL = "rk26.ftw@gmail.com"
EMAIL_SUBJECT = "Automated Video Analysis Report"

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
    "How many speakers are there in the video?",
    "What is the company name mentioned or implied?",
    "What is the average salary of employees mentioned or implied?",
]
