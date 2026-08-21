from __future__ import annotations

import os
from pathlib import Path

import pytest

from gphotos2s3.pipeline import LockHeldError, ProcessLock


def test_acquire_and_release(tmp_path: Path):
    lock_path = tmp_path / "gphotos2s3.lock"
    lock = ProcessLock(lock_path)
    lock.acquire()
    assert lock_path.exists()
    lock.release()
    assert not lock_path.exists()


def test_second_instance_refuses_while_live_pid_holds_lock(tmp_path: Path):
    lock_path = tmp_path / "gphotos2s3.lock"
    lock1 = ProcessLock(lock_path)
    lock1.acquire()
    try:
        lock2 = ProcessLock(lock_path)
        with pytest.raises(LockHeldError):
            lock2.acquire()
    finally:
        lock1.release()


def test_stale_lock_from_dead_pid_is_reclaimed(tmp_path: Path):
    lock_path = tmp_path / "gphotos2s3.lock"
    # A PID that (almost certainly) doesn't exist.
    dead_pid = 999999
    lock_path.write_text(str(dead_pid))

    lock = ProcessLock(lock_path)
    lock.acquire()  # should reclaim, not raise
    assert lock_path.read_text().strip() == str(os.getpid())
    lock.release()


def test_context_manager_releases_on_exit(tmp_path: Path):
    lock_path = tmp_path / "gphotos2s3.lock"
    with ProcessLock(lock_path):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_acquisition_uses_atomic_create_exclusive(tmp_path: Path, monkeypatch):
    """Round-2 hardening: acquisition must be O_CREAT|O_EXCL, not a
    check-then-write pair."""
    lock_path = tmp_path / "gphotos2s3.lock"
    calls = []
    real_open = os.open

    def spy_open(path, flags, *args, **kwargs):
        calls.append(flags)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy_open)
    lock = ProcessLock(lock_path)
    lock.acquire()
    lock.release()

    assert any(flags & os.O_EXCL for flags in calls)
