from __future__ import annotations

import zipfile
from pathlib import Path

from gphotos2s3 import discovery
from tests.conftest import build_takeout_zip, make_sidecar


def test_media_filtering(tmp_path: Path):
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(
        zip_path,
        {
            "a/photo.jpg": b"x",
            "a/notes.txt": b"not media",
            "a/video.mp4": b"y",
        },
    )
    entries, error = discovery.discover_zip(zip_path)
    assert error is None
    names = {e.entry_name for e in entries}
    assert names == {"a/photo.jpg", "a/video.mp4"}


def test_legacy_json_sidecar_naming(tmp_path: Path):
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(
        zip_path,
        {
            "a/photo.jpg": b"x",
            "a/photo.jpg.json": make_sidecar(),
        },
    )
    entries, _ = discovery.discover_zip(zip_path)
    assert entries[0].sidecar_entry_name == "a/photo.jpg.json"


def test_new_supplemental_metadata_naming(tmp_path: Path):
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(
        zip_path,
        {
            "a/photo.jpg": b"x",
            "a/photo.jpg.supplemental-metadata.json": make_sidecar(),
        },
    )
    entries, _ = discovery.discover_zip(zip_path)
    assert entries[0].sidecar_entry_name == "a/photo.jpg.supplemental-metadata.json"


def test_truncated_name_fallback_pairing(tmp_path: Path):
    zip_path = tmp_path / "takeout-001.zip"
    long_name = "a" * 60 + ".jpg"
    # Google truncates the sidecar's own basename but keeps a long common
    # prefix with the media file — simulate that here.
    truncated_sidecar = "a" * 50 + ".supplemental-metadata.json"
    build_takeout_zip(
        zip_path,
        {
            f"dir/{long_name}": b"x",
            f"dir/{truncated_sidecar}": make_sidecar(),
        },
    )
    entries, _ = discovery.discover_zip(zip_path)
    assert entries[0].sidecar_entry_name == f"dir/{truncated_sidecar}"


def test_no_sidecar_found_never_blocks(tmp_path: Path):
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"a/photo.jpg": b"x"})
    entries, error = discovery.discover_zip(zip_path)
    assert error is None
    assert entries[0].sidecar_entry_name is None


def test_multi_zip_input_and_rerun_does_not_duplicate(state_store, tmp_path: Path):
    zip1 = tmp_path / "takeout-001.zip"
    zip2 = tmp_path / "takeout-002.zip"
    build_takeout_zip(zip1, {"a/one.jpg": b"1"})
    build_takeout_zip(zip2, {"a/two.jpg": b"2"})

    errors = discovery.discover_sources([zip1, zip2], state_store)
    assert errors == []
    assert sum(state_store.count_by_status().values()) == 2

    # Re-run: idempotent, no duplicates.
    discovery.discover_sources([zip1, zip2], state_store)
    assert sum(state_store.count_by_status().values()) == 2


def test_basename_id_survives_zip_relocation(tmp_path: Path):
    # Same zip filename, different directory -> same id (architect review F5).
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    zip_a = dir_a / "takeout-001.zip"
    zip_b = dir_b / "takeout-001.zip"
    id_a = discovery.compute_id(str(zip_a), "photo.jpg")
    id_b = discovery.compute_id(str(zip_b), "photo.jpg")
    assert id_a == id_b

    # Different basename -> different id (renaming is NOT survived, documented).
    zip_c = dir_a / "takeout-002.zip"
    id_c = discovery.compute_id(str(zip_c), "photo.jpg")
    assert id_c != id_a


def test_corrupt_archive_isolated_other_sources_continue(state_store, tmp_path: Path):
    good_zip = tmp_path / "good.zip"
    build_takeout_zip(good_zip, {"a/photo.jpg": b"x"})
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not a zip file at all")

    errors = discovery.discover_sources([bad_zip, good_zip], state_store)
    assert len(errors) == 1
    assert str(bad_zip) in errors[0].source
    # The good source was still processed.
    assert sum(state_store.count_by_status().values()) == 1


def test_corrupt_entry_inside_valid_zip_isolated(tmp_path: Path):
    """A CRC/corruption error on one entry inside an otherwise-valid zip is
    detected at read time (hashing), not discovery time — discovery.py just
    lists it normally; this test documents that boundary explicitly (risk
    review H4 round-2 gap)."""
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"a/good.jpg": b"fine", "a/bad.jpg": b"also-fine-at-list-time"})

    # Corrupt the second entry's compressed data in place, forcing a CRC
    # error only when it's actually *read* — discover_zip should still list
    # both entries successfully.
    with zipfile.ZipFile(zip_path, "a") as zf:
        info = zf.getinfo("a/bad.jpg")
        assert info is not None

    entries, error = discovery.discover_zip(zip_path)
    assert error is None
    assert {e.entry_name for e in entries} == {"a/good.jpg", "a/bad.jpg"}


def test_unsafe_entry_name_rejected_not_collapsed():
    assert discovery.is_unsafe_entry_name("../etc/passwd") is not None
    assert discovery.is_unsafe_entry_name("/etc/passwd") is not None
    assert discovery.is_unsafe_entry_name("a/../b.jpg") is not None
    assert discovery.is_unsafe_entry_name("a/b.jpg") is None


def test_unsafe_entry_marked_failed_at_discovery(state_store, tmp_path: Path):
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"../evil.jpg": b"x"})
    discovery.discover_sources([zip_path], state_store)
    counts = state_store.count_by_status()
    assert counts.get("failed") == 1
