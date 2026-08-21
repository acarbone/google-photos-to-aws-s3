"""`status`/`verify` output formatting."""

from __future__ import annotations

from typing import Any

from gphotos2s3.state import FileRow, StateStore


def format_status(state: StateStore) -> str:
    counts = state.count_by_status()
    total = sum(counts.values())
    lines = [f"Total discovered: {total}"]
    for status in ("pending", "uploading", "uploaded", "failed", "verify_failed"):
        lines.append(f"  {status}: {counts.get(status, 0)}")

    deduped_rows = list(state.iter_by_status("uploaded"))
    deduped_count = sum(1 for r in deduped_rows if r.content_deduped)
    if deduped_rows:
        lines.append(f"Deduplicated (content already existed): {deduped_count}")

    # Orphaned-multipart-upload visibility note (risk review L6): the tool
    # doesn't track these locally, but the bucket's lifecycle rule aborts
    # them automatically after 7 days.
    lines.append(
        "\nNote: any interrupted large-file upload leaves a temporary, "
        "self-cleaning multipart-upload record in S3 (auto-aborted after "
        "7 days by the bucket's lifecycle rule) — no action needed."
    )
    return "\n".join(lines)


def format_verify_results(mismatches: list[tuple[FileRow, str]]) -> str:
    if not mismatches:
        return "verify: all uploaded files match their expected checksums."
    lines = [f"verify: {len(mismatches)} mismatch(es) found — marked 'verify_failed':"]
    for row, reason in mismatches:
        lines.append(f"  {row.zip_path}::{row.entry_name} — {reason}")
    lines.append("\nRun `gphotos2s3 retry-failed` to re-upload these.")
    return "\n".join(lines)


def format_run_summary(summary: Any) -> str:
    lines = [
        f"Uploaded: {summary.uploaded}",
        f"Failed: {summary.failed}",
    ]
    if summary.discovery_errors:
        lines.append(f"Discovery errors ({len(summary.discovery_errors)}):")
        for err in summary.discovery_errors:
            lines.append(f"  {err}")
    if summary.halted:
        lines.append(f"\nHALTED: {summary.halt_message}")
    return "\n".join(lines)
