# Plan: Google Photos (Takeout) → AWS S3 Backup Tool

> **Status**: Implemented — see the outcome note below and the fully-checked task checklist in §13.
> **Tier**: 2 (Full pipeline) — new feature, greenfield, handles credentials and long-running state; a wrong assumption here (idempotency, dedup, credential storage) is costly to unwind. Multi-agent review cycle required before implementation (see §12).
>
> **Outcome** [2026-08-21]: Implemented as planned, after 4 rounds of the multi-agent review cycle (§12) — 1 Critical + several High findings in round 1 (architect-reviewer, risk-analyst), a new Critical in round 2 (dedup-after-state-loss race), 2 new High findings in round 3 (pointer/metadata key uniqueness gap, systemic-classifier type-flapping), all closed by round 4 (**Pass with advisories**). The round-2 finding drove a genuine mid-plan architecture change — from path-based S3 keys to content-addressed keys (`content_key = f(sha256, ext)`) — which is reflected in this document's §4/§6/§7 rather than in a separate amendments file, since it happened before implementation started, not after. Every module in §3/§13 was implemented; 77 tests pass (`pytest`), lint is clean (`ruff check` + `ruff format --check`), and typing is clean (`mypy`). One real bug was caught by the tests the plan required: `discovery.py`'s sidecar-path pairing double-prefixed the directory, fixed during Phase E. No real upload was executed against real AWS or a real Google Takeout export, per explicit scope. See `CHANGELOG.md` [2026-08-21] for the full session record.

## 0. Decisions locked with the user (do not re-litigate)

| Question | Decision |
|---|---|
| Language/runtime | **Python** (3.10+) |
| Default S3 storage class | **S3 Glacier Instant Retrieval** (`GLACIER_IR`), user-overridable in config |
| Google Photos deletion | **Out of scope.** Backup-only, one-way, never calls any Google API. |
| AWS credential UX | **Always run an interactive setup wizard** (first run / `--reconfigure`), persisting into the standard `~/.aws/credentials` file under a dedicated profile — not a bespoke secret store (see research.md §5) |
| Execute a real upload in this session | **No.** Implementation + automated (mocked) tests only. |

## 1. Goal

Ship a freely-distributable, open-source, pip-installable Python CLI that:

1. Reads one or more Google Takeout export `.zip` files (Google Photos portion) without requiring the user to fully extract them first.
2. Uploads every unique media file to a user's own AWS S3 bucket at low-cost storage (`GLACIER_IR` default).
3. Preserves Google's own per-photo metadata (JSON sidecars) alongside each upload.
4. Is safe to interrupt (Ctrl+C, crash, laptop sleep, reboot) and resume at any point **without re-uploading already-transferred content and without restarting discovery from scratch**.
5. Is usable by a non-technical third party: an interactive wizard collects Takeout paths and AWS credentials, validates the bucket, and prints a minimum-privilege IAM policy example.
6. Never touches Google Photos itself (read-only against local zip files) and never performs a real upload as part of building/testing this repo.

## 2. Non-goals

- No Google Photos API / OAuth integration of any kind.
- No GUI — CLI only (a GUI can be a future community contribution).
- No automatic transition/lifecycle management between S3 storage classes beyond the one-time `AbortIncompleteMultipartUpload` rule attached at bucket setup (§3 of research.md). Users who want lifecycle transitions configure them in AWS directly.
- No support for re-importing/restoring from S3 back into Google Photos (backup direction only).
- No bundling/building of a compiled binary in this pass (pip package only); a Go/PyInstaller single-binary distribution is a possible future enhancement, not in scope now.

## 3. Package layout

```
pyproject.toml
LICENSE                              (MIT)
README.md                            (rewritten — product-facing, see §9)
.gitignore                           (extended)
CHANGELOG.md                         (existing — new entry appended)
src/
└── gphotos2s3/
    ├── __init__.py                  (package version)
    ├── cli.py                       (argparse entrypoint, subcommands: init, run, status, verify, retry-failed)
    ├── config.py                    (Config dataclass, load/save config.json, default paths)
    ├── wizard.py                    (interactive setup: Takeout paths, AWS creds, bucket validate/create, IAM policy printout)
    ├── aws_credentials.py           (read/write ~/.aws/credentials profile, chmod 0600)
    ├── discovery.py                 (walk zip files, list media entries, pair with JSON sidecars — old + new naming)
    ├── state.py                     (SQLite schema, migrations, status transitions, reconciliation-on-startup)
    ├── hashing.py                   (streaming sha256 while spooling an entry to a SpooledTemporaryFile)
    ├── uploader.py                  (S3 client wrapper: HEAD-check, multipart upload via TransferConfig, metadata JSON side-object, retry/backoff)
    ├── metadata.py                  (parse Google JSON sidecar → normalized dict; tolerate missing/partial fields)
    ├── pipeline.py                  (orchestrates discovery → dedup → upload loop, progress reporting via `rich`)
    ├── report.py                    (status/summary command output)
    └── iam_policy.py                (renders the least-privilege example policy as a string)
tests/
├── conftest.py                      (moto S3 fixture, synthetic Takeout zip fixture builder)
├── test_discovery.py
├── test_state.py
├── test_hashing.py
├── test_uploader.py
├── test_metadata.py
├── test_pipeline_resume.py          (kill-mid-run simulation → resume correctness)
├── test_dedup.py
├── test_wizard.py                   (mocked stdin/stdout, mocked boto3 sts/s3 calls)
└── test_cli.py
docs/
└── iam-policy-example.json          (also emitted by iam_policy.py; kept as a static reference doc)
```

Root-level `spec/design/*`, `AGENTS.md`, `SKILLS.md`, `PROJECT_MEMORY.md`, `CLAUDE.md`, `.cursor/*`, `.claude/*` are **untouched** — they continue to govern how this repo's own process works. README.md is rewritten to be product-facing per §9 (with a link back to the Spec-Driven docs for contributors), since the repo's purpose has changed from "empty template" to "template that has now been instantiated as this product."

## 4. Data model — SQLite state (`state.py`)

```sql
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- schema_meta['version'] = '1'. A trivial migration runner
-- (apply_migrations(conn) in state.py) checks this on every open and applies
-- any pending numbered migration in order; v1 has no predecessor, so it's a
-- no-op today, but the mechanism exists before it's ever needed (architect
-- review F8) — a future schema change never forces "delete your state DB and
-- lose all resume progress".

CREATE TABLE IF NOT EXISTS files (
    id              TEXT PRIMARY KEY,   -- sha256(basename(zip_path) || "::" || entry_name), see §5
    zip_path        TEXT NOT NULL,      -- last-seen absolute path, informational only — not part of id
    entry_name      TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    sha256          TEXT,               -- filled in once hashed (may be NULL until first processing pass)
    status          TEXT NOT NULL DEFAULT 'pending',
                        -- pending | uploading | uploaded | failed | verify_failed
                        -- (no 'skipped_duplicate' — see §6/§7 round-3 redesign: dedup is now
                        -- structural via content-addressed keys, not a distinct status)
    metadata_status TEXT NOT NULL DEFAULT 'not_found',
                        -- not_found | pending | uploaded | failed  (independent of `status` — see below)
    content_key     TEXT,               -- f"{prefix}/content/{sha256}{ext}" — pure function of content,
                                         -- shared by every row with the same sha256 (round-3 redesign)
    pointer_key     TEXT,               -- f"{prefix}/library/{zip-relative-path}.pointer.json" — unique
                                         -- per row, always this row's own path, never shared
    metadata_key    TEXT,               -- f"{prefix}/library/{zip-relative-path}.metadata.json" — unique
                                         -- per row when a sidecar was found for this occurrence
    s3_bucket       TEXT,
    content_deduped INTEGER NOT NULL DEFAULT 0,  -- informational: 1 if content_key already existed
                                                  -- when this row went to upload it (bytes not re-sent)
    error           TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    discovered_at   TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    files_uploaded INTEGER DEFAULT 0,
    files_deduped INTEGER DEFAULT 0,    -- rows whose content_key already existed (bytes not re-sent)
    files_failed INTEGER DEFAULT 0,
    bytes_uploaded INTEGER DEFAULT 0,
    bytes_deduped INTEGER DEFAULT 0
);
```

**Metadata is tracked as its own state, not folded into `status`** (architect review F1 — Critical). The media object and its `<key>.metadata.json` companion are two independent S3 PUTs with no cross-object transaction; a row can only be considered fully, durably done when *both* are accounted for. `metadata_status` transitions the same way `status` does (`pending` written before the companion PUT starts, `uploaded`/`failed` after) and is checked by both reconciliation and `verify` — a sidecar upload that silently failed while the primary succeeded is now detectable and retryable, not permanently invisible.

**Concurrency model** (architect review F3 — High). `pyproject.toml`'s SQLite usage is WAL-mode: `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=30000` set once per connection, one `sqlite3.connect(..., check_same_thread=True)` connection **per worker thread** (never shared across threads), short-lived transactions (one `COMMIT` per status write, never batched — this is what crash-safety depends on). WAL mode is designed exactly for "several threads, frequent short writes, one writer at a time" and is the standard, well-understood answer here — no bespoke writer-queue needed. `test_state.py` gains a concurrency test: N threads hammering status transitions on distinct rows concurrently, asserting no `database is locked` errors and no lost writes.

**Single-instance lock, atomic acquisition** (risk review H1 — High; atomicity gap closed in round 3 re-review). `run` and `retry-failed` acquire a PID lock file (`<state-dir>/gphotos2s3.lock`) via `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` — an atomic create-exclusive syscall, not a check-then-write pair, so two processes launched in the same instant cannot both succeed. `FileExistsError` ⇒ read the existing PID and check liveness (`os.kill(pid, 0)`); alive ⇒ refuse to start with a clear message; dead ⇒ `os.remove` the stale file and retry the `O_EXCL` open once (itself still atomic — no window where two dead-lock-reclaimers can both proceed). Lock is released (file removed) on clean exit; a lock left behind by a crash is exactly the "dead PID" case the reclaim path handles. Prevents two concurrent processes against the same state dir from doubling worker concurrency.

**Reconciliation on startup** (moved to `pipeline.reconcile_stuck_rows(state_conn, s3_client)` — architect review F2, High: `state.py` stays free of any boto3/S3 semantics; this is an orchestration concern spanning two subsystems, not a persistence concern). Any row with `status='uploading'` (or `metadata_status='pending'`) from a previous, non-clean-exited run is re-checked by calling `uploader.already_uploaded()` / an equivalent HEAD-and-compare for the metadata key — match ⇒ `uploaded`; anything else ⇒ reset to `pending`, `attempts` left as-is (not incremented — being killed isn't the file's fault). Runs before every `run`/`retry-failed` invocation, unconditionally, after the lock is acquired. Because `content_key` is now a pure function of `sha256` (§6/§7 round-3 redesign) rather than a runtime-assigned "canonical row," reconciliation — and rediscovery after total state-DB loss (§10 `test_state_rebuild.py`) — needs no notion of "which row was canonical": every row independently resolves its own `content_key` from its own `sha256` and checks it, with no ordering or ownership ambiguity possible, concurrently or not.

**Known limitation, documented rather than solved** (risk review M8): if the state DB is deleted/rebuilt, per-row `attempts`/`error` history for permanently-broken files (e.g. an oversized S3 key, §6) is lost, and such a file will be retried again rather than remembered as hopeless. Acceptable for v1 — stated explicitly in README rather than left implicit.

## 5. Discovery & metadata pairing (`discovery.py`, `metadata.py`)

- Input: a list of zip file paths (or a directory glob'd for `*.zip`/`takeout-*.zip`), collected by the wizard or passed via `--source`.
- For each zip, `zipfile.ZipFile(path).infolist()` — **no extraction at this stage**, just entry listing (cheap even for large archives).
- Media filter: extension allowlist covering common Google Photos formats — `.jpg .jpeg .png .gif .webp .heic .heif .mp4 .mov .avi .mkv .m4v .3gp .dng .cr2 .nef .arw` (RAW formats Google Photos also stores) — case-insensitive.
- Sidecar pairing, in priority order, for a media entry named `X`:
  1. `X.supplemental-metadata.json` (current Google naming, late-2024+)
  2. `X.json` (legacy naming)
  3. Truncated-name fallback: if neither exists, look for any JSON entry in the **same directory** whose name, with the metadata suffix stripped, is the **longest common prefix** of `X` at ≥ 46 characters (documented Google truncation point) — best-effort, logged when used.
  4. No match found ⇒ proceed with `metadata_found=0`; never blocks the upload.
- `metadata.py` parses whatever sidecar JSON is found into a normalized dict (`taken_at`, `latitude`, `longitude`, `description`, `favorited`, `people`) tolerant of missing keys — Google's schema is not guaranteed stable (research.md §2).
- Discovery writes rows via `INSERT OR IGNORE INTO files (...)` using the id scheme in §4 — safe to re-run, safe to add more zip parts to `--source` later and re-run discovery to pick them up.
- **Row identity uses `basename(zip_path)`, not the full path** (consistency review #2 / architect review F5): `id = sha256(basename(zip_path) + "::" + entry_name)`. This makes discovery robust against the user relocating their Takeout zips between sessions (e.g. moving them from `Downloads` to an archive folder) — a realistic action over a multi-hour, multi-session backup — since only the filename, not its directory, is part of identity. It does **not** survive a *rename* of the zip file; that residual case is accepted and stated explicitly in the wizard's first-run message and README ("keep your Takeout zip filenames unchanged for the duration of a backup; moving them to a different folder is fine"), rather than solved structurally, because doing so would require content-hashing entire zips at listing time — defeating the point of a cheap `infolist()` pass. `zip_path` itself is still stored (last-seen absolute path, informational — used to actually open the file, refreshed on each discovery run) but is not part of `id`.
- **Corrupt/truncated zip handling is explicit, not incidental** (risk review H4): `discovery.py` wraps the per-source `zipfile.ZipFile(path)` open and `infolist()` call in a `try/except zipfile.BadZipFile`; a bad *archive* is reported as one clear error for that source path and discovery continues with the remaining `--source` entries. A `zipfile.BadZipFile`/CRC error raised while *reading a single entry* later (during hashing, §6) is scoped to that one file — the row is marked `failed` with the error, the rest of that same zip's entries are unaffected.
- **Zip handle lifecycle is a discovery/pipeline concern, not `uploader.py`'s** (architect review F12): each worker task opens its own `zipfile.ZipFile(zip_path)` for the duration of processing one entry (`zipfile.ZipFile` objects are not thread-safe to share); `uploader.py` never touches zip files at all, only file-like objects handed to it.

## 6. Hashing & upload (`hashing.py`, `uploader.py`)

```python
# hashing.py
import hashlib
import tempfile
import zipfile

def spool_and_hash(zf: zipfile.ZipFile, entry_name: str, max_memory_bytes: int = 64 * 1024 * 1024):
    """Stream a zip entry into a SpooledTemporaryFile while computing sha256.
    Never fully materializes large files in memory; spills to disk above
    max_memory_bytes, using the OS temp dir (caller is responsible for
    ensuring free space — surfaced in the wizard's preflight check)."""
    spooled = tempfile.SpooledTemporaryFile(max_size=max_memory_bytes)
    digest = hashlib.sha256()
    with zf.open(entry_name) as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
            spooled.write(chunk)
    spooled.seek(0)
    return spooled, digest.hexdigest()
```

> **Round-3 redesign** (closes the round-2 Critical finding — see §12): keys are now **content-addressed**, not path-derived. This is not a wording fix; it structurally eliminates the dedup-after-state-loss race the round-2 risk-analyst pass found, because "is this content already in S3" becomes a pure function of `sha256` — computable independently by any row, with no dependency on which row processed first, in-run or across a full state-DB loss.

```python
# uploader.py (essentials)
from boto3.s3.transfer import TransferConfig

TRANSFER_CONFIG = TransferConfig(multipart_threshold=25 * 1024 * 1024, max_concurrency=4)

def content_key(prefix: str, sha256_hex: str, ext: str) -> str:
    """Pure function of (sha256, normalized extension) — round-4 wording
    correction (risk review round-3 Finding 5): round-3 text overclaimed
    'pure function of sha256' alone; the signature always took `ext` too.
    `ext` is normalized (lowercased, derived from the same media-extension
    allowlist §5 already uses) so case variance (.JPG vs .jpg) can't split
    identical content across two keys. Byte-identical content implies the
    same underlying format/header almost by construction, so a genuine
    extension mismatch for identical bytes is not a realistic case — covered
    by an explicit `test_dedup.py` assertion rather than further mitigation.
    Same content -> same key regardless of which row computes it, regardless
    of processing order, regardless of whether the local state DB has ever
    seen this content before (the round-2 Critical fix)."""
    return f"{prefix}/content/{sha256_hex}{ext.lower()}"

def pointer_key(prefix: str, zip_basename: str, entry_name: str) -> str:
    """Round-4 fix (risk review round-3 Finding 1 — High): must include the
    SAME disambiguator row `id` uses (§5: sha256(basename(zip_path) + '::' +
    entry_name)), not entry_name/relative-path alone. The round-3 draft of
    this function dropped that disambiguator and reconstructed the key from
    zip_relative_path only — safe within one coherent Takeout export session,
    but §5 explicitly endorses adding more zip parts to --source later, and
    research.md §2 documents Google's date-bucket/counter naming as unstable
    across export requests. Two different rows from two different export
    sessions could otherwise compute an identical pointer_key and silently
    clobber each other's pointer/metadata object forever (each retry
    re-corrupts it again — worse than a one-time bug, since it never
    converges). Folding in zip_basename inherits the exact same, already-
    documented, already-accepted limitation `id` has (§5: keep zip filenames
    unchanged for the duration of a backup) instead of introducing a new,
    silent one."""
    return f"{prefix}/library/{_sanitize(zip_basename)}/{_sanitize(entry_name)}.pointer.json"
    # Note: this now takes exactly the same two inputs (zip_basename,
    # entry_name) as row `id` itself (§5). Two rows can only collide on
    # pointer_key/metadata_key if they would *also* collide on id — and an id
    # collision is already handled at discovery time by INSERT OR IGNORE
    # (same id = same row, never two rows). No separate collision guard is
    # needed: uniqueness is inherited directly from the row identity scheme,
    # not re-derived independently the way the round-3 draft did.
    #
    # Round-4 advisory fix (risk review round-4, residual on Finding 1):
    # `id` hashes the two raw strings verbatim; `_sanitize` must therefore
    # REJECT a malformed entry_name (leading '/', any '..' segment) — mark
    # the row `failed` with a clear "unsafe path in zip entry" error — rather
    # than silently collapsing it to some normalized form. A collapsing
    # sanitizer would be a many-to-one transform `id`'s raw hash doesn't
    # apply, reopening a (contrived, adversarial-input-only) collision this
    # function's own uniqueness argument depends on being false. Reject, not
    # collapse — this also removes the "even though S3 has no traversal
    # semantics to escape into" caveat entirely: there's no longer any path
    # left where a `..`/leading-`/` entry name reaches key construction at
    # all.

def upload_content_if_missing(s3_client, bucket, key, spooled_file, sha256_hex, size_bytes, storage_class) -> bool:
    """Returns True if bytes were actually transferred, False if the content
    was already present (dedup hit). HEAD-then-PUT is not perfectly atomic,
    but because `key` is a pure function of `sha256_hex`, the only possible
    race is two workers uploading *identical* bytes to the *same* key
    concurrently — self-correcting (S3 just stores the same bytes twice under
    one key, no duplicate object, no data loss), and further reduced to a
    single winner by the per-sha256 in-process lock in §7."""
    if already_uploaded(s3_client, bucket, key, sha256_hex):
        return False
    s3_client.upload_fileobj(
        spooled_file, bucket, key,
        ExtraArgs={
            "StorageClass": storage_class,
            "ServerSideEncryption": "AES256",
            "ChecksumAlgorithm": "SHA256",  # S3-native, server-validated against the transferred
                                             # bytes — catches transport corruption that a
                                             # client-only metadata field cannot (risk review H6)
            "Metadata": {"sha256": sha256_hex},
        },
        Config=TRANSFER_CONFIG,
    )
    return True

def upload_pointer_and_metadata(s3_client, bucket, pointer_key, content_key, sha256_hex, size_bytes, metadata_dict=None, metadata_key=None):
    """Always runs, for every row, dedup hit or not — small JSON PUTs, cheap
    even at scale. Gives every occurrence (including duplicates) its own
    full path-based pointer and its own full sidecar metadata, resolving
    risk review M3 as a structural side effect rather than an accepted
    limitation: metadata is no longer 'whichever occurrence won the race'."""

def already_uploaded(s3_client, bucket, key, sha256_hex) -> bool:
    """Idempotency check: HEAD, compare stored sha256 metadata. Used for the
    content object (pure function of sha256) and independently for each
    row's own pointer/metadata objects (pure function of that row's path)."""
    try:
        head = s3_client.head_object(Bucket=bucket, Key=key)
    except s3_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
    return head.get("Metadata", {}).get("sha256") == sha256_hex

def verify_uploaded(s3_client, bucket, rows):
    """Bulk re-check for `gphotos2s3 verify` (consistency review #1 — owned
    here, not in cli.py or report.py): HEAD each 'uploaded' row's content,
    pointer, and (when present) metadata objects, compare sha256; yields
    (row, mismatch_reason) for anything that doesn't match, without
    re-uploading."""
```

- **Three objects per row, two of which are shared/deduplicated by design**: `content_key` (the actual bytes — one per unique `sha256`, uploaded once regardless of how many albums reference it), `pointer_key` (a tiny JSON pointer `{sha256, content_key, size}` at the original Takeout path — one per row, always, so the album/date folder structure is still fully browsable in S3 without physically duplicating bytes), and `metadata_key` (the full parsed sidecar JSON — one per row *that had a sidecar*, tracked via `metadata_status`, §4). This directly resolves risk review M3 (previously an accepted limitation: "which occurrence's metadata wins is non-deterministic") — every occurrence now keeps its own metadata, at negligible cost, because only the large content object is ever deduplicated.
- A row's `status` is `uploaded` once content (ensured present) + its own pointer + its own metadata (if applicable) are all confirmed — independent HEAD checks, no shared mutable "canonical" state anywhere.
- `botocore.config.Config(retries={"mode": "adaptive", "max_attempts": 10})` set on the S3 client for transient-error resilience. **Attempt accounting** (risk review F10/H3): one call to `upload_fileobj` — regardless of how many times botocore retries internally — counts as exactly one state-machine `attempts` increment; `--max-attempts` (default 5) bounds *that* counter independently of botocore's internal retry count, so a permanently-broken entry (e.g. a corrupt zip member) reaches `failed` within one `run` invocation rather than looping.
- **Systemic vs. per-file failure classification, thread-safe and tested** (risk review H3 — High; round-2 found this unspecified under concurrency and untested; round-3 found the exact-type-match design itself could mask a real outage — both closed here). A single `SystemicFailureTracker` object, owned by `pipeline.py`, guards one aggregate counter with one `threading.Lock`. **Round-4 fix (Finding 2)**: the counter increments on **any** classified-systemic error type — not only on a repeat of the *same* subtype (which let a mixed-subtype outage under `--workers > 1` perpetually interrupt its own streak and never halt, the opposite of the mechanism's purpose). **Round-4 hardening (residual on Finding 2, per the final review round)**: classification is a **denylist, not an allowlist** — any exception that survives botocore's own adaptive retry (`max_attempts: 10`, already absorbing most transient/throttling conditions before they ever reach this layer) is treated as systemic **by default**, except a small, explicit, genuinely content-specific set that is about *that one file*, not the environment: a corrupt/CRC-failed zip entry (§5) and the oversized-key edge case (§6's key-length truncation only fails if truncation itself somehow still collides, effectively never). The original allowlist design (`EndpointConnectionError`, `OSError`/`ENOSPC`, `AccessDenied`) would have silently excluded any *unenumerated* botocore error type from systemic accumulation — a narrower version of exactly the failure mode Finding 2 named, just reached through an unlisted error type instead of a subtype mismatch. Inverting to a denylist removes the enumeration-completeness problem structurally instead of requiring the list to be kept exhaustively up to date against botocore's error taxonomy. A **non-systemic** (denylisted, content-specific) per-file error resets the counter to 0, since that's real signal the run is otherwise healthy. The halt check (`count >= threshold`, default 5) happens inside the same locked critical section as the increment, so the halt decision itself cannot race.
  - **Attempts semantics (round-4, Finding 3)**: systemic vs. per-file cannot be distinguished before the threshold is reached, so failures #1 through #(threshold−1) are treated as ordinary per-file failures — `attempts` is incremented and the row marked `failed` normally, exactly like any other failure, because at that point there is no signal yet that anything unusual is happening. The moment the count crosses the threshold, the halt fires immediately; only rows that had **not yet reached a terminal failure decision at that instant** are spared — those are reset to `pending` with `attempts` untouched. Earlier rows in the same streak that already completed their normal failure bookkeeping before the threshold crossed keep their `attempts` increment; this is a stated, deliberate limitation (systemic detection is inherently retrospective), not an oversight.
  - **Halt propagation under concurrency (round-4, Finding 4)**: `pipeline.py` dispatches work incrementally — a bounded pool of at most `--workers` in-flight futures, refilled one at a time, checking a shared `threading.Event` (`halt_event`) before each new submission. On halt, `halt_event` is set: no new row is ever submitted, but futures already running are allowed to finish naturally (not killed mid-transfer, avoiding a fresh crash-safety edge case); any in-flight task that fails *after* `halt_event` is set is treated as a streak member per the attempts rule above (reset to `pending`, not touched), not as an ordinary failure.
  - Covered by `test_pipeline_halt.py` (§10), extended in round 4 to include a **mixed-subtype streak** (not just one repeated exception type) and an **in-flight-at-crossing-moment** case under `workers >= 2`, asserting: the halt triggers at the threshold regardless of subtype mixing, the message is specific and actionable, and `attempts` bookkeeping matches the precise semantics above (incremented for pre-threshold failures, untouched for spared rows). Disk exhaustion (risk review M6) is explicitly one of the classified systemic conditions, not a generic per-file error.
- Key hardening rules for `pointer_key`/`metadata_key` (`content_key` is exempt — it never incorporates any path component, only `sha256`+`ext`): (a) **reject, not collapse** (risk review M5/L4, hardened round-4 per the round-4 advisory above) — a leading `/` or any `..` path segment in `entry_name` marks that row `failed` with a clear "unsafe path in zip entry" error rather than being silently stripped/normalized, which both closes a real defense-in-depth gap (S3 itself has no traversal semantics to escape into, but a collapsing sanitizer is still a many-to-one transform worth refusing outright rather than trusting) and preserves `pointer_key`'s uniqueness argument (its docstring in §6) that depends on `_sanitize` treating its input exactly as strictly as `id`'s own raw hash does; (b) S3's 1024-byte key length limit — a `pointer_key`/`metadata_key` that would exceed it is deterministically shortened (truncate the path tail, append an 8-char hex suffix of the row's own `sha256` to keep it unique) rather than left to fail every retry identically.
- **Spooled temp file ownership** (risk review F11): `pipeline.py` owns the `SpooledTemporaryFile` returned by `hashing.spool_and_hash()` end-to-end via `try/finally`, closed on every path (content already deduped, uploaded, or failed) — never left to an implicit caller contract.
- **Shared S3/STS client construction** (consistency review #7): a single `build_s3_client(profile, region)` helper (owned by `aws_credentials.py`, since it already owns profile resolution) is used by both `wizard.py` (bucket validate/create) and `uploader.py`/`pipeline.py` (HEAD/upload), so retry policy and region resolution can't drift between the two call sites.

## 7. Dedup

**Round-3 redesign** (closes the round-2 Critical finding, for content storage — see round-4 note below): dedup is now a **structural consequence of content-addressed keys** (§6), not a stateful decision made at upload time. `content_key = f(sha256, ext)` is a pure function — any row, on any run, with or without a local state DB, independently arrives at the same answer for "where does this content live in S3." There is no more "canonical row" concept for content, so there is nothing for a state-DB loss or a worker race to get wrong about *which* row owns that decision. This is what actually closes the round-2 finding for content bytes — the round-1 fix (a claim-lock around a runtime-assigned canonical row) reduced the race's likelihood but could not close it, because the underlying design still had a stateful, order-dependent notion of "canonical" for the round-2 reviewer to find a hole in.

**Round-4 correction (risk review round-3 Finding 1 — High)**: applying the same "is this key really unique/ownerless" scrutiny to `pointer_key`/`metadata_key` (introduced by the round-3 redesign itself) found they had quietly kept a path-only derivation, without the `zip_basename` disambiguator row `id` deliberately includes for exactly this reason (§5) — a real, not hypothetical, collision risk across independently re-requested Takeout exports. Fixed in §6: `pointer_key`/`metadata_key` now take `zip_basename` explicitly and are never shared across rows, matching `id`'s own uniqueness scheme rather than a weaker one. This is the correct general lesson from round 3→4: a "pure function, no race possible" claim needs to be checked against *every* key the redesign introduces, not just the one the previous round's finding was about.

- Default **on**. `pipeline.py` (consistency review #F6) computes each row's `content_key` from its `sha256` once hashed, calls `uploader.upload_content_if_missing()` (§6), and always calls `uploader.upload_pointer_and_metadata()` regardless of whether the content was a dedup hit — `content_deduped` (§4) is set to `True` purely for reporting when the content PUT was skipped.
- **In-process per-sha256 lock — now an efficiency optimization, not a correctness requirement** (risk review H2, re-scoped after the round-3 redesign): with `--workers > 1`, two threads hashing two different rows with identical content could both HEAD-miss `content_key` in the same instant and both PUT — because the key is content-addressed, this produces one redundant re-upload of identical bytes to the *same* key (wasted bandwidth/API cost), never a second stored object and never data loss (§6's `upload_content_if_missing` docstring states this explicitly). The lock still exists to avoid that redundant bandwidth: `dict[sha256, threading.Lock]` (one lock per content hash, created lazily, guarded by a small top-level lock), held for the **entire** content-check-and-upload sequence — acquired before the HEAD check, released only after the upload (or the dedup-hit skip) fully completes, never just around the initial status transition — so a second worker arriving for the same sha256 always observes the finished result, not a half-finished one.
- `--no-dedupe` disables the content-level HEAD-skip (every row's content is force-uploaded to its own `content_key` even if identical bytes already exist there — a no-op re-PUT, since the key is still content-addressed) for users who want to guarantee every occurrence is independently verified end-to-end rather than trusting a prior HEAD match.
- Report (`report.py`) surfaces bytes saved by dedup (`bytes_deduped`/`files_deduped`, §4) in the run summary.
- Per-occurrence metadata preservation (previously accepted as limitation M3) is now solved structurally, not documented as a trade-off — see §6.

## 8. CLI surface (`cli.py`)

```
gphotos2s3 init                 # run the setup wizard (also auto-runs on first `run` if unconfigured)
gphotos2s3 run                  # discovery + upload loop, resumable, Ctrl+C safe
gphotos2s3 status               # print counts by status, bytes uploaded/remaining, last run summary
gphotos2s3 verify                # re-HEAD every 'uploaded' row's content/pointer/metadata objects,
                                  # report mismatches by marking them 'verify_failed' (no re-upload here)
gphotos2s3 retry-failed          # reset 'failed' AND 'verify_failed' rows (below --max-attempts) to
                                  # 'pending', run (risk review M2 — verify now has a remediation path)
gphotos2s3 run --reconfigure     # re-run the wizard before running
gphotos2s3 run --no-dedupe --workers 4 --source /path/to/takeout/dir
gphotos2s3 run --profile my-second-account   # AWS profile name override (see §11 — default is
                                              # derived per --state-dir instance, architect review F9)
```

Progress reporting via `rich.progress` (files done/total, MB uploaded, ETA); every subcommand is safe to interrupt with Ctrl+C — the state DB is the only thing that matters on the next invocation. `run` and `retry-failed` additionally acquire the PID lock described in §4 before doing anything else, and refuse to start (with a clear message, not a silent hang) if another live instance already holds it for that `--state-dir`.

## 9. README.md rewrite (product-facing)

New sections: what it does, install (`pip install gphotos2s3` once published / `pip install -e .` from source), quick start (3 commands: `init`, `run`, `status`), how idempotency/resume works (short version of research.md §4, for user trust), cost notes (Glacier IR trade-offs, per research.md §3), minimum-privilege IAM policy pointer (`docs/iam-policy-example.json`, now split setup-vs-operate per §11), FAQ (why not delete from Google Photos automatically → intentional, see scope), and a short "Built with Spec-Driven Development" footer linking to `spec/design/00_pipeline_tiers.md` and `spec/feat/google-photos-s3-backup/plan.md` for contributors who want the full decision record. License: MIT.

Also documents, explicitly rather than leaving to discovery (folding in review findings that are policy/communication, not code, fixes):
- **Don't rename or move your Takeout zip files to a different filename while a backup is in progress** — moving them between folders is fine, renaming breaks resumability tracking for that file (§5, architect review F5).
- **What's preserved when the same photo appears in multiple albums**: content bytes are uploaded once (dedup, §7) via a content-addressed key; every album's occurrence still gets its own small pointer + its own full sidecar metadata (favorited flag, people tags, that album's context) — nothing about which occurrence "wins" (risk review M3, resolved structurally in the round-3 redesign, §6).
- **What's in the companion metadata JSON**: GPS coordinates, descriptions, and people/face-tag data ride along verbatim from Google's sidecar into your S3 bucket (risk review L2) — the bucket defaults (`BlockPublicAccess`, SSE-S3) keep this private, but it's your data, stated plainly.
- **If you delete/lose your local state database**: rediscovery + rehashing correctly reconstructs upload status against S3 (research.md §4's "S3 is the ultimate source of truth" claim, now covered by `test_state_rebuild.py`, §10), but per-file failure history for permanently-broken files is lost and such files are simply retried again (risk review M8).

## 10. Testing plan

`pytest` + `moto` (`mock_aws`), no real network/AWS/Google access anywhere in the suite.

| Test file | Covers |
|---|---|
| `test_discovery.py` | Media filtering, both JSON sidecar naming schemes, truncated-name fallback pairing, multi-zip input, re-run does not duplicate rows, `basename`-only id survives relocation (architect F5/consistency #2), corrupt/truncated zip at the **archive level** is isolated and reported without aborting other `--source` entries, **and separately a corrupted entry inside an otherwise-valid zip** marks only that one row `failed` without affecting sibling entries (risk H4 — round-2 gap: entry-level case was specified in §5 but had no explicit test row until now) |
| `test_state.py` | Status transitions (including `metadata_status`, `verify_failed`), `INSERT OR IGNORE` idempotency, `schema_meta`/migration-runner no-op path (architect F8), **concurrency**: N threads writing distinct rows under WAL mode with no `database is locked` and no lost writes (architect F3) |
| `test_hashing.py` | Streaming hash correctness vs. reference `hashlib`, spill-to-disk path exercised with a small `max_memory_bytes`, zero-byte file hashed/handled like any other (risk L1) |
| `test_uploader.py` | `already_uploaded` HEAD logic (match / mismatch / 404) for content/pointer/metadata objects independently, `verify_uploaded` bulk-check (consistency #1), `ChecksumAlgorithm="SHA256"` + storage class + `ServerSideEncryption` set correctly on `moto`'s mock bucket **using a fixture file large enough to cross `multipart_threshold` (>25MB), not just a small single-part file** (risk H6 round-2 note), pointer/metadata objects written for every row incl. duplicates, S3 key length truncation for an overlong path and path-traversal segment stripping (risk M5/L4) |
| `test_metadata.py` | Sidecar parsing tolerant of missing/extra keys, **value-correctness** of `taken_at` normalization against known Google Takeout timestamp samples, not just presence/absence (risk M7) |
| `test_dedup.py` | Second occurrence of identical content reuses the same `content_key`, gets its own **distinct** `pointer_key`+`metadata_key` (round-4, Finding 1 — asserted distinct even when both occurrences share the same `entry_name` string across two different zip parts), only one S3 PUT of the actual bytes observed; **concurrent-worker race**: two threads given identical content simultaneously never produce two stored content objects — content-addressing (§6/§7 round-3 redesign) makes this true even without the lock, and the test asserts it explicitly with the lock disabled as well as enabled (risk H2); **extension consistency** (round-4, Finding 5): two occurrences of byte-identical content with differing filename case (`.JPG` vs `.jpg`) resolve to the same normalized `content_key` |
| `test_pipeline_resume.py` | **Rewritten per risk review C1 (Critical)** — the original "kill after N files" design never exercised reconciliation because it only kills at a clean file boundary. Now injects failure *inside* the transfer itself, for both dangerous sub-cases: (a) S3 receives the object but the local DB commit is interrupted before recording `uploaded`; (b) mid-multipart with no visible object yet (orphaned multipart upload). Asserts `pipeline.reconcile_stuck_rows` resolves each correctly on the next run — (a) to `uploaded` without re-transferring, (b) to `pending` and retried — and that no file is ever uploaded twice |
| `test_pipeline_halt.py` | **New (risk review H3, round-2 gap); extended round-4 per Findings 2–4** — (a) a mocked S3 client raising a **fixed** exception type N times past threshold asserts the run halts, message is clear, `attempts` bookkeeping matches the precise pre/post-threshold semantics (§6); (b) a **mixed-subtype** streak (e.g. alternating `EndpointConnectionError`/`AccessDenied`) still halts at the aggregate threshold — closes round-3 Finding 2; (c) under `workers >= 2`, an in-flight task that fails just after `halt_event` is set is confirmed treated as a spared streak member, not a normal failure — closes round-3 Finding 4; (d) counter increment+check is thread-safe under concurrent workers (no lost/doubled increments) |
| `test_state_rebuild.py` | **New (risk review H8); round-2 re-review required `--workers > 1` + explicit content-object-count assertion (added); round-3 re-review found this still didn't cover the pointer/metadata collision class (Finding 6) — extended round-4.** Now: run with `workers >= 2`, delete/replace the state DB mid-library (including content that has duplicate occurrences already uploaded), rerun discovery + upload, assert **total distinct content objects in the mock bucket is unchanged** (no duplicate content object created under a different key), **and** feed two independent zip sources whose relative paths collide but whose zip basenames and content differ, asserting both rows resolve to distinct `pointer_key`/`metadata_key` with correct per-row content (round-4, closes Finding 1/6) |
| `test_locking.py` | **New (risk review H1)** — a second `run` invocation against a state dir already locked by a live PID refuses to start with a clear error; a lock file left by a dead PID is reclaimed; the acquisition itself is asserted to use `O_CREAT\|O_EXCL` (round-2 atomicity fix), not a check-then-write pair |
| `test_wizard.py` | Mocked stdin sequence → correct `config.json` + `~/.aws/credentials` profile written with `0600` perms; bucket-exists vs bucket-create branches; secret entry uses `getpass` (risk H5); **pre-existing unrelated `~/.aws/credentials` profile survives** `init`/`--reconfigure` untouched (architect F4/risk M4); credentials are not written to disk when bucket validation fails (risk L5); no secret string leaks into `config.json`/state DB/captured logs (risk H7) |
| `test_cli.py` | Subcommand wiring, `--reconfigure`, `--profile`, `status`/`verify` output shape, `retry-failed` picks up both `failed` and `verify_failed` rows |

Lint/format: `ruff check` + `ruff format`. Type checking: `mypy src/gphotos2s3` (annotated code throughout, no bare `Any` in public function signatures). All four (`pytest`, `ruff check`, `ruff format --check`, `mypy`) must pass before any task in §13 is marked done, per `docs/quality-and-verification.md`.

## 11. Security considerations

- AWS secret material only ever touches `~/.aws/credentials` (standard SDK-recognized location, chmod'd `0600` after write) — never logged, never written into `config.json`, never included in any error message or the SQLite state DB. **Automated, not just manual, enforcement** (risk review H7 — High): `test_wizard.py` and `test_uploader.py` assert the literal secret string used in test fixtures never appears in `config.json`, the state DB file, or any captured log/exception output — a real regression test, not a one-time grep.
- **Secret entry is no-echo** (risk review H5 — High): the wizard collects the AWS Secret Access Key via `getpass.getpass()`, never plain `input()` — the target audience (non-technical, possibly following a screen-recorded tutorial or pasting terminal output into a support chat) is a realistic leak vector for plain-echo entry. `test_wizard.py` asserts `getpass` is the code path used.
- **Credential file writes are read-merge-write, never a blind overwrite** (architect review F4 — High, risk review M4): `aws_credentials.py` parses the existing `~/.aws/credentials` with `configparser`, updates only its own named section (`[gphotos2s3]` by default), and preserves every other section's data (not a literal byte-for-byte guarantee — `configparser`'s rewrite doesn't promise to keep unrelated comments/formatting, only the key/value data, round-2 wording correction). `~/.aws/credentials` is a shared, systemwide file other tools/projects may already populate — a naive overwrite destroying a user's unrelated AWS profile(s) would be a severe blast-radius bug for a distributable OSS tool. `test_wizard.py` gains an explicit case: run the wizard against a fixture `~/.aws/credentials` that already has an unrelated `[other-profile]` section, assert it survives untouched after `init`/`--reconfigure`.
- **Region is stored in `config.json`, not `~/.aws/config`** (architect review F7 — Medium, resolved by decision rather than left open): region is non-secret, passed explicitly as `boto3.Session(region_name=...)` from `config.json`'s value. `aws_credentials.py`'s file-parsing responsibility is therefore scoped to exactly one file (`~/.aws/credentials`), not two, keeping its read-merge-write logic simpler and its blast radius smaller.
- **Validate before persisting** (risk review L5): the wizard attempts the bucket HEAD/create call with the entered credentials *in memory* first; credentials are written to `~/.aws/credentials` only after that validation succeeds. A failed validation never leaves partially-tested credentials on disk.
- **Profile name is parameterized, not fixed** (architect review F9 — Medium): default AWS profile name is derived from `--state-dir` (e.g. `gphotos2s3-<state-dir-basename>`) rather than a single hardcoded `gphotos2s3`, and `--profile` (§8) overrides it explicitly. Two independent instances (e.g. backing up two Google accounts to two buckets) no longer default to silently overwriting each other's credentials on `--reconfigure`.
- **Two-tier IAM policy, not one** (risk review M1 — Medium): the wizard/`iam_policy.py` prints a **setup** policy (adds `s3:CreateBucket`, `s3:PutLifecycleConfiguration`, `s3:PutBucketPublicAccessBlock`, `s3:PutEncryptionConfiguration` — needed only if the user asks the wizard to create the bucket) separately from the smaller **operate** policy used for every subsequent run (`s3:PutObject`, `s3:GetObject` — required because `HeadObject`, used throughout for idempotency checks, is authorized under the `s3:GetObject` action per AWS's own IAM reference, not a leftover — `s3:ListBucket`, `s3:AbortMultipartUpload`, `s3:ListMultipartUploadParts`). A user who scopes their key to "operate" only, after using the wizard's create-bucket path once with broader credentials, is no longer surprised by `AccessDenied`.
- Bucket creation default: `BlockPublicAccess` fully enabled, `AbortIncompleteMultipartUpload` lifecycle rule attached automatically, encryption at rest (SSE-S3, `AES256`) set by default on every `PutObject` call (also now the S3-native checksum, §6).
- No secrets in logs: uploader/pipeline logging redacts anything resembling an access key pattern as defense-in-depth, even though secrets should never reach that code path.
- Local state DB and config live under the user's home directory with default `0700` directory permissions (`~/.gphotos2s3/` by default, overridable via `--state-dir`).

## 12. Multi-agent review cycle

Per `AGENTS.md` "Multi-agent review cycle" and `spec/design/00_pipeline_tiers.md` Tier 2 guidance (credentials + data-integrity risk ⇒ review recommended): this plan is reviewed by **architect-reviewer → consistency-reviewer → risk-analyst** before implementation begins. Verdicts and any resulting plan changes are recorded as an addendum to this section before §13 execution starts. This plan has no prior codebase pattern to be consistent *with* (greenfield repo) — the consistency reviewer's focus here is internal consistency of the plan itself and alignment with this repo's own template conventions (file layout under `spec/feat/`, changelog/skill usage), not existing app code.

### Review outcome — round 1

- **architect-reviewer**: **Needs revision.** 1 Critical (F1: metadata companion object had no state-machine representation — silent, undetectable, permanent loss possible), 3 High (F2: reconciliation logic duplicated across `state.py`/`uploader.py`, wrong module boundary; F3: SQLite concurrency strategy under `--workers N` unspecified; F4: credential-file write semantics risked clobbering unrelated `~/.aws/credentials` profiles), plus Medium/Low F5–F12 (path-based row identity fragile against relocation, dedup-check ownership unassigned, region-storage location unspecified, schema migration promised but undesigned, profile name not parameterized per instance, attempts-vs-botocore-retry interaction undefined, spooled-file cleanup ownership unstated, zip-handle lifecycle misplaced in the checklist).
- **consistency-reviewer**: **Pass with advisories.** No Critical/High. Medium: `verify` subcommand's logic had no owning module; `id` scheme said "zip filename" in research.md but hashed the full `zip_path` in plan.md (a real, not cosmetic, mismatch given the resumability guarantee both documents make); review-cycle gate not encoded as a checklist phase/acceptance criterion, unlike this repo's only precedent plan; `iam_policy.py` and the static `docs/iam-policy-example.json` had no mechanism keeping them in sync. Several Low advisories (terminology, shared client factory, docs/ folder audience mixing, changelog tag reminder).
- **risk-analyst**: **Needs revision.** 1 Critical (C1: `test_pipeline_resume.py` killed the run only at a clean file boundary, never exercising the reconciliation logic it exists to test — the single riskiest code path was untested), 8 High (H1 no cross-process lock; H2 dedup check-then-act race across concurrent workers; H3 no systemic-vs-per-file failure classification; H4 corrupt/truncated zip handling unspecified and untested; H5 wizard secret entry didn't specify no-echo input; H6 integrity relied on client-only metadata, not S3-native validated checksums; H7 the "no secrets anywhere" acceptance criterion had no automated regression test; H8 the plan's own central resilience claim — S3 as source of truth even after full state-DB loss — was untested), plus Medium/Low M1–M8/L1–L6 (two-tier IAM policy needed for the wizard's own bucket-creation feature; `verify` had no remediation path; non-canonical duplicate metadata is order-dependent and unrecoverable; unrelated-profile preservation unstated; S3 key length limit unaddressed; disk exhaustion not classified as systemic; timestamp-normalization correctness untested; failure history lost on DB rebuild; several Low advisories).

**All findings above were resolved by revising this plan document** (§4, §5, §6, §7, §8, §9, §10, §11 — see the inline callouts through those sections tagged with each finding's ID) rather than deferred, with two explicit, intentional exceptions stated as documented product limitations rather than code fixes: risk M3 (non-canonical duplicate metadata is order-dependent — a v2 concern, not a v1 correctness bug) and risk M8 (failure history lost on full state-DB rebuild — an accepted trade-off of using SQLite as a disposable index rather than the sole source of truth). No finding was silently dropped.

### Review outcome — round 2 (risk-analyst re-review)

**Needs revision.** Seven of the eight round-1 High/Critical findings were confirmed genuinely closed (C1's test rewrite, H1, H2, H4, H5, H6, H7 all held up under scrutiny — see below). But the round-1 fix for H8/dedup introduced a **new Critical finding**: the round-1 design still assigned "canonical row" status at upload time based on runtime processing order (which row's own path-based key happened to be checked first), so after a full state-DB loss combined with `--workers > 1`, a *different* row could become "canonical" than in the original run, leaving the original run's object orphaned under its old key while the content gets re-uploaded under a new one — silent duplicate storage, undermining both the README's resilience claim and the tool's core cost-savings purpose. Also found: H3 (systemic-failure classification) was specified in prose but had no named test and left thread-safety of its own counter unspecified — inconsistent with every other H-finding's 1:1 test mapping. Plus Medium/Low: H4's entry-level corruption case had no test row (only the archive-level case did); H1's lock acquisition was check-then-write, not atomic; H6's test didn't specify a multipart-sized fixture; F4's "byte-for-byte" wording overstated `configparser`'s actual guarantee; H2's lock-hold-duration wasn't explicit about covering the full transfer, not just the initial status transition.

**Root-caused and fixed, not patched**: the new Critical finding could not be closed by tightening the lock further (that was already tried in round 1 and still had a hole) — it required removing the "canonical row" concept from the design entirely. §6/§7 were redesigned around **content-addressed S3 keys** (`content_key = f(sha256)`, a pure function independent of any row, any processing order, and any local state): dedup correctness no longer depends on *which* row runs first, so there is nothing left for a concurrent race or a state-DB loss to get wrong about ownership. This is documented inline in §4/§6/§7 as the "round-3 redesign," and has the further benefit of resolving risk review M3 (per-occurrence metadata preservation) structurally rather than as an accepted trade-off. H3 gained an explicit thread-safe design (single locked counter, halt check inside the same critical section) and a named test (`test_pipeline_halt.py`). The remaining Medium/Low items (entry-level corruption test, lock atomicity via `O_CREAT|O_EXCL`, multipart-sized checksum test fixture, wording correction, explicit lock-hold-duration) were all folded into the same revision pass — see the inline "round-2"/"round-3" callouts through §4–§11.

### Review outcome — round 3 (risk-analyst re-review)

**Needs revision.** Confirmed the content-addressed redesign genuinely closes the round-2 Critical finding **for content storage** — direct walkthrough held up, no duplicate-content-storage path remains. But applying the same "is this key really ownerless" scrutiny to the sibling keys the round-3 redesign introduced found the redesign hadn't been applied consistently: **Finding 1 (High)** — `pointer_key`/`metadata_key` were derived from `zip_relative_path` alone, dropping the `zip_basename` disambiguator row `id` deliberately includes for exactly this reason (§5); across independently re-requested Takeout exports (which research.md §2 documents as producing unstable folder/counter naming), two different rows could silently and *repeatedly* clobber each other's pointer/metadata object — worse than a one-time bug because it never converges to a stable correct state. **Finding 2 (High)** — the `SystemicFailureTracker`'s exact-error-type-match reset logic could let a real mixed-subtype outage under `--workers > 1` perpetually interrupt its own streak and never halt, the opposite of its purpose; `test_pipeline_halt.py` as specified only exercised a homogeneous-type streak. Plus Medium/Low: attempts semantics for the exact N streak-triggering files were unstated (Finding 3); halt propagation to in-flight/already-dispatched workers was unspecified (Finding 4); `content_key`'s "pure function of sha256" claim overstated its actual `(sha256, ext)` signature (Finding 5); `test_state_rebuild.py` didn't yet cover the Finding-1 scenario (Finding 6).

**Fixed in a round-4 revision**, not deferred: `pointer_key`/`metadata_key` now take `zip_basename` explicitly and — since they're now derived from the *exact same two inputs* as row `id` itself — inherit `id`'s uniqueness guarantee directly rather than re-deriving a weaker one (closes Finding 1, no separate collision guard needed). `SystemicFailureTracker` now increments on any classified-systemic error type, not only a repeat of the same subtype (closes Finding 2). Attempts semantics for pre-threshold vs. threshold-crossing failures are now precisely defined (closes Finding 3). Halt propagation is now specified as an incrementally-refilled bounded worker pool checking a shared `threading.Event` before each new dispatch (closes Finding 4). `content_key`'s docstring/prose now correctly states `(sha256, ext)` (closes Finding 5). `test_state_rebuild.py` and `test_pipeline_halt.py` were both extended with the scenarios these findings specifically named (closes Finding 6 and the H3 test gap). See the "round-4" inline callouts in §6, §7, §10, §14.

### Review outcome — round 4 (risk-analyst re-review, final gate)

**Cycle verdict: Complete — Pass with advisories.** Walking both round-3 High findings against the round-4 design: Finding 1 (pointer/metadata key collision across independently re-requested Takeout exports) is closed — `pointer_key`/`metadata_key` now fold in `zip_basename`, and two rows from different export sessions sharing an `entry_name` now produce distinct `id`s **and** distinct pointer/metadata keys, confirmed directly against the named scenario. Finding 2 (systemic classifier perpetually reset by subtype-mixing) is closed — the counter now accumulates across any classified-systemic type, confirmed against the named mixed-subtype scenario. Findings 3–6 (attempts semantics, halt propagation, `content_key` wording, `test_state_rebuild.py` coverage) were all independently confirmed closed, each against a test that reproduces the finding's own scenario rather than a generic regression check.

Two Low advisories, folded into the plan rather than requiring a further round: (a) `pointer_key`'s uniqueness argument ("collides only if `id` also collides") assumed `_sanitize` and the raw `id` hash treat malformed path segments (`..`, leading `/`) identically — they didn't, quite. **Resolved below**: `_sanitize` is specified to *reject* (mark the row `failed` with a clear error) rather than silently *collapse* a malformed entry name, removing the asymmetry entirely rather than just documenting it. (b) `SystemicFailureTracker`'s three named error categories are an allowlist, so a real outage manifesting as an unenumerated botocore error type would fall through to "non-systemic, reset to 0" by default — reopening a narrower version of the original problem through an unlisted door. **Resolved below**: the classifier is inverted to a denylist — any exception that survives botocore's own adaptive retry is treated as systemic by default, *except* a small, explicit set of genuinely content-specific errors (corrupt zip entry, oversized-key edge case) that are about that one file, not the environment.

No further review round required — both advisories are closed by the two edits below, and neither reopens a scenario a reviewer walked through and found real.

## 13. Implementation checklist

### Phase 0 — review cycle gate
- [x] architect-reviewer round 1 verdict recorded (§12) — needs-revision, addressed above
- [x] consistency-reviewer round 1 verdict recorded (§12) — pass-with-advisories, addressed above
- [x] risk-analyst round 1 verdict recorded (§12) — needs-revision, addressed above
- [x] risk-analyst round 2 verdict recorded (§12) — needs-revision (new Critical: dedup-after-DB-loss race), addressed via content-addressed redesign
- [x] risk-analyst round 3 verdict recorded (§12) — needs-revision (2 new High: pointer/metadata key uniqueness gap, systemic-classifier type-flapping), addressed via round-4 fixes
- [x] risk-analyst round 4 verdict recorded (§12) — **Pass with advisories.** Both round-3 High findings confirmed closed against their named scenarios; two Low advisories (sanitize reject-vs-collapse, systemic-classifier allowlist-vs-denylist) resolved inline in §6 rather than requiring a further round. **Gate satisfied — cycle complete, Phase A begins.**

### Phase A — scaffolding
- [x] `pyproject.toml` (hatchling backend, `gphotos2s3` package under `src/`, console-script entry point, deps: `boto3`, `rich`; dev deps: `pytest`, `pytest-cov`, `moto[s3]`, `ruff`, `mypy`, `types-boto3` if available)
- [x] `LICENSE` (MIT)
- [x] `.gitignore` extended (`.venv/`, `__pycache__/`, `*.egg-info/`, `dist/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.gphotos2s3/`, `*.db`)
- [x] `src/gphotos2s3/__init__.py`

### Phase B — state & discovery
- [x] `state.py`: `schema_meta` + migration runner (no-op v1), `files`/`run_log` schema incl. `metadata_status`, WAL mode + `busy_timeout` connection setup, connection-per-thread helper, CRUD/status-transition functions — **no boto3/S3 imports in this module** (architect F2)
- [x] `metadata.py`: sidecar JSON parsing, `taken_at` normalization to UTC
- [x] `discovery.py`: zip walking, media filtering, sidecar pairing (both naming schemes + truncated fallback), `id = sha256(basename(zip_path)+entry_name)`, per-source `zipfile.BadZipFile` isolation, **reject (not collapse) an `entry_name` with a leading `/` or `..` segment** — row marked `failed` (round-4 hardening, §6)
- [x] `hashing.py`: streaming spool+hash, `OSError` (incl. `ENOSPC`) surfaced not raised, zero-byte files handled without special-casing

### Phase C — AWS integration
- [x] `aws_credentials.py`: read-merge-write named profile in `~/.aws/credentials` via `configparser` (preserves unrelated sections), `0600` perms, `getpass` for secret entry, `build_s3_client(profile, region)` shared factory
- [x] `iam_policy.py`: render both the **setup** and **operate** least-privilege policy JSON for a given bucket/prefix; a test/Phase-F step keeps `docs/iam-policy-example.json` equal to its rendered output
- [x] `uploader.py`: content-addressed `content_key`/`pointer_key`/`metadata_key` derivation (round-3 redesign), `upload_content_if_missing`/`upload_pointer_and_metadata`, `already_uploaded`/`verify_uploaded` HEAD checks, multipart upload via `TransferConfig`, S3-native `ChecksumAlgorithm="SHA256"`, storage-class + `ServerSideEncryption` defaults, key traversal-stripping + length truncation — zip file handling lives in discovery/pipeline, not here
- [x] `config.py`: `Config` dataclass (incl. `region`, `aws_profile`), `config.json` load/save, defaults (state dir, prefix, storage class, dedupe on, workers, max-attempts)

### Phase D — orchestration & CLI
- [x] `pipeline.py`: discovery → content-addressed dedup via per-sha256 lock (`dict[sha256, threading.Lock]`, held for the full content-check-and-upload sequence) → always-run pointer/metadata upload → `ThreadPoolExecutor` with per-thread `zipfile.ZipFile`+SQLite connections, `reconcile_stuck_rows` (moved here from state.py per F2), atomic PID lock acquire/release (`O_CREAT|O_EXCL`), `SystemicFailureTracker` (single locked counter, **denylist classification** — systemic by default, except the small explicit content-specific set, round-4 hardening — halt after N accumulated systemic errors, `attempts` not incremented for halted-streak files), `rich` progress, spooled-file `try/finally` cleanup
- [x] `wizard.py`: prompts (Takeout source path(s), AWS Access Key ID/`getpass` Secret/region, bucket name — validate with in-memory credentials **before** persisting, then offer create with lifecycle rule + public-access-block, prefix, storage class, dedupe on/off), preflight free-disk-space check, prints both IAM policy tiers, derives default profile name from `--state-dir`
- [x] `report.py`: `status`/`verify` output formatting, dedup bytes-saved summary, orphaned-multipart-upload visibility note (risk L6)
- [x] `cli.py`: `init`, `run`, `status`, `verify`, `retry-failed` (picks up `failed` + `verify_failed`), `--reconfigure`, `--source`, `--no-dedupe`, `--workers`, `--max-attempts`, `--state-dir`, `--profile`

### Phase E — tests
- [x] `tests/conftest.py`: `moto` S3 fixture, synthetic Takeout zip builder fixture
- [x] `test_discovery.py` (incl. corrupt-zip isolation, basename-id relocation case)
- [x] `test_state.py` (incl. concurrency, migration no-op)
- [x] `test_hashing.py` (incl. zero-byte)
- [x] `test_uploader.py` (incl. verify_uploaded, native checksum, key truncation/sanitization)
- [x] `test_metadata.py` (incl. timestamp value-correctness)
- [x] `test_dedup.py` (incl. concurrent-race case)
- [x] `test_pipeline_resume.py` (rewritten per C1 — mid-transfer kill, not clean-boundary kill)
- [x] `test_pipeline_halt.py` (new — H3, systemic-failure halt + thread-safety)
- [x] `test_state_rebuild.py` (new — H8, full state-DB-loss end-to-end, `workers >= 2`, content-addressing verified)
- [x] `test_locking.py` (new — H1, atomic `O_CREAT|O_EXCL` PID lock acquire/refuse/reclaim-stale)
- [x] `test_wizard.py` (incl. unrelated-profile preservation, getpass, validate-before-persist, no-secret-leak)
- [x] `test_cli.py` (incl. `--profile`, `retry-failed` picking up `verify_failed`)
- [x] `test_iam_policy.py` (new, not originally listed — consistency review #4's `docs/iam-policy-example.json`↔`iam_policy.py` equality check)

### Phase F — docs & housekeeping
- [x] `README.md` rewritten product-facing (§9)
- [x] `docs/iam-policy-example.json`
- [x] `CHANGELOG.md` entry (via `changelog` skill)
- [x] Run `pytest`, `ruff check`, `ruff format --check`, `mypy src/gphotos2s3` — all green
- [x] This `plan.md` outcome note added at top after implementation (per `spec/feat/CONVENTIONS.md`)
- [x] Commit(s) created per current git config, referencing this plan — `fd529c6` on branch `feat/google-photos-s3-backup` (branched off `main` per this session's convention of not committing directly to the default branch)

## 14. Acceptance criteria (mechanically checkable)

1. `pytest` exits 0 with tests covering discovery/pairing (both JSON naming schemes), idempotent re-discovery, content-addressed dedup (incl. the concurrent-worker case, H2, and full state-DB-loss under `--workers >= 2`, H8/round-2-Critical), HEAD-based upload idempotency for content/pointer/metadata objects independently, resume-after-mid-transfer-crash (C1's corrected scenario, not a clean-boundary kill), systemic-failure halting (H3), atomic single-instance locking (H1), and wizard credential persistence (incl. unrelated-profile preservation, H5/H7) — no test hits real AWS or Google endpoints.
2. `ruff check` and `ruff format --check` exit 0.
3. `mypy src/gphotos2s3` exits 0.
4. `gphotos2s3 --help` and every subcommand's `--help` runs without error from an installed (`pip install -e .`) environment.
5. No AWS secret ever appears in `config.json`, the SQLite state DB, or any log line — enforced by an automated test (H7), not only a manual grep.
6. Every uploaded content object carries both the S3-native `ChecksumAlgorithm=SHA256` (H6) and the custom `sha256` metadata field used for idempotency checks.
7. No two distinct S3 keys ever hold identical content bytes — i.e. `content_key` is proven, by `test_state_rebuild.py`, to be a pure function of `(sha256, normalized extension)` under concurrent workers and across a full state-DB loss (round-2 Critical finding, closed by the round-3 content-addressed redesign, §6/§7); and no two distinct rows ever silently overwrite each other's `pointer_key`/`metadata_key` — those keys inherit row `id`'s own uniqueness scheme exactly (round-3 Finding 1, closed round-4, §6).
8. `SystemicFailureTracker` halts on any mix of classified-systemic error subtypes, not only a repeated exact type, and the `attempts`/halt-propagation semantics under concurrent workers are precisely defined and tested (round-3 Findings 2–4, closed round-4, §6/§10).
9. The Phase 0 review-cycle gate in §13 reached a Pass (or Pass-with-advisories-only) verdict from risk-analyst's round-4 re-review before Phase A began — matching this repo's own precedent (`spec/feat/loop-engineering/plan.md` §13/§14).
10. No actual `s3:PutObject`/upload is executed against real AWS during this implementation session — verified by construction (all tests mocked) and by not running the `init`/`run` commands against real credentials.
