from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from gphotos2s3.hashing import spool_and_hash
from tests.conftest import build_takeout_zip


def test_hash_matches_reference_hashlib(tmp_path: Path):
    content = b"hello world" * 1000
    zip_path = tmp_path / "t.zip"
    build_takeout_zip(zip_path, {"a.jpg": content})

    with zipfile.ZipFile(zip_path) as zf:
        spooled, sha256_hex, size = spool_and_hash(zf, "a.jpg")

    try:
        assert sha256_hex == hashlib.sha256(content).hexdigest()
        assert size == len(content)
        assert spooled.read() == content
    finally:
        spooled.close()


def test_spill_to_disk_path(tmp_path: Path):
    content = b"x" * 1000
    zip_path = tmp_path / "t.zip"
    build_takeout_zip(zip_path, {"a.jpg": content})

    with zipfile.ZipFile(zip_path) as zf:
        # Tiny max_memory_bytes forces the spooled file to spill to disk.
        spooled, sha256_hex, size = spool_and_hash(zf, "a.jpg", max_memory_bytes=16)

    try:
        assert sha256_hex == hashlib.sha256(content).hexdigest()
        assert size == 1000
        assert spooled.read() == content
    finally:
        spooled.close()


def test_zero_byte_file_hashed_like_any_other(tmp_path: Path):
    zip_path = tmp_path / "t.zip"
    build_takeout_zip(zip_path, {"empty.jpg": b""})

    with zipfile.ZipFile(zip_path) as zf:
        spooled, sha256_hex, size = spool_and_hash(zf, "empty.jpg")

    try:
        assert size == 0
        assert sha256_hex == hashlib.sha256(b"").hexdigest()
    finally:
        spooled.close()
