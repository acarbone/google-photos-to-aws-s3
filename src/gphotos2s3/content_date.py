"""Best-effort capture-date extraction from a file's own embedded bytes.

Deliberately NOT the Google Takeout sidecar (metadata.py) — the sidecar is
per-occurrence, external data; two rows sharing identical content bytes
could in principle carry different sidecar dates, which would make
uploader.content_key's dedup-addressing occurrence-dependent again (see
spec/feat/chronological-s3-layout/plan.md §2). Everything here reads only
the bytes already spooled for hashing, so the same content always yields
the same result, regardless of which row/run/worker computes it — the
property uploader.content_key's pure-function guarantee depends on.

Never raises: any parse failure, missing tag, or unsupported format
returns None ("unknown-date" bucket for the caller), exactly like
metadata.py's stance on the external sidecar. Malformed embedded dates are
common in the wild (an unset camera clock writes literal zeros) and MUST
resolve to None rather than propagate — an uncaught exception here would
reach pipeline.py's generic exception handler, which is not in the
content-specific denylist, and could misclassify ordinary bad metadata as
a systemic failure and halt the whole run.
"""

from __future__ import annotations

import datetime
import logging
import struct
from typing import IO, BinaryIO, cast

import exifread

# exifread logs a WARNING for every file it can't find EXIF in — routine
# for this pipeline (screenshots, WhatsApp exports, and any other JPEG with
# no APP1/EXIF segment are common in a real photo library and are not an
# error condition here, just an unknown-date file). Silenced to avoid
# spamming the console once per such file during a real backup run.
logging.getLogger("exifread").setLevel(logging.ERROR)

# JPEG and TIFF-based RAW: exifread reads the EXIF/TIFF IFD directly.
_EXIF_EXTENSIONS = {".jpg", ".jpeg", ".dng", ".cr2", ".nef", ".arw"}

# ISO-BMFF containers: read via the hand-rolled mvhd box walker below.
# HEIC/HEIF are also ISO-BMFF but store EXIF in a different box structure
# this module doesn't parse — deliberately out of scope for v1, falls
# through to None like any other unsupported format.
_ISO_BMFF_EXTENSIONS = {".mp4", ".mov", ".m4v"}

_QUICKTIME_EPOCH = datetime.datetime(1904, 1, 1)
_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"


def extract_taken_at(spooled_file: IO[bytes], ext: str) -> datetime.datetime | None:
    """Best-effort capture-date extraction. Caller need not seek() before
    or after calling — this always leaves the file positioned at 0."""
    ext_lower = ext.lower()
    try:
        spooled_file.seek(0)
        if ext_lower in _EXIF_EXTENSIONS:
            return _extract_exif_date(spooled_file)
        if ext_lower in _ISO_BMFF_EXTENSIONS:
            return _extract_mvhd_date(spooled_file)
        return None
    except Exception:  # noqa: BLE001 - best-effort by design, see module docstring
        return None
    finally:
        spooled_file.seek(0)


# --------------------------------------------------------------------------
# EXIF (JPEG, TIFF-based RAW)
# --------------------------------------------------------------------------


def _extract_exif_date(f: IO[bytes]) -> datetime.datetime | None:
    # stop_tag short-circuits the scan once DateTimeOriginal is found; if
    # it's absent, exifread processes normally and "Image DateTime" (read
    # earlier, from IFD0) is still available as a fallback.
    # exifread's own type hints ask for BinaryIO specifically; IO[bytes] (our
    # public signature, matching hashing.spool_and_hash's return type) is
    # structurally identical at runtime — a SpooledTemporaryFile or BytesIO
    # satisfies it either way.
    tags = exifread.process_file(cast(BinaryIO, f), stop_tag="EXIF DateTimeOriginal", details=False)
    raw = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
    if raw is None:
        return None
    # "0000:00:00 00:00:00" is a common real-world placeholder (camera/phone
    # with an unset clock) — strptime raises ValueError for month/day 0,
    # which the caller's try/except turns into None, same as any other
    # unparseable value. Never special-cased separately; the outer except
    # is the single point of truth for "malformed date -> unknown-date".
    return datetime.datetime.strptime(str(raw), _EXIF_DATETIME_FORMAT)


# --------------------------------------------------------------------------
# ISO-BMFF (`mvhd` box) — MP4/MOV/M4V
# --------------------------------------------------------------------------


class _BoxHeader:
    __slots__ = ("box_type", "body_start", "body_end")

    def __init__(self, box_type: bytes, body_start: int, body_end: int) -> None:
        self.box_type = box_type
        self.body_start = body_start
        self.body_end = body_end


def _read_box_header(f: IO[bytes]) -> _BoxHeader | None:
    """Reads one ISO/IEC 14496-12 box header at the file's current
    position. Handles the 64-bit `largesize` extension (size field == 1)
    and the "box extends to EOF" case (size field == 0) — both are real,
    not hypothetical, for the multi-GB-`mdat`-before-`moov` files this
    walker exists to handle cheaply. Returns None on a short/truncated
    read (caller treats this as "no date found", never a raised error)."""
    box_start = f.tell()
    header = f.read(8)
    if len(header) < 8:
        return None
    size, box_type = struct.unpack(">I4s", header)
    if size == 1:
        ext = f.read(8)
        if len(ext) < 8:
            return None
        (size,) = struct.unpack(">Q", ext)
    if size == 0:
        current = f.tell()
        f.seek(0, 2)
        body_end = f.tell()
        f.seek(current)
    else:
        body_end = box_start + size
    return _BoxHeader(box_type, f.tell(), body_end)


def _walk_boxes(f: IO[bytes], start: int, end: int, target: bytes) -> _BoxHeader | None:
    """Scans sibling boxes in [start, end) for the first box of type
    `target`, without recursing — one level at a time, which is all
    either the top level or `moov`'s direct children ever need here.
    Bails out (returns None) rather than looping on a malformed size that
    doesn't advance the position, instead of trusting untrusted input to
    be well-formed."""
    f.seek(start)
    while f.tell() < end:
        pos_before = f.tell()
        header = _read_box_header(f)
        if header is None:
            return None
        if header.body_end <= pos_before or header.body_end > end:
            return None
        if header.box_type == target:
            return header
        f.seek(header.body_end)
    return None


def _parse_mvhd_creation_time(f: IO[bytes], body_start: int) -> int | None:
    f.seek(body_start)
    version_flags = f.read(4)
    if len(version_flags) < 4:
        return None
    version = version_flags[0]
    if version == 1:
        raw = f.read(8)
        if len(raw) < 8:
            return None
        (creation_time,) = struct.unpack(">Q", raw)
    else:
        raw = f.read(4)
        if len(raw) < 4:
            return None
        (creation_time,) = struct.unpack(">I", raw)
    return creation_time


def _extract_mvhd_date(f: IO[bytes]) -> datetime.datetime | None:
    f.seek(0, 2)
    file_end = f.tell()
    moov = _walk_boxes(f, 0, file_end, b"moov")
    if moov is None:
        return None
    mvhd = _walk_boxes(f, moov.body_start, moov.body_end, b"mvhd")
    if mvhd is None:
        return None
    creation_time = _parse_mvhd_creation_time(f, mvhd.body_start)
    if not creation_time:  # None, or 0 which means "not set" per spec
        return None
    return _QUICKTIME_EPOCH + datetime.timedelta(seconds=creation_time)
