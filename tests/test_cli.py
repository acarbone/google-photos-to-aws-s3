from __future__ import annotations

import pytest

from gphotos2s3 import aws_credentials, cli
from gphotos2s3.config import Config, config_path
from gphotos2s3.config import db_path as state_db_path
from gphotos2s3.state import open_state
from tests.conftest import TEST_BUCKET, TEST_REGION, build_takeout_zip


@pytest.mark.parametrize(
    "args",
    [
        ["--help"],
        ["init", "--help"],
        ["run", "--help"],
        ["status", "--help"],
        ["verify", "--help"],
        ["retry-failed", "--help"],
    ],
)
def test_help_runs_without_error(args):
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(args)
    assert exc_info.value.code == 0


def _write_config(state_dir, bucket=TEST_BUCKET, region=TEST_REGION):
    state_dir.mkdir(parents=True, exist_ok=True)
    config = Config(
        bucket=bucket,
        region=region,
        aws_profile="default",
        prefix="gphotos2s3",
        storage_class="STANDARD",
        sources=[],
    )
    config.save(config_path(state_dir))
    return config


def test_status_command_prints_counts(tmp_path, capsys):
    state_dir = tmp_path / "state"
    _write_config(state_dir)
    with open_state(state_db_path(state_dir)) as store:
        store.insert_discovered("id1", "z.zip", "a.jpg", 10)

    args = cli.build_parser().parse_args(["--state-dir", str(state_dir), "status"])
    rc = cli.cmd_status(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "pending: 1" in out


def test_run_command_uploads_and_reports(tmp_path, s3_client, monkeypatch, capsys):
    state_dir = tmp_path / "state"
    _write_config(state_dir)
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"a/photo.jpg": b"hello"})

    monkeypatch.setattr(aws_credentials, "build_s3_client", lambda profile, region: s3_client)

    args = cli.build_parser().parse_args(
        ["--state-dir", str(state_dir), "run", "--source", str(zip_path), "--workers", "1"]
    )
    rc = cli.cmd_run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Uploaded: 1" in out


def test_retry_failed_picks_up_failed_and_verify_failed(tmp_path, s3_client, monkeypatch, capsys):
    state_dir = tmp_path / "state"
    _write_config(state_dir)

    with open_state(state_db_path(state_dir)) as store:
        store.insert_discovered("id1", "z.zip", "a.jpg", 10)
        store.mark_failed("id1", "boom", increment_attempts=True)
        store.insert_discovered("id2", "z.zip", "b.jpg", 10)
        store.mark_hashed("id2", "sha2", 10)
        store.mark_uploaded("id2", "content/x", "pointer/x", TEST_BUCKET, content_deduped=False)
        store.mark_verify_failed("id2", "checksum mismatch")

    monkeypatch.setattr(aws_credentials, "build_s3_client", lambda profile, region: s3_client)
    # No zip sources needed for this assertion — we only check the reset count.
    args = cli.build_parser().parse_args(
        ["--state-dir", str(state_dir), "retry-failed", "--source", str(tmp_path)]
    )
    cli.cmd_retry_failed(args)
    out = capsys.readouterr().out
    assert "Reset 2 row(s) to pending." in out


def test_profile_flag_overrides_config(tmp_path, s3_client, monkeypatch):
    state_dir = tmp_path / "state"
    _write_config(state_dir)
    zip_path = tmp_path / "takeout-001.zip"
    build_takeout_zip(zip_path, {"a/photo.jpg": b"hello"})

    captured = {}

    def fake_build_s3_client(profile, region):
        captured["profile"] = profile
        return s3_client

    monkeypatch.setattr(aws_credentials, "build_s3_client", fake_build_s3_client)

    args = cli.build_parser().parse_args(
        [
            "--state-dir",
            str(state_dir),
            "run",
            "--source",
            str(zip_path),
            "--workers",
            "1",
            "--profile",
            "custom-profile",
        ]
    )
    cli.cmd_run(args)
    assert captured["profile"] == "custom-profile"
