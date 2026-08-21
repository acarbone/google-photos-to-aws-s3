"""Read/write a named profile in the standard ~/.aws/credentials file.

Deliberately NOT a bespoke secret store (research.md §5): persisting into
the location every other AWS SDK/CLI tool and every credential-hygiene
scanner already knows to look for is safer for a distributable open-source
tool than inventing our own. Writes are read-merge-write (architect review
F4) — every other profile in the file is preserved.
"""

from __future__ import annotations

import configparser
import getpass
import os
import stat
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

DEFAULT_CREDENTIALS_PATH = Path.home() / ".aws" / "credentials"

_RETRY_CONFIG = BotoConfig(retries={"mode": "adaptive", "max_attempts": 10})


def default_profile_name(state_dir: Path) -> str:
    """Profile name is parameterized per --state-dir instance (architect
    review F9), not a single hardcoded name — two independent instances
    (e.g. two Google accounts, two buckets) no longer default to silently
    overwriting each other's credentials on --reconfigure."""
    return f"gphotos2s3-{state_dir.resolve().name}"


def prompt_for_credentials() -> tuple[str, str]:
    """Collects Access Key ID via plain input(), Secret Access Key via
    getpass.getpass() — no-echo entry (risk review H5). The target audience
    is non-technical and may be following a screen-recorded tutorial or
    pasting terminal output into a support chat; plain-echo secret entry is
    a realistic leak vector for that audience."""
    access_key_id = input("AWS Access Key ID: ").strip()
    secret_access_key = getpass.getpass("AWS Secret Access Key (hidden): ").strip()
    return access_key_id, secret_access_key


def write_credentials(
    profile: str,
    access_key_id: str,
    secret_access_key: str,
    credentials_path: Path | None = None,
) -> None:
    """Read-merge-write: parses the existing file, updates only `profile`'s
    section, and preserves every other section's data (not a literal
    byte-for-byte guarantee — configparser's rewrite doesn't promise to keep
    unrelated comments/formatting, only the key/value data). A blind
    overwrite of this shared, systemwide file would be a severe blast-radius
    bug for a distributable OSS tool (architect review F4).

    `credentials_path` resolves the module-level default at CALL time, not
    at function-definition time — a plain default-parameter value would bind
    once at import and silently ignore a test's monkeypatch of
    DEFAULT_CREDENTIALS_PATH."""
    if credentials_path is None:
        credentials_path = DEFAULT_CREDENTIALS_PATH
    credentials_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parser = configparser.ConfigParser()
    if credentials_path.exists():
        parser.read(credentials_path)
    if not parser.has_section(profile):
        parser.add_section(profile)
    parser.set(profile, "aws_access_key_id", access_key_id)
    parser.set(profile, "aws_secret_access_key", secret_access_key)

    fd = os.open(credentials_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            parser.write(fh)
    finally:
        os.chmod(credentials_path, stat.S_IRUSR | stat.S_IWUSR)


def profile_exists(profile: str, credentials_path: Path | None = None) -> bool:
    if credentials_path is None:
        credentials_path = DEFAULT_CREDENTIALS_PATH
    if not credentials_path.exists():
        return False
    parser = configparser.ConfigParser()
    parser.read(credentials_path)
    return parser.has_section(profile)


def build_s3_client(profile: str, region: str) -> Any:
    """Shared S3 client factory (consistency review #7) used by both
    wizard.py (bucket validate/create) and uploader.py/pipeline.py
    (HEAD/upload) — so retry policy and region resolution can't drift
    between the two call sites."""
    session = boto3.Session(profile_name=profile, region_name=region)
    return session.client("s3", config=_RETRY_CONFIG)
