"""S3 client wrapper — content-addressed keys, HEAD idempotency, upload.

Round-3/round-4 redesign (see spec/feat/google-photos-s3-backup/plan.md §6):
keys are content-addressed, not path-derived. `content_key` is a pure
function of (sha256, normalized extension) — any row, on any run, with or
without a local state DB, independently arrives at the same answer for
"where does this content live in S3." There is no "canonical row" concept:
dedup correctness cannot be broken by a worker race or a state-DB loss,
because there is no runtime-assigned ownership left to get wrong.

No zip file handling lives here — that's discovery.py/pipeline.py's job.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import IO, Any

from boto3.s3.transfer import TransferConfig

from gphotos2s3.discovery import UnsafePathError, is_unsafe_entry_name
from gphotos2s3.state import FileRow

TRANSFER_CONFIG = TransferConfig(multipart_threshold=25 * 1024 * 1024, max_concurrency=4)
_MAX_KEY_LENGTH = 1024
_TRUNCATE_SUFFIX_LEN = 8


def _sanitize(name: str) -> str:
    """Defense-in-depth double check (discovery.py already rejects unsafe
    entry names before a row ever reaches this layer): raise rather than
    silently collapse a malformed path segment, preserving the uniqueness
    argument pointer_key/metadata_key depend on — they must treat their
    input exactly as strictly as row `id`'s own raw hash does."""
    reason = is_unsafe_entry_name(name)
    if reason is not None:
        raise UnsafePathError(f"unsafe path in key component: {reason}")
    return name


def _truncate_key(key: str, sha256_hex: str) -> str:
    """S3's 1024-byte key length limit: deterministically shorten an
    overlong pointer/metadata key (truncate the tail, append an 8-char hex
    suffix of the row's own sha256 to keep it unique) rather than leaving it
    to fail every retry identically (risk review M5). content_key cannot
    exceed the limit — a fixed-length hex digest plus a short extension is
    always well under 1024 bytes."""
    encoded_len = len(key.encode("utf-8"))
    if encoded_len <= _MAX_KEY_LENGTH:
        return key
    suffix = f"~{sha256_hex[:_TRUNCATE_SUFFIX_LEN]}"
    overshoot = encoded_len - _MAX_KEY_LENGTH + len(suffix.encode("utf-8"))
    # Truncate on a UTF-8-safe boundary by trimming characters, not bytes.
    truncated = key
    while len(truncated.encode("utf-8")) > _MAX_KEY_LENGTH - len(suffix.encode("utf-8")):
        truncated = truncated[:-1]
    del overshoot
    return truncated + suffix


def content_key(prefix: str, sha256_hex: str, ext: str) -> str:
    """Pure function of (sha256, normalized extension) — same content
    always resolves to the same key, regardless of which row computes it,
    regardless of processing order, regardless of whether the local state
    DB has ever seen this content before. This is the fix for the
    round-2-Critical dedup-after-state-loss race."""
    normalized_ext = ext.lower()
    return f"{prefix}/content/{sha256_hex}{normalized_ext}"


def pointer_key(prefix: str, zip_basename: str, entry_name: str, sha256_hex: str) -> str:
    """Takes exactly the same two inputs (zip_basename, entry_name) as row
    `id` itself (discovery.py). Two rows can only collide on pointer_key if
    they would also collide on `id` — and an `id` collision is already
    handled at discovery time by INSERT OR IGNORE. No separate collision
    guard needed: uniqueness is inherited directly from row identity."""
    key = f"{prefix}/library/{_sanitize(zip_basename)}/{_sanitize(entry_name)}.pointer.json"
    return _truncate_key(key, sha256_hex)


def metadata_key(prefix: str, zip_basename: str, entry_name: str, sha256_hex: str) -> str:
    key = f"{prefix}/library/{_sanitize(zip_basename)}/{_sanitize(entry_name)}.metadata.json"
    return _truncate_key(key, sha256_hex)


def already_uploaded(s3_client: Any, bucket: str, key: str, sha256_hex: str) -> bool:
    """Idempotency check: HEAD, compare stored sha256 metadata. Used for the
    content object (pure function of sha256) and independently for each
    row's own pointer/metadata objects (pure function of that row's path).

    TOCTOU note: this HEAD and the eventual upload are not perfectly atomic.
    For content_key the only possible race is two workers uploading
    identical bytes to the same key concurrently — self-correcting (S3
    stores the same bytes twice under one key, no duplicate object, no data
    loss); the per-sha256 in-process lock in pipeline.py further reduces
    this to a single winner as an efficiency optimization, not a
    correctness requirement."""
    try:
        head = s3_client.head_object(Bucket=bucket, Key=key)
    except s3_client.exceptions.ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
    return head.get("Metadata", {}).get("sha256") == sha256_hex


def upload_content_if_missing(
    s3_client: Any,
    bucket: str,
    key: str,
    spooled_file: IO[bytes],
    sha256_hex: str,
    storage_class: str,
) -> bool:
    """Returns True if bytes were actually transferred, False if the
    content was already present (dedup hit)."""
    if already_uploaded(s3_client, bucket, key, sha256_hex):
        return False
    spooled_file.seek(0)
    s3_client.upload_fileobj(
        spooled_file,
        bucket,
        key,
        ExtraArgs={
            "StorageClass": storage_class,
            "ServerSideEncryption": "AES256",
            "ChecksumAlgorithm": "SHA256",
            "Metadata": {"sha256": sha256_hex},
        },
        Config=TRANSFER_CONFIG,
    )
    return True


def upload_pointer(
    s3_client: Any,
    bucket: str,
    key: str,
    content_key_value: str,
    sha256_hex: str,
    size_bytes: int,
) -> None:
    """Always runs, for every row, dedup hit or not — a small JSON PUT,
    cheap even at scale. Gives every occurrence (including duplicates) its
    own full path-based pointer, resolving risk review M3 structurally."""
    body = json.dumps(
        {"sha256": sha256_hex, "content_key": content_key_value, "size_bytes": size_bytes}
    ).encode("utf-8")
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        ServerSideEncryption="AES256",
        Metadata={"sha256": sha256_hex},
    )


def upload_metadata(
    s3_client: Any,
    bucket: str,
    key: str,
    sha256_hex: str,
    metadata_dict: dict[str, Any],
) -> None:
    """Uploads the full parsed sidecar (not just the trimmed object-metadata
    fields — S3 user-metadata headers are capped at 2KB total) as its own
    companion object, tracked via the row's metadata_status column."""
    body = json.dumps(metadata_dict).encode("utf-8")
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        ServerSideEncryption="AES256",
        Metadata={"sha256": sha256_hex},
    )


def verify_uploaded(
    s3_client: Any, bucket: str, rows: Iterable[FileRow]
) -> list[tuple[FileRow, str]]:
    """Bulk re-check for `gphotos2s3 verify`: HEAD each 'uploaded' row's
    content, pointer, and (when present) metadata objects, compare sha256;
    returns (row, mismatch_reason) for anything that doesn't match, without
    re-uploading."""
    mismatches: list[tuple[FileRow, str]] = []
    for row in rows:
        if row.sha256 is None:
            mismatches.append((row, "no sha256 recorded"))
            continue
        if row.content_key is None or not already_uploaded(
            s3_client, bucket, row.content_key, row.sha256
        ):
            mismatches.append((row, "content object missing or checksum mismatch"))
            continue
        if row.pointer_key is None or not already_uploaded(
            s3_client, bucket, row.pointer_key, row.sha256
        ):
            mismatches.append((row, "pointer object missing or checksum mismatch"))
            continue
        if row.metadata_status == "uploaded" and (
            row.metadata_key is None
            or not already_uploaded(s3_client, bucket, row.metadata_key, row.sha256)
        ):
            mismatches.append((row, "metadata object missing or checksum mismatch"))
    return mismatches


def guess_extension(entry_name: str) -> str:
    return Path(entry_name).suffix.lower()
