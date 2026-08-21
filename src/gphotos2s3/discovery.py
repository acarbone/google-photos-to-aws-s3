"""Walk Google Takeout zip files and discover media entries + sidecars.

No extraction happens here — only `zipfile.ZipFile.infolist()`, cheap even
for large archives. Corrupt/truncated zip handling is explicit (risk review
H4): a bad *archive* is reported as one error for that source and discovery
continues with the remaining sources; a corrupted *entry* inside an
otherwise-valid zip is only detected when actually read (hashing.py), scoped
to that one row.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from gphotos2s3.state import StateStore

MEDIA_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".heic",
    ".heif",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
    ".3gp",
    ".dng",
    ".cr2",
    ".nef",
    ".arw",
}

# Metadata sidecar naming, in priority order (research.md §2): Google
# renamed the pattern in late 2024; an export requested today can contain
# either or both, depending on when the underlying items were uploaded.
_SIDECAR_SUFFIXES = (".supplemental-metadata.json", ".json")
_TRUNCATION_MIN_PREFIX = 46


class UnsafePathError(Exception):
    """Raised for a zip entry name with a leading '/' or '..' segment.
    Content-specific (about this one file's own path), never systemic."""


@dataclass(slots=True)
class DiscoveryError:
    source: str
    message: str


@dataclass(slots=True)
class DiscoveredEntry:
    id: str
    zip_path: str
    entry_name: str
    size_bytes: int
    sidecar_entry_name: str | None
    unsafe: bool
    unsafe_reason: str | None


def compute_id(zip_path: str, entry_name: str) -> str:
    """id = sha256(basename(zip_path) + '::' + entry_name). Using only the
    zip's basename (not its full path) makes discovery robust against the
    user relocating their Takeout zips between sessions (architect review
    F5) — a realistic action over a multi-hour, multi-session backup.
    Renaming the zip file is NOT survived; that residual case is accepted
    and documented (README/wizard first-run message)."""
    basename = Path(zip_path).name
    return hashlib.sha256(f"{basename}::{entry_name}".encode()).hexdigest()


def is_unsafe_entry_name(entry_name: str) -> str | None:
    """Reject (not collapse) a malformed zip entry name — round-4 hardening
    (risk review, final round): a leading '/' or any '..' path segment marks
    the row failed with a clear reason rather than being silently
    normalized, which would break the uniqueness argument pointer_key/
    metadata_key depend on (they derive from the exact same raw inputs as
    `id`). Returns a human-readable reason, or None if the name is safe."""
    if entry_name.startswith("/"):
        return "entry name has a leading '/'"
    parts = entry_name.split("/")
    if any(part == ".." for part in parts):
        return "entry name contains a '..' path segment"
    return None


def _is_media(name: str) -> bool:
    return Path(name).suffix.lower() in MEDIA_EXTENSIONS


def _find_sidecar(names_in_dir: dict[str, str], media_name: str) -> str | None:
    """`names_in_dir` maps a lowercase basename to its original-cased
    zip entry name, restricted to the same directory as `media_name`."""
    for suffix in _SIDECAR_SUFFIXES:
        candidate = (media_name + suffix).lower()
        if candidate in names_in_dir:
            return names_in_dir[candidate]

    # Truncated-name fallback (research.md §2): Google truncates filenames
    # past ~46-51 chars, so the sidecar's own name can diverge from a naive
    # concatenation. Best-effort longest-common-prefix match within the
    # same directory.
    media_lower = media_name.lower()
    best: str | None = None
    best_len = _TRUNCATION_MIN_PREFIX - 1
    for lower_name, original in names_in_dir.items():
        stripped = lower_name
        for suffix in _SIDECAR_SUFFIXES:
            if stripped.endswith(suffix):
                stripped = stripped[: -len(suffix)]
                break
        else:
            continue  # not a sidecar file at all
        common = _common_prefix_len(media_lower, stripped)
        if common > best_len:
            best_len = common
            best = original
    return best


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b, strict=False):
        if ca != cb:
            break
        n += 1
    return n


def discover_zip(zip_path: Path) -> tuple[list[DiscoveredEntry], DiscoveryError | None]:
    """Lists one zip's media entries paired with their sidecar (if any).
    A bad archive returns ([], error) — callers continue with remaining
    sources rather than aborting the whole run."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        return [], DiscoveryError(source=str(zip_path), message=str(exc))

    with zf:
        try:
            infolist = zf.infolist()
        except (zipfile.BadZipFile, OSError) as exc:
            return [], DiscoveryError(source=str(zip_path), message=str(exc))

        by_dir: dict[str, dict[str, str]] = {}
        for info in infolist:
            if info.is_dir():
                continue
            directory = str(Path(info.filename).parent)
            by_dir.setdefault(directory, {})[Path(info.filename).name.lower()] = info.filename

        entries: list[DiscoveredEntry] = []
        for info in infolist:
            if info.is_dir() or not _is_media(info.filename):
                continue
            directory = str(Path(info.filename).parent)
            media_basename = Path(info.filename).name
            # `_find_sidecar` returns the sidecar's own full entry name
            # (already includes its directory, via `by_dir`'s values) — not
            # a bare basename, so it must be used as-is, not re-prefixed.
            sidecar_entry = _find_sidecar(by_dir.get(directory, {}), media_basename)

            unsafe_reason = is_unsafe_entry_name(info.filename)
            entries.append(
                DiscoveredEntry(
                    id=compute_id(str(zip_path), info.filename),
                    zip_path=str(zip_path),
                    entry_name=info.filename,
                    size_bytes=info.file_size,
                    sidecar_entry_name=sidecar_entry,
                    unsafe=unsafe_reason is not None,
                    unsafe_reason=unsafe_reason,
                )
            )
        return entries, None


def discover_sources(zip_paths: list[Path], state: StateStore) -> list[DiscoveryError]:
    """Discover every zip in `zip_paths`, writing rows via INSERT OR IGNORE
    (safe to re-run, safe to add more --source entries later). Unsafe entry
    names are inserted then immediately marked failed with a clear reason,
    rather than silently skipped or normalized. Returns any per-archive
    errors encountered; discovery never raises for a single bad source."""
    errors: list[DiscoveryError] = []
    for zip_path in zip_paths:
        entries, error = discover_zip(zip_path)
        if error is not None:
            errors.append(error)
            continue
        for entry in entries:
            state.insert_discovered(
                entry.id,
                entry.zip_path,
                entry.entry_name,
                entry.size_bytes,
                entry.sidecar_entry_name,
            )
            if entry.unsafe:
                state.mark_failed(
                    entry.id,
                    f"unsafe path in zip entry: {entry.unsafe_reason}",
                    increment_attempts=False,
                )
    return errors
