"""Interactive first-run setup: Takeout sources, AWS credentials, bucket.

Always runs on first use / --reconfigure (user's explicit choice, see
research.md §5) rather than silently depending on ambient AWS env vars —
the target audience is non-technical third parties who need to be walked
through this, not assumed to already have AWS tooling configured.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from gphotos2s3 import aws_credentials, iam_policy
from gphotos2s3.config import DEFAULT_STORAGE_CLASS, Config

STORAGE_CLASS_CHOICES = {
    "1": "GLACIER_IR",
    "2": "INTELLIGENT_TIERING",
    "3": "STANDARD_IA",
    "4": "STANDARD",
}


def _prompt(text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or (default or "")


def _prompt_yes_no(text: str, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    value = input(f"{text} {suffix}: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes")


def preflight_disk_space(min_free_gb: float = 5.0) -> tuple[bool, str]:
    """Cheap, one-time check at wizard time — not a substitute for the
    pipeline's own ENOSPC handling mid-run (risk review M6), but catches
    the common "no free space at all" case early with a clear message."""
    usage = shutil.disk_usage(Path.home())
    free_gb = usage.free / (1024**3)
    if free_gb < min_free_gb:
        return False, f"Only {free_gb:.1f} GB free — recommend at least {min_free_gb:.0f} GB."
    return True, f"{free_gb:.1f} GB free."


def collect_sources() -> list[str]:
    print("\nWhere are your Google Takeout .zip files?")
    print("(Enter a directory to use every .zip in it, or a single file path.)")
    print("(Blank line to finish.)")
    sources: list[str] = []
    while True:
        entry = input("  Path: ").strip()
        if not entry:
            break
        sources.append(entry)
    return sources


def choose_storage_class() -> str:
    print("\nS3 storage class:")
    print("  1) Glacier Instant Retrieval (default — cheapest with instant access)")
    print("  2) Intelligent-Tiering")
    print("  3) Standard-IA")
    print("  4) Standard")
    choice = _prompt("Choice", default="1")
    return STORAGE_CLASS_CHOICES.get(choice, DEFAULT_STORAGE_CLASS)


def ensure_bucket(s3_client: Any, bucket: str, region: str, prefix: str) -> None:
    """Validates the bucket exists (or offers to create it) using the
    in-memory credentials BEFORE anything is persisted to disk (risk review
    L5) — a failed validation never leaves partially-tested credentials on
    disk."""
    try:
        s3_client.head_bucket(Bucket=bucket)
        print(f"Bucket '{bucket}' exists and is reachable.")
        return
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in ("404", "NoSuchBucket", "NotFound"):
            raise

    print(f"\nBucket '{bucket}' was not found or not reachable with these credentials.")
    print("Setup policy required for the following (see printed IAM policy):")
    print(iam_policy.render(bucket, prefix, include_setup=True))
    if not _prompt_yes_no(f"Create bucket '{bucket}' now?", default=False):
        raise SystemExit("Cannot proceed without a bucket. Re-run `gphotos2s3 init`.")

    create_kwargs: dict[str, Any] = {"Bucket": bucket}
    if region != "us-east-1":
        create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3_client.create_bucket(**create_kwargs)

    s3_client.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3_client.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    s3_client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "abort-incomplete-multipart-uploads",
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                }
            ]
        },
    )
    print(
        f"Bucket '{bucket}' created with public access blocked, SSE-S3 encryption, "
        "and a 7-day abort-incomplete-multipart-upload lifecycle rule."
    )


def run_wizard(state_dir: Path) -> Config:
    print("=== gphotos2s3 setup ===")
    ok, msg = preflight_disk_space()
    print(f"Disk space check: {msg}")
    if not ok:
        _prompt_yes_no("Continue anyway?", default=False)

    sources = collect_sources()

    access_key_id, secret_access_key = aws_credentials.prompt_for_credentials()
    region = _prompt("AWS region", default="us-east-1")
    bucket = _prompt("S3 bucket name")
    prefix = _prompt("Key prefix", default="gphotos2s3")
    storage_class = choose_storage_class()
    dedupe = _prompt_yes_no("Deduplicate identical photos across albums?", default=True)

    profile = aws_credentials.default_profile_name(state_dir)

    # Validate with in-memory credentials BEFORE persisting anything.
    session = boto3.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region,
    )
    retry_config = BotoConfig(retries={"mode": "adaptive", "max_attempts": 10})
    s3_client = session.client("s3", config=retry_config)
    ensure_bucket(s3_client, bucket, region, prefix)

    # Validation succeeded — now persist.
    aws_credentials.write_credentials(profile, access_key_id, secret_access_key)
    print(f"\nCredentials saved to ~/.aws/credentials under profile '{profile}' (permissions 600).")

    print("\nOperate policy (for ongoing runs, after setup):")
    print(iam_policy.render(bucket, prefix, include_setup=False))

    config = Config(
        bucket=bucket,
        region=region,
        aws_profile=profile,
        prefix=prefix,
        storage_class=storage_class,
        dedupe=dedupe,
        sources=sources,
    )
    return config
