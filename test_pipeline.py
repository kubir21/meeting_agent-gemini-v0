"""Run the full pipeline on the sample video in the project root (no browser).

Usage:
    python test_pipeline.py              # Gemini -> PDF -> email
    python test_pipeline.py --no-email   # skip email, keep the PDF in temp/
    python test_pipeline.py --video path/to/other.mp4
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import uuid
from pathlib import Path

import config
from pipeline import run_pipeline


def find_sample_video() -> Path:
    videos = sorted(
        p for p in config.BASE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in config.VIDEO_EXTENSIONS
    )
    if not videos:
        sys.exit(f"No video ({', '.join(sorted(config.VIDEO_EXTENSIONS))}) found in {config.BASE_DIR}")
    return videos[0]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # print Hindi etc. on Windows consoles
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-email", action="store_true", help="Skip sending the email and keep the PDF.")
    parser.add_argument("--video", type=Path, help="Video to use (default: first video in project root).")
    args = parser.parse_args()

    original = (args.video or find_sample_video()).resolve()
    if not original.is_file():
        sys.exit(f"Video not found: {original}")

    # Work on a temporary copy so the original is never modified or deleted.
    temp_copy = config.TEMP_DIR / f"{uuid.uuid4().hex}{original.suffix.lower()}"
    shutil.copy2(original, temp_copy)
    print(f"Using video: {original.name}  (temporary copy: temp/{temp_copy.name})")
    print(f"Model: {config.GEMINI_MODEL}\n")

    try:
        result = run_pipeline(temp_copy, original.name, send_email=not args.no_email, keep_pdf=args.no_email)
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("\n================ PARSED JSON ================")
    print(json.dumps(result["analysis"], indent=2, ensure_ascii=False))
    print("=============================================\n")
    if args.no_email:
        print(f"Email skipped (--no-email). PDF kept at: {result['pdf_path']}")
    else:
        print(f"Report emailed to {result['recipient']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
