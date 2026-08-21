"""H3 (risk review): systemic-failure classification, thread safety, and
the round-4 hardening (denylist not allowlist; mixed-subtype accumulation;
precise attempts semantics; halt propagation to in-flight workers).
"""

from __future__ import annotations

import threading
import zipfile

from botocore.exceptions import ClientError, EndpointConnectionError

from gphotos2s3 import pipeline
from gphotos2s3.discovery import discover_sources
from gphotos2s3.pipeline import SystemicFailureTracker
from tests.conftest import build_takeout_zip


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "PutObject")


def test_content_specific_error_does_not_count_as_systemic():
    tracker = SystemicFailureTracker(threshold=3)
    for _ in range(10):
        crossed = tracker.record_failure(zipfile.BadZipFile("bad crc"))
        assert crossed is False
    assert tracker.halt.triggered is False


def test_denylist_not_allowlist_unenumerated_error_still_systemic():
    """Round-4 hardening: an error type NOT in any explicit list must still
    count as systemic by default (denylist design), not silently reset."""

    class SomeUnenumeratedBotoError(Exception):
        pass

    tracker = SystemicFailureTracker(threshold=3)
    crossed = False
    for _ in range(3):
        crossed = tracker.record_failure(SomeUnenumeratedBotoError("weird"))
    assert crossed is True
    assert tracker.halt.triggered is True


def test_mixed_subtype_streak_still_halts():
    """Round-4 fix (Finding 2): alternating error subtypes must still
    accumulate on the same aggregate counter, not reset each time."""
    tracker = SystemicFailureTracker(threshold=4)
    errors = [
        EndpointConnectionError(endpoint_url="https://s3.amazonaws.com"),
        _client_error("AccessDenied"),
        EndpointConnectionError(endpoint_url="https://s3.amazonaws.com"),
        _client_error("AccessDenied"),
    ]
    crossed = False
    for exc in errors:
        crossed = tracker.record_failure(exc)
    assert crossed is True


def test_success_resets_counter():
    tracker = SystemicFailureTracker(threshold=3)
    tracker.record_failure(_client_error("SlowDown"))
    tracker.record_failure(_client_error("SlowDown"))
    tracker.record_success()
    crossed = tracker.record_failure(_client_error("SlowDown"))
    assert crossed is False  # counter was reset, this is only #1 again


def test_thread_safe_increment_no_lost_or_doubled_counts():
    tracker = SystemicFailureTracker(threshold=1_000_000)  # never trips
    n_threads = 16
    per_thread = 50

    def worker():
        for _ in range(per_thread):
            tracker.record_failure(_client_error("SlowDown"))

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert tracker._count == n_threads * per_thread  # noqa: SLF001


def test_pipeline_halts_and_spares_untouched_pending_rows(
    s3_client, state_store, config, tmp_path, monkeypatch
):
    """Integration: a systemic condition (every upload fails the same way)
    halts the run; rows never dispatched keep attempts untouched."""
    config.workers = 1  # deterministic attempts semantics for this assertion
    zip_path = tmp_path / "takeout-001.zip"
    entries = {f"a/photo{i}.jpg": f"content-{i}".encode() for i in range(10)}
    build_takeout_zip(zip_path, entries)
    discover_sources([zip_path], state_store)

    def always_fail(*args, **kwargs):
        raise _client_error("InternalError")

    monkeypatch.setattr(pipeline.uploader, "upload_content_if_missing", always_fail)

    summary = pipeline.run_pipeline(state_store, s3_client, config, [zip_path], threshold=3)
    assert summary.halted is True
    assert "systemic" in summary.halt_message.lower() or "Halting" in summary.halt_message

    counts = state_store.count_by_status()
    # threshold=3: rows 1-2 fail normally (attempts incremented), row 3
    # crosses the threshold and halts; everything else stays pending.
    assert counts.get("failed", 0) <= 3
    assert counts.get("pending", 0) >= 6

    for row in state_store.iter_by_status("pending"):
        assert row.attempts == 0
