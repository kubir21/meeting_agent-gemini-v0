"""Gemini integration: upload a video, wait until ACTIVE, extract JSON analysis.

Uses the current `google-genai` SDK (NOT the deprecated `google-generativeai`).
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

import config

log = logging.getLogger(__name__)

NOT_MENTIONED = "Not mentioned in the video."


class ConfigError(RuntimeError):
    """Missing/invalid configuration (e.g. API key not set)."""


class GeminiProcessingError(RuntimeError):
    """Gemini failed to process the file or returned unusable output."""


# --- Response schema ----------------------------------------------------------
class QAItem(BaseModel):
    question: str = Field(description="The question, copied verbatim.")
    answer: str = Field(description="Concise answer based strictly on the video.")
    reasoning: str = Field(description="One or two sentences of evidence from the video.")


class VideoAnalysis(BaseModel):
    transcript: str = Field(description="Full verbatim transcript with speaker labels.")
    qa: list[QAItem]


PROMPT_TEMPLATE = """You are a meticulous video analyst. Watch AND listen to the entire attached video.

Return ONLY a single JSON object (no markdown, no commentary) with exactly this shape:
{{
  "transcript": "<full exact transcript>",
  "qa": [
    {{"question": "<question 1 verbatim>", "answer": "<answer>", "reasoning": "<evidence>"}},
    {{"question": "<question 2 verbatim>", "answer": "<answer>", "reasoning": "<evidence>"}},
    {{"question": "<question 3 verbatim>", "answer": "<answer>", "reasoning": "<evidence>"}}
  ]
}}

TRANSCRIPT RULES
- Transcribe every spoken word exactly as spoken, in order, from start to end. Do not summarise, paraphrase, or translate.
- Keep the original language/script of each utterance (e.g. Hindi stays in Hindi, Hinglish stays as spoken).
- Put each speaker turn on its own line, prefixed with a speaker label: use the person's name if it is stated or shown on screen, otherwise "Speaker 1:", "Speaker 2:", etc.
- Mark non-speech sounds only if meaningful, in square brackets, e.g. [laughter], [music].
- If there is no speech at all, set transcript to "[No speech detected]".

QUESTIONS - answer each strictly from the video's audio and visual context:
{questions}

ANSWER RULES
- Base answers only on what is said or shown in the video. Do not use outside knowledge to invent facts.
- If an answer is not stated but can reasonably be inferred from context, give it and begin the answer with "Implied: ".
- If it is neither stated nor implied, answer exactly "{not_mentioned}".
- Keep each answer short (one sentence or a number/name); put supporting evidence in "reasoning".
"""


def build_prompt() -> str:
    qs = "\n".join(f"Q{i}: {q}" for i, q in enumerate(config.QUESTIONS, 1))
    return PROMPT_TEMPLATE.format(questions=qs, not_mentioned=NOT_MENTIONED)


# --- Client / file handling ----------------------------------------------------
def get_client() -> genai.Client:
    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY.startswith("paste-"):
        raise ConfigError("GEMINI_API_KEY is not set. Add it to the .env file (see .env.example).")
    return genai.Client(api_key=config.GEMINI_API_KEY)


def _state_name(file_obj: Any) -> str:
    state = getattr(file_obj, "state", None)
    if state is None:
        return "STATE_UNSPECIFIED"
    return str(getattr(state, "name", state)).upper().replace("FILESTATE.", "")


def upload_and_wait(client: genai.Client, path: Path, ref: dict) -> Any:
    """Upload `path` via the File API and block until it is ACTIVE.

    `ref["name"]` is set as soon as the upload succeeds so the caller can delete
    the remote file in a `finally` block even if a later step fails.
    """
    mime = config.VIDEO_MIME_TYPES.get(path.suffix.lower(), "video/mp4")
    log.info("Uploading %s to Gemini File API (%s)...", path.name, mime)
    file_obj = client.files.upload(file=str(path), config=types.UploadFileConfig(mime_type=mime))
    ref["name"] = file_obj.name
    log.info("Uploaded as %s; waiting for processing...", file_obj.name)

    deadline = time.monotonic() + config.FILE_PROCESSING_TIMEOUT_S
    while True:
        state = _state_name(file_obj)
        if state == "ACTIVE":
            log.info("File is ACTIVE.")
            return file_obj
        if state == "FAILED":
            raise GeminiProcessingError(f"Gemini failed to process the video: {getattr(file_obj, 'error', None)}")
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Video was not ready after {config.FILE_PROCESSING_TIMEOUT_S}s (last state: {state})."
            )
        time.sleep(config.POLL_INTERVAL_S)
        file_obj = client.files.get(name=file_obj.name)


def delete_remote_file(name: str | None) -> None:
    if not name:
        return
    try:
        get_client().files.delete(name=name)
        log.info("Deleted Gemini file %s", name)
    except Exception as exc:  # cleanup must never raise
        log.warning("Could not delete Gemini file %s: %s", name, exc)


# --- JSON parsing ----------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)\s*```", re.DOTALL)


def parse_model_json(text: str) -> dict:
    """Parse the model's JSON robustly (handles ```json fences / stray prose)."""
    if not text or not text.strip():
        raise GeminiProcessingError("Gemini returned an empty response.")
    candidates = [text.strip()]
    candidates += [m.group(1) for m in _FENCE_RE.finditer(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise GeminiProcessingError(f"Could not parse JSON from Gemini response: {text[:300]!r}")


def normalize_analysis(data: dict) -> dict:
    """Coerce arbitrary model output into {transcript, qa:[3 items in fixed order]}."""
    transcript = str(data.get("transcript") or "").strip() or "[No transcript returned]"
    raw_qa = data.get("qa") or data.get("answers") or data.get("questions") or []
    if isinstance(raw_qa, dict):  # e.g. {"Q1": "...", ...}
        raw_qa = [{"question": k, "answer": v} for k, v in raw_qa.items()]

    qa = []
    for i, question in enumerate(config.QUESTIONS):
        item = raw_qa[i] if i < len(raw_qa) else {}
        if not isinstance(item, dict):
            item = {"answer": item}
        qa.append(
            {
                "question": question,
                "answer": str(item.get("answer") or NOT_MENTIONED).strip(),
                "reasoning": str(item.get("reasoning") or "").strip(),
            }
        )
    return {"transcript": transcript, "qa": qa}


# --- Main entry point -----------------------------------------------------------
def analyze_video(path: Path, ref: dict) -> dict:
    """Upload the video, ask Gemini for transcript + answers, return parsed dict."""
    client = get_client()
    file_obj = upload_and_wait(client, path, ref)

    log.info("Requesting analysis from %s...", config.GEMINI_MODEL)
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=[file_obj, build_prompt()],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoAnalysis,
            temperature=0.1,
        ),
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, VideoAnalysis):
        data = parsed.model_dump()
    else:
        data = parse_model_json(response.text or "")
    analysis = normalize_analysis(data)
    analysis["model"] = config.GEMINI_MODEL
    return analysis
