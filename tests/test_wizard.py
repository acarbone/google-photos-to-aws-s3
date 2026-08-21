from __future__ import annotations

import configparser
import stat
from pathlib import Path

import pytest

from gphotos2s3 import aws_credentials, wizard
from tests.conftest import TEST_REGION


@pytest.fixture
def fake_credentials_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "aws-credentials"
    monkeypatch.setattr(aws_credentials, "DEFAULT_CREDENTIALS_PATH", path)
    return path


def _scripted_inputs(monkeypatch, answers: list[str]):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: next(it))


def test_wizard_writes_config_and_credentials_with_0600(
    tmp_path, monkeypatch, fake_credentials_path, aws_credentials_env
):
    from moto import mock_aws

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    with mock_aws():
        # Pre-create the bucket so ensure_bucket's "exists" branch is taken.
        import boto3

        boto3.client("s3", region_name=TEST_REGION).create_bucket(Bucket="my-bucket")

        _scripted_inputs(
            monkeypatch,
            [
                "",  # sources: blank line, no sources for this test
                TEST_REGION,  # region
                "my-bucket",  # bucket
                "gphotos2s3",  # prefix
                "1",  # storage class choice
                "y",  # dedupe
            ],
        )
        monkeypatch.setattr(
            aws_credentials, "prompt_for_credentials", lambda: ("AKIAFAKE", "secretvalue")
        )

        config = wizard.run_wizard(state_dir)

    assert config.bucket == "my-bucket"
    assert config.region == TEST_REGION
    assert config.storage_class == "GLACIER_IR"
    assert config.dedupe is True

    assert fake_credentials_path.exists()
    mode = stat.S_IMODE(fake_credentials_path.stat().st_mode)
    assert mode == 0o600

    parser = configparser.ConfigParser()
    parser.read(fake_credentials_path)
    assert parser.get(config.aws_profile, "aws_access_key_id") == "AKIAFAKE"
    assert parser.get(config.aws_profile, "aws_secret_access_key") == "secretvalue"


def test_wizard_preserves_unrelated_existing_profile(
    tmp_path, monkeypatch, fake_credentials_path, aws_credentials_env
):
    """Architect review F4 / risk M4: a pre-existing unrelated profile must
    survive init/--reconfigure untouched."""
    fake_credentials_path.write_text(
        "[other-project]\naws_access_key_id = OTHERKEY\naws_secret_access_key = othersecret\n"
    )

    from moto import mock_aws

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    with mock_aws():
        import boto3

        boto3.client("s3", region_name=TEST_REGION).create_bucket(Bucket="my-bucket")
        _scripted_inputs(monkeypatch, ["", TEST_REGION, "my-bucket", "gphotos2s3", "1", "y"])
        monkeypatch.setattr(
            aws_credentials, "prompt_for_credentials", lambda: ("AKIAFAKE", "secretvalue")
        )
        wizard.run_wizard(state_dir)

    parser = configparser.ConfigParser()
    parser.read(fake_credentials_path)
    assert parser.get("other-project", "aws_access_key_id") == "OTHERKEY"
    assert parser.get("other-project", "aws_secret_access_key") == "othersecret"


def test_secret_entry_uses_getpass_not_plain_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "AKIAFAKE")
    calls = []

    def fake_getpass(prompt=""):
        calls.append(prompt)
        return "hidden-secret"

    monkeypatch.setattr("gphotos2s3.aws_credentials.getpass.getpass", fake_getpass)
    access_key, secret = aws_credentials.prompt_for_credentials()
    assert access_key == "AKIAFAKE"
    assert secret == "hidden-secret"
    assert len(calls) == 1


def test_credentials_not_persisted_when_bucket_validation_fails(
    tmp_path, monkeypatch, fake_credentials_path, aws_credentials_env
):
    """Risk review L5: validate BEFORE persisting — a failed validation must
    never leave credentials on disk."""
    from moto import mock_aws

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    with mock_aws():
        # Bucket is never created; user declines to create it -> SystemExit.
        # Input order: sources, region, bucket, prefix, storage class,
        # dedupe, then ensure_bucket's own "create it now?" prompt.
        _scripted_inputs(
            monkeypatch,
            ["", TEST_REGION, "nonexistent-bucket", "gphotos2s3", "1", "y", "n"],
        )
        monkeypatch.setattr(
            aws_credentials, "prompt_for_credentials", lambda: ("AKIAFAKE", "secretvalue")
        )
        with pytest.raises(SystemExit):
            wizard.run_wizard(state_dir)

    assert not fake_credentials_path.exists()


def test_no_secret_leak_into_config_json(
    tmp_path, monkeypatch, fake_credentials_path, aws_credentials_env
):
    from moto import mock_aws

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    secret = "super-secret-value-xyz"

    with mock_aws():
        import boto3

        boto3.client("s3", region_name=TEST_REGION).create_bucket(Bucket="my-bucket")
        _scripted_inputs(monkeypatch, ["", TEST_REGION, "my-bucket", "gphotos2s3", "1", "y"])
        monkeypatch.setattr(aws_credentials, "prompt_for_credentials", lambda: ("AKIAFAKE", secret))
        config = wizard.run_wizard(state_dir)

    config_path = state_dir / "config.json"
    config.save(config_path)
    assert secret not in config_path.read_text()
