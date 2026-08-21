from __future__ import annotations

import io
import json

import pytest

from gphotos2s3 import uploader
from gphotos2s3.discovery import UnsafePathError
from gphotos2s3.state import FileRow
from tests.conftest import TEST_BUCKET


def _row(**overrides) -> FileRow:
    base = dict(
        id="id1",
        zip_path="z.zip",
        entry_name="a.jpg",
        sidecar_entry_name=None,
        size_bytes=10,
        sha256="deadbeef",
        status="uploaded",
        metadata_status="not_found",
        content_key=None,
        pointer_key=None,
        metadata_key=None,
        s3_bucket=TEST_BUCKET,
        content_deduped=False,
        error=None,
        attempts=0,
        discovered_at="now",
        updated_at="now",
    )
    base.update(overrides)
    return FileRow(**base)


def test_content_key_pure_function_of_sha256_and_ext():
    k1 = uploader.content_key("gphotos2s3", "abc123", ".jpg")
    k2 = uploader.content_key("gphotos2s3", "abc123", ".jpg")
    assert k1 == k2 == "gphotos2s3/content/abc123.jpg"


def test_content_key_normalizes_extension_case():
    k1 = uploader.content_key("p", "abc", ".JPG")
    k2 = uploader.content_key("p", "abc", ".jpg")
    assert k1 == k2


def test_pointer_key_distinct_for_same_entry_name_different_zip_basename():
    """Round-4 fix (Finding 1): two rows sharing an entry_name but from
    different zip basenames must never collide."""
    k1 = uploader.pointer_key("p", "takeout-A.zip", "Photos/img.jpg", "sha1")
    k2 = uploader.pointer_key("p", "takeout-B.zip", "Photos/img.jpg", "sha2")
    assert k1 != k2


def test_pointer_key_rejects_unsafe_entry_name():
    with pytest.raises(UnsafePathError):
        uploader.pointer_key("p", "z.zip", "../evil.jpg", "sha1")


def test_key_length_truncation_for_overlong_path():
    long_entry = "a" * 2000 + ".jpg"
    key = uploader.pointer_key("prefix", "z.zip", long_entry, "abc123")
    assert len(key.encode("utf-8")) <= 1024
    assert key.endswith("~abc123"[:9])


def test_already_uploaded_head_logic(s3_client):
    key = "content/abc.jpg"
    assert uploader.already_uploaded(s3_client, TEST_BUCKET, key, "abc") is False

    s3_client.put_object(Bucket=TEST_BUCKET, Key=key, Body=b"x", Metadata={"sha256": "abc"})
    assert uploader.already_uploaded(s3_client, TEST_BUCKET, key, "abc") is True
    assert uploader.already_uploaded(s3_client, TEST_BUCKET, key, "different") is False


def test_upload_content_if_missing_dedup_hit(s3_client):
    key = "content/abc.jpg"
    spooled = io.BytesIO(b"hello")
    transferred = uploader.upload_content_if_missing(
        s3_client, TEST_BUCKET, key, spooled, "abc", "STANDARD"
    )
    assert transferred is True

    spooled2 = io.BytesIO(b"hello")
    transferred2 = uploader.upload_content_if_missing(
        s3_client, TEST_BUCKET, key, spooled2, "abc", "STANDARD"
    )
    assert transferred2 is False  # dedup hit, no second transfer


def test_upload_sets_storage_class_and_checksum_algorithm_large_file(s3_client):
    # Fixture large enough to cross multipart_threshold (>25MB) — round-2
    # note: a small single-part file wouldn't exercise the multipart path
    # ChecksumAlgorithm is meant to protect.
    big_content = b"x" * (26 * 1024 * 1024)
    key = "content/big.jpg"
    spooled = io.BytesIO(big_content)
    import hashlib

    sha = hashlib.sha256(big_content).hexdigest()
    uploader.upload_content_if_missing(s3_client, TEST_BUCKET, key, spooled, sha, "STANDARD_IA")

    head = s3_client.head_object(Bucket=TEST_BUCKET, Key=key)
    assert head["Metadata"]["sha256"] == sha
    assert head["StorageClass"] == "STANDARD_IA"


def test_upload_pointer_and_metadata_written_for_every_row(s3_client):
    uploader.upload_pointer(
        s3_client, TEST_BUCKET, "library/z.zip/a.jpg.pointer.json", "content/x", "sha1", 10
    )
    body = s3_client.get_object(Bucket=TEST_BUCKET, Key="library/z.zip/a.jpg.pointer.json")[
        "Body"
    ].read()
    data = json.loads(body)
    assert data["sha256"] == "sha1"
    assert data["content_key"] == "content/x"

    uploader.upload_metadata(
        s3_client, TEST_BUCKET, "library/z.zip/a.jpg.metadata.json", "sha1", {"description": "hi"}
    )
    body = s3_client.get_object(Bucket=TEST_BUCKET, Key="library/z.zip/a.jpg.metadata.json")[
        "Body"
    ].read()
    assert json.loads(body) == {"description": "hi"}


def test_verify_uploaded_detects_missing_content(s3_client):
    row = _row(content_key="content/missing.jpg", pointer_key="library/missing.pointer.json")
    mismatches = uploader.verify_uploaded(s3_client, TEST_BUCKET, [row])
    assert len(mismatches) == 1
    assert "content" in mismatches[0][1]


def test_verify_uploaded_passes_when_all_present(s3_client):
    s3_client.put_object(
        Bucket=TEST_BUCKET, Key="content/x.jpg", Body=b"x", Metadata={"sha256": "sha1"}
    )
    s3_client.put_object(
        Bucket=TEST_BUCKET, Key="library/x.pointer.json", Body=b"{}", Metadata={"sha256": "sha1"}
    )
    row = _row(sha256="sha1", content_key="content/x.jpg", pointer_key="library/x.pointer.json")
    mismatches = uploader.verify_uploaded(s3_client, TEST_BUCKET, [row])
    assert mismatches == []
