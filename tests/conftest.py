from __future__ import annotations

import json
import zipfile
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from gphotos2s3.config import Config
from gphotos2s3.state import open_state

TEST_BUCKET = "test-gphotos-bucket"
TEST_REGION = "us-east-1"


@pytest.fixture
def aws_credentials_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", TEST_REGION)


@pytest.fixture
def s3_client(aws_credentials_env):
    with mock_aws():
        client = boto3.client("s3", region_name=TEST_REGION)
        client.create_bucket(Bucket=TEST_BUCKET)
        yield client


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture
def state_store(state_dir: Path):
    with open_state(state_dir / "state.db") as store:
        yield store


@pytest.fixture
def config() -> Config:
    return Config(
        bucket=TEST_BUCKET,
        region=TEST_REGION,
        aws_profile="default",
        prefix="gphotos2s3",
        storage_class="STANDARD",
        dedupe=True,
        workers=2,
        max_attempts=5,
        sources=[],
    )


def make_sidecar(taken_at_epoch: int = 1700000000, **overrides) -> bytes:
    data = {
        "photoTakenTime": {"timestamp": str(taken_at_epoch)},
        "geoData": {"latitude": 45.0, "longitude": 9.0},
        "description": "A test photo",
        "favorited": True,
        "people": [{"name": "Alice"}],
        **overrides,
    }
    return json.dumps(data).encode("utf-8")


def build_takeout_zip(
    path: Path,
    entries: dict[str, bytes],
) -> Path:
    """entries maps a zip entry name -> raw bytes to write."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return path


@pytest.fixture
def simple_takeout_zip(tmp_path: Path) -> Path:
    zip_path = tmp_path / "takeout-20260101T000000Z-001.zip"
    base = "Takeout/Google Photos/Photos from 2020/IMG_0001.jpg"
    build_takeout_zip(
        zip_path,
        {
            base: b"fake-jpeg-bytes-0001",
            f"{base}.supplemental-metadata.json": make_sidecar(),
        },
    )
    return zip_path
