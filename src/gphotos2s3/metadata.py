"""Parse a Google Takeout photo/video JSON sidecar into a normalized dict.

Google's sidecar schema is not guaranteed stable across export requests
(research.md §2) — every field access here is defensive. A media file with
no sidecar, or a sidecar with an unexpected shape, must never block the
backup of the file itself; this module only ever returns a best-effort dict,
never raises on malformed input.
"""

from __future__ import annotations

import datetime
import json
from typing import Any


def parse_sidecar(raw_json: bytes | str) -> dict[str, Any]:
    """Parse Google's supplemental-metadata JSON into a normalized dict.
    Tolerant of missing/extra/malformed keys — returns whatever could be
    extracted, never raises for a shape mismatch (only for genuinely
    unparsable JSON, which the caller should treat as "no metadata found",
    not a fatal error)."""
    data = json.loads(raw_json)
    if not isinstance(data, dict):
        return {}

    normalized: dict[str, Any] = {}

    taken_at = _extract_timestamp(data.get("photoTakenTime"))
    if taken_at is not None:
        normalized["taken_at"] = taken_at

    geo = data.get("geoData") or data.get("geoDataExif")
    if isinstance(geo, dict):
        lat = geo.get("latitude")
        lon = geo.get("longitude")
        if isinstance(lat, int | float) and isinstance(lon, int | float) and (lat != 0 or lon != 0):
            normalized["latitude"] = float(lat)
            normalized["longitude"] = float(lon)

    description = data.get("description")
    if isinstance(description, str) and description.strip():
        normalized["description"] = description

    favorited = data.get("favorited")
    if isinstance(favorited, bool):
        normalized["favorited"] = favorited

    people = data.get("people")
    if isinstance(people, list):
        names = [p.get("name") for p in people if isinstance(p, dict) and p.get("name")]
        if names:
            normalized["people"] = names

    title = data.get("title")
    if isinstance(title, str) and title.strip():
        normalized["title"] = title

    return normalized


def _extract_timestamp(photo_taken_time: Any) -> str | None:
    """Google's photoTakenTime carries a Unix epoch string in `timestamp`.
    Normalized to an ISO-8601 UTC string so downstream consumers (and
    tests) compare on one unambiguous format regardless of the exporting
    account's local timezone at the time of upload."""
    if not isinstance(photo_taken_time, dict):
        return None
    raw = photo_taken_time.get("timestamp")
    if raw is None:
        return None
    try:
        epoch_seconds = int(raw)
    except (TypeError, ValueError):
        return None
    return datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc).isoformat()
