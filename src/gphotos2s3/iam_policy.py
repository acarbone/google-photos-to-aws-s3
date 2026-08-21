"""Render least-privilege example IAM policies for a given bucket/prefix.

Two tiers (risk review M1): a **setup** policy (only needed once, if the
wizard is asked to create the bucket) and a smaller **operate** policy used
for every subsequent run. A user who scopes their key to "operate" only,
after using the wizard's create-bucket path once with broader credentials,
is not surprised by AccessDenied.
"""

from __future__ import annotations

import json
from typing import Any


def _statement(sid: str, actions: list[str], resources: list[str]) -> dict[str, Any]:
    return {
        "Sid": sid,
        "Effect": "Allow",
        "Action": actions,
        "Resource": resources,
    }


def operate_policy(bucket: str, prefix: str = "") -> dict[str, Any]:
    """Ongoing run permissions. s3:GetObject is required because
    HeadObject — used throughout for idempotency checks — is authorized
    under the s3:GetObject action per AWS's own IAM reference, not a
    leftover (risk review L3)."""
    object_arn = f"arn:aws:s3:::{bucket}/{prefix}*" if prefix else f"arn:aws:s3:::{bucket}/*"
    bucket_arn = f"arn:aws:s3:::{bucket}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            _statement(
                "GPhotos2S3Operate",
                [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:AbortMultipartUpload",
                    "s3:ListMultipartUploadParts",
                ],
                [object_arn],
            ),
            _statement("GPhotos2S3ListBucket", ["s3:ListBucket"], [bucket_arn]),
        ],
    }


def setup_policy(bucket: str, prefix: str = "") -> dict[str, Any]:
    """Superset needed only if the wizard is asked to create the bucket
    itself (risk review M1) — CreateBucket, lifecycle rule, public-access
    block, and default encryption configuration."""
    operate = operate_policy(bucket, prefix)
    bucket_arn = f"arn:aws:s3:::{bucket}"
    operate["Statement"].append(
        _statement(
            "GPhotos2S3BucketSetup",
            [
                "s3:CreateBucket",
                "s3:PutLifecycleConfiguration",
                "s3:PutBucketPublicAccessBlock",
                "s3:PutEncryptionConfiguration",
            ],
            [bucket_arn],
        )
    )
    return operate


def render(bucket: str, prefix: str = "", *, include_setup: bool = True) -> str:
    """Human-readable printout for the wizard: both tiers, clearly labeled."""
    parts = ["# Minimum-privilege IAM policy for gphotos2s3", ""]
    if include_setup:
        parts.append("## Setup (one-time, only if you ask the wizard to create the bucket)")
        parts.append(json.dumps(setup_policy(bucket, prefix), indent=2))
        parts.append("")
    parts.append("## Operate (every run, once the bucket exists)")
    parts.append(json.dumps(operate_policy(bucket, prefix), indent=2))
    return "\n".join(parts)
