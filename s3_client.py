"""AWS S3 Integration for direct client uploads and video streaming.

Enables browsers to upload videos (up to 500 MB) directly to Amazon S3
via multipart presigned URLs, bypassing server payload limits (Vercel 4.5 MB).
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import config

log = logging.getLogger(__name__)

_S3_CLIENT = None


def get_s3_client():
    """Return a cached, thread-safe boto3 S3 client."""
    global _S3_CLIENT
    if _S3_CLIENT is None:
        if not (config.AWS_ACCESS_KEY_ID and config.AWS_SECRET_ACCESS_KEY):
            raise RuntimeError("AWS credentials (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) not configured.")
        _S3_CLIENT = boto3.client(
            "s3",
            region_name=config.AWS_REGION,
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return _S3_CLIENT


def is_s3_configured() -> bool:
    """Check whether AWS S3 credentials and bucket name are set."""
    return bool(config.AWS_ACCESS_KEY_ID and config.AWS_SECRET_ACCESS_KEY and config.S3_BUCKET_NAME)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to keep safe alphanumeric characters and extension."""
    name = Path(filename).name
    # Keep letters, numbers, dash, underscore, dot
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return clean or "video.mp4"


def generate_s3_key(filename: str) -> str:
    """Generate a unique S3 key inside the configured prefix."""
    safe_name = sanitize_filename(filename)
    unique_prefix = uuid.uuid4().hex
    prefix = config.S3_PREFIX.strip("/")
    if prefix:
        return f"{prefix}/{unique_prefix}_{safe_name}"
    return f"{unique_prefix}_{safe_name}"


def initiate_multipart_upload(filename: str, content_type: str = "video/mp4") -> dict[str, str]:
    """Start an S3 multipart upload and return key and uploadId."""
    s3 = get_s3_client()
    key = generate_s3_key(filename)
    try:
        resp = s3.create_multipart_upload(
            Bucket=config.S3_BUCKET_NAME,
            Key=key,
            ContentType=content_type,
        )
        upload_id = resp["UploadId"]
        log.info("Initiated S3 multipart upload for %s (Key: %s, UploadId: %s)", filename, key, upload_id)
        return {
            "key": key,
            "upload_id": upload_id,
            "bucket": config.S3_BUCKET_NAME,
        }
    except ClientError as exc:
        log.error("Failed to initiate S3 multipart upload: %s", exc)
        raise RuntimeError(f"S3 initiate failed: {exc}")


def sign_part_upload(key: str, upload_id: str, part_number: int, expires_in: int = 3600) -> str:
    """Generate a presigned PUT URL for a specific multipart part."""
    s3 = get_s3_client()
    try:
        url = s3.generate_presigned_url(
            ClientMethod="upload_part",
            Params={
                "Bucket": config.S3_BUCKET_NAME,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": int(part_number),
            },
            ExpiresIn=expires_in,
        )
        return url
    except ClientError as exc:
        log.error("Failed to sign S3 part %s: %s", part_number, exc)
        raise RuntimeError(f"Failed to sign S3 part {part_number}: {exc}")


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Complete a multipart upload with the list of part numbers and ETags."""
    s3 = get_s3_client()
    # Format parts list as required by boto3: [{"PartNumber": int, "ETag": str}, ...]
    formatted_parts = []
    for p in parts:
        pn = int(p.get("PartNumber") or p.get("part_number") or 0)
        etag = str(p.get("ETag") or p.get("etag") or "").strip().strip('"')
        formatted_parts.append({"PartNumber": pn, "ETag": f'"{etag}"'})

    formatted_parts.sort(key=lambda x: x["PartNumber"])
    try:
        resp = s3.complete_multipart_upload(
            Bucket=config.S3_BUCKET_NAME,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": formatted_parts},
        )
        log.info("Successfully completed S3 upload: %s", key)
        return {
            "status": "completed",
            "key": key,
            "location": resp.get("Location", ""),
        }
    except ClientError as exc:
        log.error("Failed to complete S3 multipart upload for %s: %s", key, exc)
        raise RuntimeError(f"S3 completion failed: {exc}")


def abort_multipart_upload(key: str, upload_id: str) -> None:
    """Abort an in-progress multipart upload to free resources."""
    s3 = get_s3_client()
    try:
        s3.abort_multipart_upload(
            Bucket=config.S3_BUCKET_NAME,
            Key=key,
            UploadId=upload_id,
        )
        log.info("Aborted S3 multipart upload: %s", key)
    except Exception as exc:
        log.warning("Could not abort S3 multipart upload (%s): %s", key, exc)


def delete_s3_object(key: str) -> bool:
    """Delete an object from S3. Safe cleanup (does not raise)."""
    if not key:
        return False
    try:
        s3 = get_s3_client()
        s3.delete_object(Bucket=config.S3_BUCKET_NAME, Key=key)
        log.info("Deleted S3 object: %s", key)
        return True
    except Exception as exc:
        log.warning("Failed to delete S3 object %s: %s", key, exc)
        return False


def download_s3_to_temp(key: str, destination: Path) -> Path:
    """Download an S3 object to a local temporary path."""
    s3 = get_s3_client()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        log.info("Downloading s3://%s/%s -> %s", config.S3_BUCKET_NAME, key, destination.name)
        s3.download_file(config.S3_BUCKET_NAME, key, str(destination))
        log.info("Download completed (%s bytes)", destination.stat().st_size)
        return destination
    except ClientError as exc:
        log.error("Failed to download S3 object %s: %s", key, exc)
        raise RuntimeError(f"Could not retrieve video from S3: {exc}")
