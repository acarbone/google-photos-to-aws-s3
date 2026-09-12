from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from gphotos2s3.state import open_state


def test_insert_discovered_idempotent(state_store):
    assert state_store.insert_discovered("id1", "z.zip", "a.jpg", 100) is True
    assert state_store.insert_discovered("id1", "z.zip", "a.jpg", 100) is False
    assert sum(state_store.count_by_status().values()) == 1


def test_status_transitions(state_store):
    state_store.insert_discovered("id1", "z.zip", "a.jpg", 100)
    state_store.mark_hashed("id1", "sha-abc", 100)
    state_store.mark_uploading("id1")
    row = state_store.get("id1")
    assert row.status == "uploading"
    assert row.sha256 == "sha-abc"

    state_store.mark_uploaded(
        "id1",
        "content/sha-abc.jpg",
        "library/z.zip/a.jpg.pointer.json",
        "bucket",
        content_deduped=False,
        metadata_key=None,
        metadata_status="not_found",
    )
    row = state_store.get("id1")
    assert row.status == "uploaded"
    assert row.content_key == "content/sha-abc.jpg"
    assert row.metadata_status == "not_found"


def test_metadata_status_independent_of_status(state_store):
    state_store.insert_discovered("id1", "z.zip", "a.jpg", 100)
    state_store.mark_hashed("id1", "sha-abc", 100)
    state_store.mark_uploaded(
        "id1",
        "content/x",
        "pointer/x",
        "bucket",
        content_deduped=False,
        metadata_key="meta/x",
        metadata_status="uploaded",
    )
    row = state_store.get("id1")
    assert row.status == "uploaded"
    assert row.metadata_status == "uploaded"

    # Metadata can independently be marked failed without touching status.
    state_store.mark_metadata_status("id1", "failed", None)
    row = state_store.get("id1")
    assert row.status == "uploaded"
    assert row.metadata_status == "failed"


def test_verify_failed_status(state_store):
    state_store.insert_discovered("id1", "z.zip", "a.jpg", 100)
    state_store.mark_verify_failed("id1", "checksum mismatch")
    row = state_store.get("id1")
    assert row.status == "verify_failed"
    assert row.error == "checksum mismatch"


def test_reset_failed_for_retry_respects_max_attempts(state_store):
    state_store.insert_discovered("id1", "z.zip", "a.jpg", 100)
    state_store.mark_failed("id1", "boom", increment_attempts=True)
    state_store.insert_discovered("id2", "z.zip", "b.jpg", 100)
    for _ in range(5):
        state_store.mark_failed("id2", "boom", increment_attempts=True)

    n = state_store.reset_failed_for_retry(max_attempts=5)
    assert n == 1  # id2 has attempts == 5, not < 5, so excluded
    assert state_store.get("id1").status == "pending"
    assert state_store.get("id2").status == "failed"


def test_reset_to_pending_never_touches_attempts(state_store):
    state_store.insert_discovered("id1", "z.zip", "a.jpg", 100)
    state_store.mark_failed("id1", "boom", increment_attempts=True)
    assert state_store.get("id1").attempts == 1
    state_store.reset_to_pending("id1")
    row = state_store.get("id1")
    assert row.status == "pending"
    assert row.attempts == 1  # untouched


def test_schema_migration_no_op(state_dir):
    with open_state(state_dir / "state.db") as store:
        cur = store.conn.execute("SELECT value FROM schema_meta WHERE key = 'version'")
        assert cur.fetchone()["value"] == "2"
    # Re-opening is a no-op, doesn't error or duplicate.
    with open_state(state_dir / "state.db") as store:
        cur = store.conn.execute("SELECT COUNT(*) AS n FROM schema_meta WHERE key = 'version'")
        assert cur.fetchone()["n"] == 1


def _create_legacy_v1_db(path: Path) -> None:
    """Simulates a pre-migration v1 database on disk: the `files` table
    without a `taken_at` column, `schema_meta` pinned at version 1, and one
    already-discovered row — the shape a real user's state DB has right
    before upgrading to the chronological-s3-layout schema (§3.2)."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE files (
            id              TEXT PRIMARY KEY,
            zip_path        TEXT NOT NULL,
            entry_name      TEXT NOT NULL,
            sidecar_entry_name TEXT,
            size_bytes      INTEGER NOT NULL,
            sha256          TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            metadata_status TEXT NOT NULL DEFAULT 'not_found',
            content_key     TEXT,
            pointer_key     TEXT,
            metadata_key    TEXT,
            s3_bucket       TEXT,
            content_deduped INTEGER NOT NULL DEFAULT 0,
            error           TEXT,
            attempts        INTEGER NOT NULL DEFAULT 0,
            discovered_at   TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO schema_meta (key, value) VALUES ('version', '1')")
    conn.execute(
        "INSERT INTO files (id, zip_path, entry_name, size_bytes, discovered_at, updated_at) "
        "VALUES ('id1', 'z.zip', 'a.jpg', 100, 'now', 'now')"
    )
    conn.commit()
    conn.close()


def test_schema_migration_v1_to_v2_adds_taken_at_preserves_rows(state_dir):
    db_path = state_dir / "state.db"
    _create_legacy_v1_db(db_path)

    with open_state(db_path) as store:
        cur = store.conn.execute("SELECT value FROM schema_meta WHERE key = 'version'")
        assert cur.fetchone()["value"] == "2"
        row = store.get("id1")
        assert row is not None
        assert row.taken_at is None  # pre-existing row: column added as NULL
        assert row.zip_path == "z.zip"  # data preserved, not wiped


def test_schema_migration_race_two_processes_on_same_v1_db(state_dir):
    """Two connections opening the same v1 DB at once must not crash with
    'duplicate column name' — status/verify/retry-failed open the state DB
    without the single-instance ProcessLock `run` takes (chronological-
    s3-layout plan §3.2, risk-analyst High finding)."""
    db_path = state_dir / "state.db"
    _create_legacy_v1_db(db_path)

    errors: list[Exception] = []

    def opener() -> None:
        try:
            with open_state(db_path) as store:
                store.get("id1")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=opener) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    with open_state(db_path) as store:
        cur = store.conn.execute("SELECT value FROM schema_meta WHERE key = 'version'")
        assert cur.fetchone()["value"] == "2"


def test_concurrency_no_lost_writes_or_locking_errors(state_dir):
    """N threads writing distinct rows under WAL mode: no 'database is
    locked' errors and no lost writes (architect review F3)."""
    with open_state(state_dir / "state.db") as store:
        n_threads = 8
        rows_per_thread = 20
        errors: list[Exception] = []

        def worker(thread_idx: int) -> None:
            try:
                for i in range(rows_per_thread):
                    row_id = f"t{thread_idx}-{i}"
                    store.insert_discovered(row_id, "z.zip", row_id, 10)
                    store.mark_hashed(row_id, f"sha-{row_id}", 10)
                    store.mark_uploading(row_id)
                    store.mark_uploaded(
                        row_id,
                        f"content/{row_id}",
                        f"pointer/{row_id}",
                        "bucket",
                        content_deduped=False,
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        counts = store.count_by_status()
        assert counts.get("uploaded") == n_threads * rows_per_thread
