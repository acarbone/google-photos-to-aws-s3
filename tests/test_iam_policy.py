"""Consistency review #4: docs/iam-policy-example.json must stay in sync
with iam_policy.py's rendered output — a static doc with no equality check
can silently drift from the code it documents."""

from __future__ import annotations

import json
from pathlib import Path

from gphotos2s3 import iam_policy

DOCS_PATH = Path(__file__).resolve().parents[1] / "docs" / "iam-policy-example.json"
EXAMPLE_BUCKET = "your-bucket-name"
EXAMPLE_PREFIX = "gphotos2s3"


def test_docs_example_matches_rendered_output():
    on_disk = json.loads(DOCS_PATH.read_text())
    expected = {
        "setup": iam_policy.setup_policy(EXAMPLE_BUCKET, EXAMPLE_PREFIX),
        "operate": iam_policy.operate_policy(EXAMPLE_BUCKET, EXAMPLE_PREFIX),
    }
    assert on_disk == expected


def test_operate_policy_is_subset_of_setup_policy_actions():
    setup = iam_policy.setup_policy(EXAMPLE_BUCKET, EXAMPLE_PREFIX)
    operate = iam_policy.operate_policy(EXAMPLE_BUCKET, EXAMPLE_PREFIX)
    setup_sids = {s["Sid"] for s in setup["Statement"]}
    operate_sids = {s["Sid"] for s in operate["Statement"]}
    assert operate_sids <= setup_sids
