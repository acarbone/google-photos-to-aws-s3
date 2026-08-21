"""H8 (risk review): the plan's central resilience claim — S3 is the
ultimate source of truth even after full local state-DB loss.

Round-2 required workers >= 2 + an explicit distinct-content-object-count
assertion (the original spec could pass while hiding the canonical-row
race). Round-3/4 additionally require covering the pointer/metadata
collision class: two independent zip sources whose relative paths collide
but whose zip basenames and content differ.
"""

from __future__ import annotations

from pathlib import Path

from gphotos2s3 import pipeline
from gphotos2s3.config import Config, db_path
from gphotos2s3.discovery import discover_sources
from gphotos2s3.state import open_state
from tests.conftest import build_takeout_zip


def test_full_state_db_loss_with_concurrent_workers_no_duplicate_content(
    s3_client, config: Config, tmp_path: Path
):
    config.workers = 4
    state_dir = tmp_path / "state"
    zip_path = tmp_path / "takeout-001.zip"
    identical = b"duplicated-across-albums"
    entries = {f"Album{i}/photo.jpg": identical for i in range(6)}
    entries["Album-unique/only-one.jpg"] = b"unique-content"
    build_takeout_zip(zip_path, entries)

    # --- Run 1: full backup ---
    with open_state(db_path(state_dir)) as state:
        discover_sources([zip_path], state)
        summary1 = pipeline.run_pipeline(state, s3_client, config, [zip_path])
        assert summary1.uploaded == 7

    objs_after_run1 = s3_client.list_objects_v2(
        Bucket=config.bucket, Prefix=f"{config.prefix}/content/"
    )
    content_keys_after_run1 = {o["Key"] for o in objs_after_run1.get("Contents", [])}
    assert len(content_keys_after_run1) == 2  # 1 for the 6 duplicates, 1 for the unique file

    # --- Simulate total local state loss ---
    db_path(state_dir).unlink()
    (db_path(state_dir).with_suffix(".db-wal")).unlink(missing_ok=True)
    (db_path(state_dir).with_suffix(".db-shm")).unlink(missing_ok=True)

    # --- Run 2: rediscover + rehash from scratch, workers >= 2 ---
    with open_state(db_path(state_dir)) as state:
        discover_sources([zip_path], state)
        summary2 = pipeline.run_pipeline(state, s3_client, config, [zip_path])
        assert summary2.uploaded == 7

    objs_after_run2 = s3_client.list_objects_v2(
        Bucket=config.bucket, Prefix=f"{config.prefix}/content/"
    )
    content_keys_after_run2 = {o["Key"] for o in objs_after_run2.get("Contents", [])}

    # The central claim: no duplicate content object was created under a
    # different key. Content addressing makes this a pure-function
    # guarantee, not a lock-discipline one.
    assert content_keys_after_run2 == content_keys_after_run1


def test_colliding_relative_paths_across_independent_export_sessions(
    s3_client, config: Config, state_store, tmp_path: Path
):
    """Round-4, Finding 1/6: two zip sources whose relative paths collide
    (same album/entry name) but whose zip basenames and content differ must
    resolve to distinct pointer_key/metadata_key with correct per-row
    content — not silently overwrite each other."""
    zip_session_a = tmp_path / "takeout-20260101T000000Z-001.zip"
    zip_session_b = tmp_path / "takeout-20260601T000000Z-001.zip"
    build_takeout_zip(zip_session_a, {"Photos from 2020/IMG_0001.jpg": b"session-a-bytes"})
    build_takeout_zip(zip_session_b, {"Photos from 2020/IMG_0001.jpg": b"session-b-bytes"})

    discover_sources([zip_session_a, zip_session_b], state_store)
    summary = pipeline.run_pipeline(state_store, s3_client, config, [zip_session_a, zip_session_b])
    assert summary.uploaded == 2

    rows = list(state_store.iter_by_status("uploaded"))
    assert len(rows) == 2
    pointer_keys = {r.pointer_key for r in rows}
    content_keys = {r.content_key for r in rows}
    assert len(pointer_keys) == 2, "pointer keys must not collide across export sessions"
    assert len(content_keys) == 2, "content genuinely differs, so content keys must differ too"

    # Correct per-row content survives — neither row clobbered the other.
    for row in rows:
        body = s3_client.get_object(Bucket=config.bucket, Key=row.content_key)["Body"].read()
        assert body in (b"session-a-bytes", b"session-b-bytes")
    bodies = {
        s3_client.get_object(Bucket=config.bucket, Key=r.content_key)["Body"].read() for r in rows
    }
    assert bodies == {b"session-a-bytes", b"session-b-bytes"}
