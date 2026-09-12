"""SQLite state store — the external memory that makes a run resumable.

No boto3/S3 imports live here (architect review finding F2): this module
owns persistence only. Reconciling local state against what actually exists
in S3 is an orchestration concern that belongs to pipeline.py.
"""

from __future__ import annotations

import datetime
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 2

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id              TEXT PRIMARY KEY,
    zip_path        TEXT NOT NULL,
    entry_name      TEXT NOT NULL,
    sidecar_entry_name TEXT,
    size_bytes      INTEGER NOT NULL,
    sha256          TEXT,
    taken_at        TEXT,               -- capture date embedded in the file's own bytes
                                         -- (content_date.extract_taken_at); NULL if none
                                         -- found. Persisted at mark_hashed time so
                                         -- reconcile_stuck_rows never needs to reopen the
                                         -- zip to recompute content_key (schema v2).
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
);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    files_uploaded INTEGER DEFAULT 0,
    files_deduped INTEGER DEFAULT 0,
    files_failed INTEGER DEFAULT 0,
    bytes_uploaded INTEGER DEFAULT 0,
    bytes_deduped INTEGER DEFAULT 0
);
"""

# Valid values for files.status / files.metadata_status — enforced in code
# (application-level, not a SQL CHECK constraint) so a future value can be
# added via the migration mechanism without a destructive schema change.
STATUS_VALUES = {"pending", "uploading", "uploaded", "failed", "verify_failed"}
METADATA_STATUS_VALUES = {"not_found", "pending", "uploaded", "failed"}


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass(slots=True)
class FileRow:
    id: str
    zip_path: str
    entry_name: str
    sidecar_entry_name: str | None
    size_bytes: int
    sha256: str | None
    taken_at: str | None
    status: str
    metadata_status: str
    content_key: str | None
    pointer_key: str | None
    metadata_key: str | None
    s3_bucket: str | None
    content_deduped: bool
    error: str | None
    attempts: int
    discovered_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> FileRow:
        return cls(
            id=row["id"],
            zip_path=row["zip_path"],
            entry_name=row["entry_name"],
            sidecar_entry_name=row["sidecar_entry_name"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            taken_at=row["taken_at"],
            status=row["status"],
            metadata_status=row["metadata_status"],
            content_key=row["content_key"],
            pointer_key=row["pointer_key"],
            metadata_key=row["metadata_key"],
            s3_bucket=row["s3_bucket"],
            content_deduped=bool(row["content_deduped"]),
            error=row["error"],
            attempts=row["attempts"],
            discovered_at=row["discovered_at"],
            updated_at=row["updated_at"],
        )


class StateStore:
    """One instance per thread (architect review F3): SQLite connections are
    not shared across threads in this design. WAL mode + a generous
    busy_timeout is the standard, correct answer for several threads doing
    frequent short writes — no bespoke writer-queue needed."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def init_schema(self) -> None:
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        """Migration runner (architect review F8): checks
        schema_meta['version'] on every open and applies any pending
        numbered migration in order, so a schema change never forces
        'delete your state DB and lose all resume progress'.

        v1->v2 (chronological-s3-layout plan §3.2) adds `files.taken_at`.
        This is the first migration this codebase has ever actually had to
        run (v1 had no predecessor). `status`/`verify`/`retry-failed` open
        the state DB without the single-instance `ProcessLock` that `run`
        takes, so two processes could open the same v1 DB at once and both
        reach the `ALTER TABLE` below — SQLite's own per-statement locking
        (governed by `busy_timeout`, already set in `_connect`) serializes
        them regardless: the loser blocks until the winner's ALTER commits,
        then runs its own ALTER against the now-migrated schema and hits
        'duplicate column', which is caught below as an already-applied
        no-op — the same catch that makes this method a harmless repeat for
        a brand-new DB too (`_SCHEMA_SQL` already creates `taken_at`
        directly there, so its ALTER always hits this exact path)."""
        cur = self.conn.execute("SELECT value FROM schema_meta WHERE key = 'version'")
        row = cur.fetchone()
        current = int(row["value"]) if row else 0
        if current >= SCHEMA_VERSION:
            return
        if current < 2:
            try:
                self.conn.execute("ALTER TABLE files ADD COLUMN taken_at TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise
            current = 2
        # Future migrations: `if current < 3: ...` before the version write.
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
            (str(current),),
        )
        self.conn.commit()

    # -- discovery -----------------------------------------------------

    def insert_discovered(
        self,
        id_: str,
        zip_path: str,
        entry_name: str,
        size_bytes: int,
        sidecar_entry_name: str | None = None,
    ) -> bool:
        """Idempotent by construction: INSERT OR IGNORE keyed on `id`. Safe
        to call repeatedly across re-runs and additional --source entries.
        Returns True if a new row was actually inserted."""
        now = _utcnow()
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO files "
            "(id, zip_path, entry_name, sidecar_entry_name, size_bytes, discovered_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id_, zip_path, entry_name, sidecar_entry_name, size_bytes, now, now),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # -- reads -----------------------------------------------------------

    def get(self, id_: str) -> FileRow | None:
        row = self.conn.execute("SELECT * FROM files WHERE id = ?", (id_,)).fetchone()
        return FileRow.from_row(row) if row else None

    def iter_by_status(self, *statuses: str) -> Iterator[FileRow]:
        placeholders = ",".join("?" for _ in statuses)
        cur = self.conn.execute(
            f"SELECT * FROM files WHERE status IN ({placeholders}) ORDER BY discovered_at",
            statuses,
        )
        for row in cur:
            yield FileRow.from_row(row)

    def count_by_status(self) -> dict[str, int]:
        cur = self.conn.execute("SELECT status, COUNT(*) AS n FROM files GROUP BY status")
        return {row["status"]: row["n"] for row in cur}

    def find_uploaded_by_sha256(self, sha256: str) -> FileRow | None:
        row = self.conn.execute(
            "SELECT * FROM files WHERE sha256 = ? AND status = 'uploaded' LIMIT 1",
            (sha256,),
        ).fetchone()
        return FileRow.from_row(row) if row else None

    # -- status transitions (each is its own immediate commit — crash-safety
    #    depends on never batching these, per research.md §4) ---------------

    def mark_hashed(
        self, id_: str, sha256: str, size_bytes: int, taken_at: str | None = None
    ) -> None:
        """`taken_at` (content_date.extract_taken_at's result, an ISO-8601
        string or None) is persisted here — before `mark_uploading` ever
        runs — so reconcile_stuck_rows can recompute the exact same
        content_key a crashed row would have used without reopening the
        zip (chronological-s3-layout plan §3.2)."""
        self.conn.execute(
            "UPDATE files SET sha256 = ?, size_bytes = ?, taken_at = ?, updated_at = ? "
            "WHERE id = ?",
            (sha256, size_bytes, taken_at, _utcnow(), id_),
        )
        self.conn.commit()

    def mark_uploading(self, id_: str) -> None:
        self.conn.execute(
            "UPDATE files SET status = 'uploading', updated_at = ? WHERE id = ?",
            (_utcnow(), id_),
        )
        self.conn.commit()

    def mark_uploaded(
        self,
        id_: str,
        content_key: str,
        pointer_key: str,
        s3_bucket: str,
        content_deduped: bool,
        metadata_key: str | None = None,
        metadata_status: str = "not_found",
    ) -> None:
        self.conn.execute(
            "UPDATE files SET status = 'uploaded', content_key = ?, pointer_key = ?, "
            "metadata_key = ?, metadata_status = ?, s3_bucket = ?, content_deduped = ?, "
            "error = NULL, updated_at = ? WHERE id = ?",
            (
                content_key,
                pointer_key,
                metadata_key,
                metadata_status,
                s3_bucket,
                int(content_deduped),
                _utcnow(),
                id_,
            ),
        )
        self.conn.commit()

    def mark_metadata_status(
        self, id_: str, metadata_status: str, metadata_key: str | None
    ) -> None:
        self.conn.execute(
            "UPDATE files SET metadata_status = ?, metadata_key = ?, updated_at = ? WHERE id = ?",
            (metadata_status, metadata_key, _utcnow(), id_),
        )
        self.conn.commit()

    def mark_failed(self, id_: str, error: str, *, increment_attempts: bool) -> None:
        if increment_attempts:
            self.conn.execute(
                "UPDATE files SET status = 'failed', error = ?, attempts = attempts + 1, "
                "updated_at = ? WHERE id = ?",
                (error, _utcnow(), id_),
            )
        else:
            self.conn.execute(
                "UPDATE files SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
                (error, _utcnow(), id_),
            )
        self.conn.commit()

    def mark_verify_failed(self, id_: str, error: str) -> None:
        self.conn.execute(
            "UPDATE files SET status = 'verify_failed', error = ?, updated_at = ? WHERE id = ?",
            (error, _utcnow(), id_),
        )
        self.conn.commit()

    def reset_to_pending(self, id_: str, *, keep_attempts: bool = True) -> None:
        """Used by reconciliation (uploading -> pending) and by the
        systemic-halt path (spared streak members -> pending, attempts
        untouched). keep_attempts=True never touches the attempts counter —
        being interrupted, or caught in a systemic outage, isn't the file's
        fault (§4/§6 of the plan)."""
        del keep_attempts  # always kept; parameter documents intent at call sites
        self.conn.execute(
            "UPDATE files SET status = 'pending', error = NULL, updated_at = ? WHERE id = ?",
            (_utcnow(), id_),
        )
        self.conn.commit()

    def reset_failed_for_retry(self, max_attempts: int) -> int:
        """Used by `retry-failed`: resets 'failed' and 'verify_failed' rows
        below max_attempts back to 'pending'. Returns the count reset."""
        cur = self.conn.execute(
            "UPDATE files SET status = 'pending', error = NULL, updated_at = ? "
            "WHERE status IN ('failed', 'verify_failed') AND attempts < ?",
            (_utcnow(), max_attempts),
        )
        self.conn.commit()
        return cur.rowcount

    # -- run_log -----------------------------------------------------------

    def start_run(self) -> int:
        cur = self.conn.execute("INSERT INTO run_log (started_at) VALUES (?)", (_utcnow(),))
        self.conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def finish_run(
        self,
        run_id: int,
        files_uploaded: int,
        files_deduped: int,
        files_failed: int,
        bytes_uploaded: int,
        bytes_deduped: int,
    ) -> None:
        self.conn.execute(
            "UPDATE run_log SET ended_at = ?, files_uploaded = ?, files_deduped = ?, "
            "files_failed = ?, bytes_uploaded = ?, bytes_deduped = ? WHERE id = ?",
            (
                _utcnow(),
                files_uploaded,
                files_deduped,
                files_failed,
                bytes_uploaded,
                bytes_deduped,
                run_id,
            ),
        )
        self.conn.commit()


@contextmanager
def open_state(db_path: Path) -> Iterator[StateStore]:
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    store = StateStore(db_path)
    store.init_schema()
    try:
        yield store
    finally:
        store.close()
