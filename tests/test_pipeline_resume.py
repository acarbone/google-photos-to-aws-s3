"""C1 (Critical, round 1): the original 'kill after N files' design never
exercised reconciliation because it only killed at a clean file boundary.
This file injects failure INSIDE the transfer itself, for both dangerous
sub-cases named in the plan (§10):
  (a) S3 receives the object but the local DB commit is interrupted before
      recording 'uploaded'.
  (b) mid-multipart with no visible object yet (orphaned multipart upload).
"""

from __future__ import annotations

from pathlib import Path

from gphotos2s3 import pipeline
from gphotos2s3.discovery import discover_sources
from tests.conftest import build_takeout_zip


def test_resume_after_s3_success_but_db_commit_interrupted(
    s3_client, state_store, config, tmp_path: Path
):
    """Sub-case (a): simulate the process dying after the content object is
    actually in S3, but before mark_uploaded() ever ran — the row is left
    'uploading'. Reconciliation on the next run must resolve it to
    'uploaded' WITHOUT re-transferring."""
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"a/photo.jpg": b"content-bytes"})
    discover_sources([zip_path], state_store)
    row = next(state_store.iter_by_status("pending"))

    # Manually reproduce what process_one does up to (and including) the S3
    # PUT, but stop before the state DB is ever told 'uploaded' — this is
    # exactly the crash window C1 targets.
    import zipfile

    from gphotos2s3 import uploader
    from gphotos2s3.hashing import spool_and_hash

    with zipfile.ZipFile(zip_path) as zf:
        spooled, sha256_hex, size = spool_and_hash(zf, row.entry_name)
    state_store.mark_hashed(row.id, sha256_hex, size)
    state_store.mark_uploading(row.id)  # <-- crash happens right after this

    c_key = uploader.content_key(config.prefix, sha256_hex, ".jpg")
    p_key = uploader.pointer_key(config.prefix, Path(zip_path).name, row.entry_name, sha256_hex)
    uploader.upload_content_if_missing(
        s3_client, config.bucket, c_key, spooled, sha256_hex, "STANDARD"
    )
    uploader.upload_pointer(s3_client, config.bucket, p_key, c_key, sha256_hex, size)
    spooled.close()
    # PROCESS DIES HERE — mark_uploaded() never runs. Row is stuck 'uploading'.

    assert state_store.get(row.id).status == "uploading"

    reconciled = pipeline.reconcile_stuck_rows(state_store, s3_client, config.bucket, config.prefix)
    assert reconciled == 1
    final = state_store.get(row.id)
    assert final.status == "uploaded"
    assert final.content_key == c_key

    # Critically: no re-transfer happened — verify the content object still
    # has exactly the bytes from the one PUT above (no second write).
    body = s3_client.get_object(Bucket=config.bucket, Key=c_key)["Body"].read()
    assert body == b"content-bytes"


def test_resume_after_upgrade_finds_content_at_legacy_flat_key(
    s3_client, state_store, config, tmp_path: Path
):
    """A row left 'uploading' by a pre-chronological-layout version has no
    taken_at and may have already uploaded its content under the OLD flat
    key. Reconciliation must find it there rather than concluding 'not
    uploaded' and re-uploading under the new unknown-date key
    (chronological-s3-layout plan §3.4b — closes a reopening of the
    round-2 dedup-race class on the first run after upgrading)."""
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"a/photo.jpg": b"content-bytes"})
    discover_sources([zip_path], state_store)
    row = next(state_store.iter_by_status("pending"))

    import zipfile

    from gphotos2s3 import uploader
    from gphotos2s3.hashing import spool_and_hash

    with zipfile.ZipFile(zip_path) as zf:
        spooled, sha256_hex, size = spool_and_hash(zf, row.entry_name)
    # taken_at intentionally NOT passed — simulates a row hashed by a
    # pre-upgrade version, which had no such column (NULL after migration).
    state_store.mark_hashed(row.id, sha256_hex, size)
    state_store.mark_uploading(row.id)

    legacy_c_key = f"{config.prefix}/content/{sha256_hex}.jpg"
    s3_client.put_object(
        Bucket=config.bucket,
        Key=legacy_c_key,
        Body=spooled.read(),
        Metadata={"sha256": sha256_hex},
    )
    p_key = uploader.pointer_key(config.prefix, Path(zip_path).name, row.entry_name, sha256_hex)
    uploader.upload_pointer(s3_client, config.bucket, p_key, legacy_c_key, sha256_hex, size)
    spooled.close()
    # PROCESS DIES HERE, then the tool is upgraded to the chronological
    # layout before the next run.

    reconciled = pipeline.reconcile_stuck_rows(state_store, s3_client, config.bucket, config.prefix)
    assert reconciled == 1
    final = state_store.get(row.id)
    assert final.status == "uploaded"
    assert final.content_key == legacy_c_key  # records where the bytes actually are

    # No duplicate content object was created under the new-scheme key.
    new_scheme_objs = s3_client.list_objects_v2(
        Bucket=config.bucket, Prefix=f"{config.prefix}/content/unknown-date/"
    )
    assert new_scheme_objs.get("KeyCount", 0) == 0


def test_resume_after_mid_multipart_no_visible_object(
    s3_client, state_store, config, tmp_path: Path
):
    """Sub-case (b): the content object was never actually completed (no
    upload_content_if_missing call reached S3 at all) — simulating a crash
    mid-multipart-upload, before CompleteMultipartUpload. The row is stuck
    'uploading' with no object present. Reconciliation must reset it to
    'pending', not leave it stuck or wrongly mark it uploaded."""
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"a/photo.jpg": b"content-bytes"})
    discover_sources([zip_path], state_store)
    row = next(state_store.iter_by_status("pending"))

    state_store.mark_hashed(row.id, "fake-sha-never-uploaded", 13)
    state_store.mark_uploading(row.id)
    # PROCESS DIES HERE — no S3 object was ever created.

    reconciled = pipeline.reconcile_stuck_rows(state_store, s3_client, config.bucket, config.prefix)
    assert reconciled == 1
    final = state_store.get(row.id)
    assert final.status == "pending"
    assert final.attempts == 0  # not the file's fault


def test_full_run_resumes_correctly_with_no_double_upload(
    s3_client, state_store, config, tmp_path: Path
):
    """End-to-end: a full run followed by a second run against the same
    (already-complete) state never re-uploads anything."""
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"a/one.jpg": b"one", "a/two.jpg": b"two"})
    discover_sources([zip_path], state_store)

    summary1 = pipeline.run_pipeline(state_store, s3_client, config, [zip_path])
    assert summary1.uploaded == 2

    objs_before = s3_client.list_objects_v2(
        Bucket=config.bucket, Prefix=f"{config.prefix}/content/"
    )
    keys_before = {o["Key"] for o in objs_before.get("Contents", [])}

    summary2 = pipeline.run_pipeline(state_store, s3_client, config, [zip_path])
    assert summary2.uploaded == 2  # still 2 uploaded rows total, nothing pending left

    objs_after = s3_client.list_objects_v2(Bucket=config.bucket, Prefix=f"{config.prefix}/content/")
    keys_after = {o["Key"] for o in objs_after.get("Contents", [])}
    assert keys_before == keys_after
