"""Non-secret configuration: config.json load/save, defaults.

Secrets never live here (see aws_credentials.py) — only bucket, prefix,
region, storage class, and behavioral defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".gphotos2s3"
DEFAULT_STORAGE_CLASS = "GLACIER_IR"
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_WORKERS = 4
DEFAULT_SYSTEMIC_FAILURE_THRESHOLD = 5


@dataclass(slots=True)
class Config:
    bucket: str
    region: str
    aws_profile: str
    prefix: str = "gphotos2s3"
    storage_class: str = DEFAULT_STORAGE_CLASS
    dedupe: bool = True
    workers: int = DEFAULT_WORKERS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    sources: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Config:
        data = json.loads(path.read_text())
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(asdict(self), fh, indent=2)


def config_path(state_dir: Path) -> Path:
    return state_dir / "config.json"


def db_path(state_dir: Path) -> Path:
    return state_dir / "state.db"


def lock_path(state_dir: Path) -> Path:
    return state_dir / "gphotos2s3.lock"
