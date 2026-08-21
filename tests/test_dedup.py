from __future__ import annotations

from pathlib import Path

from gphotos2s3 import pipeline
from gphotos2s3.discovery import discover_sources
from tests.conftest import TEST_BUCKET, build_takeout_zip


def test_duplicate_content_reuses_content_key_own_pointer(
    s3_client, state_store, config, tmp_path: Path
):
    zip_path = tmp_path / "takeout-001.zip"
    identical = b"same-bytes-everywhere"
    build_takeout_zip(
        zip_path,
        {
            "Album A/photo.jpg": identical,
            "Album B/photo.jpg": identical,
        },
    )
    discover_sources([zip_path], state_store)
    summary = pipeline.run_pipeline(state_store, s3_client, config, [zip_path])
    assert summary.uploaded == 2

    rows = list(state_store.iter_by_status("uploaded"))
    assert len(rows) == 2
    assert rows[0].content_key == rows[1].content_key  # same content -> same key
    assert rows[0].pointer_key != rows[1].pointer_key  # own pointer each

    # Exactly one content PUT of the actual bytes.
    objs = s3_client.list_objects_v2(Bucket=TEST_BUCKET, Prefix=f"{config.prefix}/content/")
    assert objs["KeyCount"] == 1

    deduped = [r for r in rows if r.content_deduped]
    assert len(deduped) == 1


def test_same_entry_name_different_zip_parts_no_pointer_collision(
    s3_client, state_store, config, tmp_path: Path
):
    """Round-4, Finding 1: two occurrences with the identical entry_name but
    different zip basenames must get distinct pointer keys, even across two
    different zip 'sessions'."""
    zip1 = tmp_path / "takeout-20260101-001.zip"
    zip2 = tmp_path / "takeout-20260601-001.zip"
    build_takeout_zip(zip1, {"Photos from 2020/img.jpg": b"content-one"})
    build_takeout_zip(zip2, {"Photos from 2020/img.jpg": b"content-two"})

    discover_sources([zip1, zip2], state_store)
    pipeline.run_pipeline(state_store, s3_client, config, [zip1, zip2])

    rows = list(state_store.iter_by_status("uploaded"))
    assert len(rows) == 2
    pointer_keys = {r.pointer_key for r in rows}
    content_keys = {r.content_key for r in rows}
    assert len(pointer_keys) == 2  # no collision
    assert len(content_keys) == 2  # genuinely different content


def test_extension_case_normalization_dedupes(s3_client, state_store, config, tmp_path: Path):
    zip_path = tmp_path / "takeout-001.zip"
    identical = b"same-bytes"
    build_takeout_zip(zip_path, {"a/photo.JPG": identical, "a/photo2.jpg": identical})
    discover_sources([zip_path], state_store)
    pipeline.run_pipeline(state_store, s3_client, config, [zip_path])

    rows = list(state_store.iter_by_status("uploaded"))
    assert rows[0].content_key == rows[1].content_key


def test_concurrent_workers_never_produce_two_content_objects(
    s3_client, state_store, config, tmp_path: Path
):
    """Concurrent-worker race (risk H2): content-addressing makes this true
    structurally, not just via the lock."""
    config.workers = 8
    zip_path = tmp_path / "takeout-001.zip"
    identical = b"race-condition-bytes"
    entries = {f"Album{i}/photo.jpg": identical for i in range(10)}
    build_takeout_zip(zip_path, entries)
    discover_sources([zip_path], state_store)

    summary = pipeline.run_pipeline(state_store, s3_client, config, [zip_path])
    assert summary.uploaded == 10

    objs = s3_client.list_objects_v2(Bucket=TEST_BUCKET, Prefix=f"{config.prefix}/content/")
    assert objs["KeyCount"] == 1
