"""Orchestration: discovery -> content-addressed dedup -> upload loop.

Owns everything that spans state.py and uploader.py/S3 — reconciliation,
the single-instance lock, the per-sha256 dedup lock, and systemic-failure
classification all live here (architect review F2: state.py stays free of
any boto3/S3 semantics).
"""

from __future__ import annotations

import errno
import logging
import os
import threading
import zipfile
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from gphotos2s3 import content_date, uploader
from gphotos2s3 import metadata as metadata_mod
from gphotos2s3.config import Config
from gphotos2s3.discovery import UnsafePathError, discover_sources
from gphotos2s3.hashing import spool_and_hash
from gphotos2s3.state import FileRow, StateStore

logger = logging.getLogger("gphotos2s3")

DEFAULT_SYSTEMIC_THRESHOLD = 5

# Content-specific errors are about *this one file*, not the environment —
# excluded from systemic classification (round-4 hardening: the classifier
# is a denylist of exceptions known to be content-specific, not an allowlist
# of exceptions known to be systemic, so an unenumerated AWS error type
# still counts as systemic by default rather than silently resetting the
# streak).
_CONTENT_SPECIFIC_EXCEPTIONS = (zipfile.BadZipFile, UnsafePathError)


# --------------------------------------------------------------------------
# Single-instance lock (risk review H1)
# --------------------------------------------------------------------------


class LockHeldError(Exception):
    pass


class ProcessLock:
    """Atomic PID lock via O_CREAT|O_EXCL — not a check-then-write pair
    (round-2 hardening). A lock file left by a dead PID is reclaimed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._acquired = False

    def acquire(self) -> None:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            self._handle_existing()
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(str(os.getpid()))
        self._acquired = True

    def _handle_existing(self) -> None:
        try:
            existing_pid = int(self.path.read_text().strip())
        except (OSError, ValueError):
            self.path.unlink(missing_ok=True)
            return
        if _pid_alive(existing_pid):
            raise LockHeldError(
                f"another gphotos2s3 process (pid {existing_pid}) already holds the lock "
                f"at {self.path} — wait for it to finish, or remove the file if you're sure "
                "it's not actually running."
            )
        # Stale lock: dead PID, reclaim it.
        self.path.unlink(missing_ok=True)

    def release(self) -> None:
        if self._acquired:
            self.path.unlink(missing_ok=True)
            self._acquired = False

    def __enter__(self) -> ProcessLock:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    else:
        return True


# --------------------------------------------------------------------------
# Systemic-failure classification (risk review H3)
# --------------------------------------------------------------------------


@dataclass(slots=True)
class HaltSignal:
    triggered: bool = False
    message: str = ""


class SystemicFailureTracker:
    """Single locked counter. Increments on any exception NOT in the
    content-specific denylist; resets on any classified non-systemic
    (content-specific) failure or on a success. The halt check happens
    inside the same critical section as the increment, so the halt
    decision itself cannot race."""

    def __init__(self, threshold: int = DEFAULT_SYSTEMIC_THRESHOLD) -> None:
        self._threshold = threshold
        self._count = 0
        self._lock = threading.Lock()
        self.halt = HaltSignal()

    def record_success(self) -> None:
        with self._lock:
            self._count = 0

    def record_failure(self, exc: BaseException) -> bool:
        """Returns True if this call crossed the threshold (halt now)."""
        with self._lock:
            if isinstance(exc, _CONTENT_SPECIFIC_EXCEPTIONS):
                self._count = 0
                return False
            self._count += 1
            if self._count >= self._threshold and not self.halt.triggered:
                self.halt.triggered = True
                self.halt.message = (
                    f"Halting: {self._count} consecutive systemic failures "
                    f"(last: {type(exc).__name__}: {exc}). This looks like an "
                    "environment problem (network, disk, or credentials), not a "
                    "problem with individual files. Fix the underlying issue and "
                    "run `gphotos2s3 run` again — nothing has been lost."
                )
                return True
            return False


def is_content_specific(exc: BaseException) -> bool:
    return isinstance(exc, _CONTENT_SPECIFIC_EXCEPTIONS)


# --------------------------------------------------------------------------
# Per-sha256 dedup lock (efficiency optimization, not correctness-critical
# — risk review H2, re-scoped after the content-addressed redesign)
# --------------------------------------------------------------------------


class Sha256LockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._top_lock = threading.Lock()

    def get(self, sha256_hex: str) -> threading.Lock:
        with self._top_lock:
            lock = self._locks.get(sha256_hex)
            if lock is None:
                lock = threading.Lock()
                self._locks[sha256_hex] = lock
            return lock


# --------------------------------------------------------------------------
# Reconciliation (architect review F2 — orchestration, not state.py)
# --------------------------------------------------------------------------


def reconcile_stuck_rows(state: StateStore, s3_client: Any, bucket: str, prefix: str) -> int:
    """Any row left 'uploading' by a previous, non-clean-exited run is
    re-checked: content+pointer present with matching sha256 -> uploaded;
    otherwise -> pending, attempts untouched (being killed isn't the file's
    fault). Returns the number of rows reconciled.

    `content_key`/`pointer_key` are only ever persisted to a row on success
    (mark_uploaded) — a row stuck 'uploading' never had them written. They
    must therefore be RECOMPUTED here from the row's already-persisted
    sha256 + taken_at + zip/entry identity (the same pure functions
    process_one uses), not read off the row. sha256 and taken_at are both
    guaranteed present for any 'uploading' row: mark_hashed always commits
    both before mark_uploading does (a row from before the taken_at column
    existed has taken_at=NULL, handled by the legacy-key fallback below)."""
    reconciled = 0
    for row in list(state.iter_by_status("uploading")):
        if row.sha256 is None:
            state.reset_to_pending(row.id)
            reconciled += 1
            continue

        ext = uploader.guess_extension(row.entry_name)
        c_key = uploader.content_key(prefix, row.sha256, ext, row.taken_at)
        zip_basename = Path(row.zip_path).name
        try:
            p_key = uploader.pointer_key(
                prefix, zip_basename, row.entry_name, row.sha256, row.taken_at
            )
        except Exception:  # noqa: BLE001 - an unsafe entry can't have reached 'uploading'
            state.reset_to_pending(row.id)
            reconciled += 1
            continue

        content_ok = uploader.already_uploaded(s3_client, bucket, c_key, row.sha256)
        if not content_ok:
            # A row left 'uploading' by a pre-upgrade version has no
            # taken_at (NULL) and may have already uploaded its content
            # under the old flat key — check there before concluding "not
            # uploaded" (chronological-s3-layout plan §3.4b). Without this,
            # the very first run after upgrading would 404 on the new
            # unknown-date key, reset to pending, and re-upload the same
            # bytes under a second key — orphaning the original object and
            # reopening the round-2 dedup-race class this reconciliation
            # exists to prevent.
            legacy_key = f"{prefix}/content/{row.sha256}{ext}"
            if uploader.already_uploaded(s3_client, bucket, legacy_key, row.sha256):
                c_key = legacy_key
                content_ok = True
        pointer_ok = content_ok and uploader.already_uploaded(s3_client, bucket, p_key, row.sha256)
        if content_ok and pointer_ok:
            state.mark_uploaded(
                row.id,
                c_key,
                p_key,
                bucket,
                content_deduped=bool(row.content_deduped),
                metadata_key=row.metadata_key,
                metadata_status=row.metadata_status,
            )
        else:
            state.reset_to_pending(row.id)
        reconciled += 1
    return reconciled


# --------------------------------------------------------------------------
# Per-file processing
# --------------------------------------------------------------------------


class DiskSpaceError(Exception):
    pass


def _open_zip_entry_metadata(zip_path: str, sidecar_entry_name: str | None) -> dict[str, Any]:
    if sidecar_entry_name is None:
        return {}
    try:
        with zipfile.ZipFile(zip_path) as zf, zf.open(sidecar_entry_name) as fh:
            return metadata_mod.parse_sidecar(fh.read())
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        logger.warning("could not read sidecar %s: %s", sidecar_entry_name, exc)
        return {}


def process_one(
    row: FileRow,
    state: StateStore,
    s3_client: Any,
    config: Config,
    sha256_locks: Sha256LockRegistry,
) -> None:
    """Processes exactly one row end-to-end. Raises on failure so the
    caller (the worker-pool loop) can classify it via
    SystemicFailureTracker; never partially commits state."""
    zip_path = Path(row.zip_path)
    spooled = None
    try:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                spooled, sha256_hex, size = spool_and_hash(zf, row.entry_name)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise DiskSpaceError(str(exc)) from exc
            raise

        ext = uploader.guess_extension(row.entry_name)
        # Pure function of these same spooled bytes (content_date module
        # docstring) — computed once here and reused at every key-building
        # call site below, never re-derived independently (chronological-
        # s3-layout plan §3.4, risk-analyst Low finding).
        taken_at_dt = content_date.extract_taken_at(spooled, ext)
        taken_at = taken_at_dt.isoformat() if taken_at_dt is not None else None

        state.mark_hashed(row.id, sha256_hex, size, taken_at)
        state.mark_uploading(row.id)

        zip_basename = zip_path.name
        # Canonical-key reuse (plan §3.4a): if this content already has a
        # successful upload recorded locally, reuse its content_key rather
        # than recomputing one from this row's own taken_at. Within one run
        # this is a no-op (extract_taken_at is a pure function of the same
        # bytes, so a fresh computation would agree anyway) — it matters
        # across time: if content_date.py's logic ever changes between
        # runs, a duplicate row discovered later must still land on the
        # already-recorded key, not a possibly-different fresh one. Residual,
        # accepted: this can't help if the local state DB itself was lost
        # *and* the code changed in between — a narrower version of the
        # already-accepted "full state-DB loss" scenario, not a new risk.
        existing = state.find_uploaded_by_sha256(sha256_hex)
        if existing is not None and existing.content_key:
            c_key = existing.content_key
        else:
            c_key = uploader.content_key(config.prefix, sha256_hex, ext, taken_at)
        p_key = uploader.pointer_key(
            config.prefix, zip_basename, row.entry_name, sha256_hex, taken_at
        )

        sha_lock = sha256_locks.get(sha256_hex)
        with sha_lock:
            transferred = uploader.upload_content_if_missing(
                s3_client, config.bucket, c_key, spooled, sha256_hex, config.storage_class
            )
        content_deduped = not transferred

        uploader.upload_pointer(s3_client, config.bucket, p_key, c_key, sha256_hex, size)

        m_key = None
        metadata_status = "not_found"
        if row.sidecar_entry_name:
            m_key = uploader.metadata_key(
                config.prefix, zip_basename, row.entry_name, sha256_hex, taken_at
            )
            metadata_dict = _open_zip_entry_metadata(row.zip_path, row.sidecar_entry_name)
            if metadata_dict:
                try:
                    uploader.upload_metadata(
                        s3_client, config.bucket, m_key, sha256_hex, metadata_dict
                    )
                    metadata_status = "uploaded"
                except ClientError:
                    metadata_status = "failed"
                    raise
            else:
                metadata_status = "not_found"
                m_key = None

        state.mark_uploaded(
            row.id,
            c_key,
            p_key,
            config.bucket,
            content_deduped=content_deduped,
            metadata_key=m_key,
            metadata_status=metadata_status,
        )
    finally:
        if spooled is not None:
            spooled.close()


# --------------------------------------------------------------------------
# Bounded incremental worker pool with halt propagation (risk review H3)
# --------------------------------------------------------------------------


@dataclass(slots=True)
class RunSummary:
    uploaded: int = 0
    deduped: int = 0
    failed: int = 0
    bytes_uploaded: int = 0
    bytes_deduped: int = 0
    halted: bool = False
    halt_message: str = ""
    discovery_errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.discovery_errors is None:
            self.discovery_errors = []


def run_pipeline(
    state: StateStore,
    s3_client: Any,
    config: Config,
    zip_paths: list[Path],
    *,
    threshold: int = DEFAULT_SYSTEMIC_THRESHOLD,
    on_progress: Callable[[FileRow], None] | None = None,
) -> RunSummary:
    """Discovery, then the upload loop. `state` is shared across worker
    threads — StateStore opens one connection per thread internally."""
    summary = RunSummary()

    errors = discover_sources(zip_paths, state)
    summary.discovery_errors = [f"{e.source}: {e.message}" for e in errors]

    reconcile_stuck_rows(state, s3_client, config.bucket, config.prefix)

    tracker = SystemicFailureTracker(threshold=threshold)
    sha256_locks = Sha256LockRegistry()
    halt_event = threading.Event()

    pending_ids = [row.id for row in state.iter_by_status("pending")]

    def worker(row_id: str) -> None:
        row = state.get(row_id)
        if row is None:
            return
        try:
            process_one(row, state, s3_client, config, sha256_locks)
        except _CONTENT_SPECIFIC_EXCEPTIONS as exc:
            tracker.record_failure(exc)
            state.mark_failed(row.id, str(exc), increment_attempts=True)
        except Exception as exc:  # noqa: BLE001 - classify, never crash the pool
            crossed = tracker.record_failure(exc)
            if halt_event.is_set():
                # Already halted, or crossing now: this row is a spared
                # streak member, not an ordinary failure (round-4, Finding 3).
                state.reset_to_pending(row.id)
                if crossed:
                    halt_event.set()
                return
            if crossed:
                halt_event.set()
                state.reset_to_pending(row.id)
                return
            state.mark_failed(row.id, str(exc), increment_attempts=True)
        else:
            tracker.record_success()
            if on_progress is not None:
                updated = state.get(row_id)
                if updated is not None:
                    on_progress(updated)

    with ThreadPoolExecutor(max_workers=max(1, config.workers)) as executor:
        in_flight = {}
        it = iter(pending_ids)

        def submit_next() -> bool:
            if halt_event.is_set():
                return False
            row_id = next(it, None)
            if row_id is None:
                return False
            future = executor.submit(worker, row_id)
            in_flight[future] = row_id
            return True

        for _ in range(max(1, config.workers)):
            if not submit_next():
                break

        while in_flight:
            finished, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in finished:
                in_flight.pop(future, None)
                future.result()  # propagate unexpected bugs loudly in tests
                submit_next()

    summary.halted = tracker.halt.triggered
    summary.halt_message = tracker.halt.message

    counts = state.count_by_status()
    summary.uploaded = counts.get("uploaded", 0)
    summary.failed = counts.get("failed", 0)
    return summary
