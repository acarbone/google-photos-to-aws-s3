"""Stream a zip entry into a spooled temp file while computing its sha256.

Never fully materializes a large file in memory: spills to disk above
`max_memory_bytes`, using the OS temp dir. Disk-space exhaustion during
spooling (OSError/ENOSPC) is surfaced to the caller, never left to crash the
process — pipeline.py's systemic-failure classifier treats it as a systemic
condition (risk review M6/H3), not a per-file one.
"""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from typing import IO

_CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_MEMORY_BYTES = 64 * 1024 * 1024


def spool_and_hash(
    zf: zipfile.ZipFile,
    entry_name: str,
    max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES,
) -> tuple[IO[bytes], str, int]:
    """Returns (spooled_file, sha256_hex, size_bytes). The caller owns the
    returned file end-to-end via try/finally (risk review F11) — closed on
    every path (dedup hit, uploaded, or failed), never left to an implicit
    contract.

    Zero-byte files are hashed and handled like any other file — no special
    casing (risk review L1); hashlib.sha256() of an empty stream is a
    well-defined, stable digest.
    """
    # Lint suppression justified: the caller owns this file's lifecycle
    # end-to-end (returned open, closed by pipeline.py via try/finally).
    spooled: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=max_memory_bytes)  # noqa: SIM115
    digest = hashlib.sha256()
    size = 0
    with zf.open(entry_name) as src:
        while True:
            chunk = src.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            spooled.write(chunk)
            size += len(chunk)
    spooled.seek(0)
    return spooled, digest.hexdigest(), size
