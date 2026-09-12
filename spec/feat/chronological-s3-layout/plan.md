# Chronological S3 layout — date-organized keys, no duplication

> **Outcome** [2026-09-06]: Implemented as planned, after one risk-analyst
> review round (Critical: Findings 1 and 2 below, both closed in this
> document before implementation started, not after) and one open finding
> re-verified empirically post-implementation (Finding 6, hang risk — see
> `amendments.md`). One implementation detail deviated from §3.2 as
> drafted (migration locking mechanism, same guarantee) — see
> `amendments.md`. 94 tests pass (`pytest`), lint is clean
> (`ruff check` + `ruff format --check`), typing is clean (`mypy`). Three
> pre-existing `test_cli.py` failures (rich ANSI color codes leaking into
> `capsys` output on this machine) are unrelated to this change — confirmed
> via `git stash` before starting. No real upload was executed against real
> AWS, per this repo's existing testing scope.

## 1. Problem

User tested a real run: upload works, but the S3 layout is hard to browse.
`content/{sha256}{ext}` is a flat bucket of hash-named files with no dates;
`library/{zip_basename}/{entry_name}.pointer.json` mirrors the original
Takeout export structure (JSON pointers, not the photos themselves). Ask:
rename files to include the captured date/time, and nest them under
`YYYY/MM/DD` folders — "easier to navigate."

## 2. Constraint that shaped this plan

`content_key = f(sha256, ext)` is not a style choice — it is the fix for a
Critical dedup-after-state-loss race (see
`spec/feat/google-photos-s3-backup/plan.md` §6/§7, round-2/round-3): any
row, on any run, with or without local state, must independently arrive at
the *same* answer for "where does this content live in S3." Acceptance
criterion #7 of that plan, tested by `test_state_rebuild.py`, states this
explicitly: "no two distinct S3 keys ever hold identical content bytes."

Two options were rejected during planning specifically because they break
this invariant or its cost basis:

- **Duplicate the bytes at a friendly date path** (real image, real click,
  same content also kept at `content/<hash>`) — rejected: doubles total S3
  storage for *every* unique file (not just true album-duplicates), directly
  undermining the reason content-addressing exists. User explicitly ruled
  this out ("no duplication").
- **Derive the date from Google's sidecar JSON (`photoTakenTime`)** —
  rejected: the sidecar is per-*row* (external, per-occurrence) data, not a
  property of the bytes. Two rows sharing an identical sha256 could in
  principle carry different sidecar dates (rare, but real — e.g. a
  re-exported album with corrected metadata), which would make
  `content_key` occurrence-dependent again and silently defeat dedup for
  that pair. That is a narrower re-opening of the exact class of bug
  round-2 closed, and it would falsify the current, tested wording of
  acceptance criterion #7.

**Chosen approach**: derive the date from metadata **embedded in the file's
own bytes** (EXIF `DateTimeOriginal` for photos, the `mvhd` atom's creation
time for ISO-BMFF video). This is still a pure function of content — the
same bytes always yield the same extracted date, with no external input —
so `content_key`'s pure-function guarantee is preserved *exactly*, not
loosened. Cost: a new dependency for EXIF, and no reliable embedded date
for every format (HEIC, AVI/MKV/3GP) — those fall into an explicit
`unknown-date` bucket rather than a wrong guess. This mirrors this
project's existing style of stating an accepted limitation outright rather
than pretending an edge case doesn't exist (see e.g. "renaming the zip file
is NOT survived" in `discovery.py::compute_id`).

**Round-2 correction (risk-analyst pass, before implementation started)**:
"pure function of content bytes" is true *within one fixed version* of
`content_date.extract_taken_at` — it is not automatically true *across
time*. If that function's logic ever changes (a bug fix, or the
`unknown-date` formats above gaining support later), two rows sharing an
identical sha256 but hashed under different code versions could compute
different `content_key` values — a version-drift reopening of the same
invariant, distinct from but just as real as the sidecar-based one
rejected above. A second, symmetric gap: `reconcile_stuck_rows` (running
against rows left `uploading` by a pre-upgrade version) would compute only
the *new*-scheme key, miss the object actually sitting at the *old* flat
`content/{sha256}{ext}` key, and re-upload — orphaning the original and
creating a second content object on the very first ordinary run after
upgrading. Both are closed below (§3.4a, §3.4b) rather than left as
residual risk, because both are reachable in ordinary (non-adversarial,
non-concurrent) use, not just theoretical corner cases.

## 3. Design

### 3.1 New module: `src/gphotos2s3/content_date.py`

```python
def extract_taken_at(spooled_file: IO[bytes], ext: str) -> datetime.datetime | None:
    """Best-effort extraction of a capture date embedded in the file's own
    bytes. Pure function of content: same bytes -> same return value, always.
    Never raises — any parse failure, unsupported format, or missing tag
    returns None (unknown-date bucket), exactly like metadata.py's stance on
    the external sidecar. Caller owns seek(0) before and after."""
```

- **Photos** (`.jpg .jpeg .dng .cr2 .nef .arw` — JPEG and TIFF-based RAW):
  parse via `exifread` (pure-Python, no C dependency), read
  `EXIF DateTimeOriginal` falling back to `Image DateTime`. The **entire**
  read-tag + parse-to-`datetime` sequence is wrapped in one try/except —
  not just the exifread call. `DateTimeOriginal == "0000:00:00 00:00:00"`
  is a common real-world placeholder (camera/phone with an unset clock) and
  raises `ValueError` on conversion to `datetime`, distinct from an
  exifread parse failure; this must return `None` like any other
  unextractable case, not propagate. An uncaught `ValueError` here would
  reach `pipeline.py`'s generic `except Exception`, which is *not* in the
  content-specific denylist — a handful of such files in one run would
  misclassify as systemic and **halt the whole backup** (`threshold=5` by
  default). This is the single most important defensive-coding note in
  this plan.
- **Video** (`.mp4 .mov .m4v` — ISO-BMFF container): hand-rolled `mvhd` box
  walker (no new dependency). `mvhd` is a **direct child of `moov`**, not a
  top-level sibling of `moov`/`mdat`/`ftyp` — the walker scans top-level
  boxes by declared size (never reading `mdat`'s body), and only when it
  reaches `moov` does it scan *moov's own direct children* (one level, no
  need to recurse into `trak`/`mdia`) looking for `mvhd`. Per ISO/IEC
  14496-12, a box header's 32-bit `size` field can be `1` (real size is an
  additional 8-byte "largesize" field immediately following) or `0` (box
  extends to EOF) — both are handled explicitly; skipping this is exactly
  what would desync the walker on the multi-GB-`mdat`-before-`moov` files
  this design is meant to handle cheaply. `mvhd.creation_time == 0` means
  "not set" per spec and is treated as `None`, same as a missing tag.
  QuickTime epoch (1904-01-01) converted to a `datetime`. **Caveat, stated
  rather than assumed**: the spec defines `creation_time` as UTC, but many
  real-world encoders write local wall-clock time into it regardless: the
  derived date can be off by the recording device's UTC offset on a
  spec-compliant device. Documented limitation, not fixed here (same
  category as the sub-day imprecision `unknown-date` already accepts).
- **Unsupported** (`.png .gif .webp .heic .heif .avi .mov`/`.mp4` without a
  parseable `mvhd`, `.mkv .3gp`): no extraction attempted — return `None`
  outright. Documented limitation, not a bug: these formats either have no
  standard embedded capture-date field (`.gif`, `.webp`) or need a
  dependency/parser this plan deliberately doesn't add for v1 (HEIC/HEIF's
  ISO-BMFF-based EXIF box, AVI's RIFF metadata, MKV's EBML tags). All such
  files land in `unknown-date`, uploaded and byte-correct exactly as
  before — only their location is coarser.
- **Hang risk, not just raise risk**: IFD-chain-based EXIF parsers are a
  known hazard class for self-referencing "offset to next IFD" values
  causing unbounded loops — a failure mode try/except cannot stop. Before
  shipping, run `exifread` against one deliberately circular/malformed IFD
  fixture and confirm bounded runtime; Google Takeout content is the
  user's own (low adversarial risk) but real corruption (partial download,
  bit rot) can trigger this unintentionally.

### 3.2 Schema migration (v1 -> v2)

Add nullable column `files.taken_at TEXT` (naive local datetime, ISO-8601,
no timezone — EXIF/QuickTime dates are camera/device local time with no
reliable offset). Extends `_apply_migrations()`'s existing `if current < N`
ladder — the mechanism was built for exactly this ("a future schema change
never forces 'delete your state DB and lose all resume progress'").

- `FileRow` gets a `taken_at: str | None` field.
- `StateStore.mark_hashed(id_, sha256, size_bytes, taken_at=None)` persists
  it — called once, right after hashing, same call site as today.
- **Why persist rather than re-derive on demand**: `reconcile_stuck_rows`
  must recompute the exact same `content_key` a crashed row would have
  used, without reopening the zip. Today it does this from
  `row.sha256` alone; after this change it reads `row.taken_at` alongside
  it — both already committed by `mark_hashed` before `mark_uploading` ever
  runs, so a stuck row always has both. No zip re-read added to the
  reconciliation path.
- **Migration race (risk-analyst finding, High)**: this is the *first*
  migration this codebase will ever actually execute (v1's ladder was a
  no-op), and `_apply_migrations` runs on every `open_state()` call, not
  only under `cmd_run`'s `ProcessLock` — `status`/`verify`/`retry-failed`
  open the state DB unguarded (`cli.py`). Two processes opening a v1 DB at
  the same moment (e.g. `run` in one terminal, `status` in another, right
  after upgrading) would both see `version == 1` and both attempt
  `ALTER TABLE files ADD COLUMN taken_at TEXT` — the loser crashes with
  `duplicate column name`. Fix: wrap the version-check + `ALTER TABLE` +
  version-write in one `BEGIN IMMEDIATE ... COMMIT` transaction, letting
  the existing `busy_timeout=30000` serialize the two processes (the loser
  blocks, then re-reads `version == 2` and skips the `ALTER`); additionally
  catch `sqlite3.OperationalError` matching "duplicate column" as a
  belt-and-suspenders fallback and treat it as already-applied.

### 3.3 Key functions (`uploader.py`)

```python
def content_key(prefix: str, sha256_hex: str, ext: str, taken_at: str | None) -> str:
    """Still a pure function of the file's own content: sha256+ext identify
    the bytes; taken_at is *itself* deterministically derived from those
    same bytes (content_date.extract_taken_at), never from row/path/sidecar
    data. Same content, any row, any run, any order -> identical key."""
    if taken_at is None:
        return f"{prefix}/content/unknown-date/{sha256_hex}{ext.lower()}"
    yyyy, mm, dd, compact = _date_parts(taken_at)
    return f"{prefix}/content/{yyyy}/{mm}/{dd}/{yyyy}-{mm}-{dd}_{compact}__{sha256_hex}{ext.lower()}"
```

Full `sha256_hex` stays embedded in the filename verbatim (not shortened) —
the date prefix is purely a human sorting/browsing aid layered on top of
the exact same collision-proof identifier used today. This is the key
property that makes the change additive rather than a weakening: nothing
about uniqueness or collision-resistance changes, only the location and a
human-readable prefix.

`pointer_key`/`metadata_key` get the same date-folder treatment for a
consistent, browsable tree (`library/{YYYY}/{MM}/{DD}/...`, falling back to
`library/unknown-date/...`), built from the *same* `taken_at` value so the
two trees (`content/`, `library/`) always agree on which date a given photo
lives under. The filename still embeds `zip_basename` + `entry_name`
exactly as today — the existing uniqueness argument ("collides only if `id`
also collides") is untouched, since those two inputs are still present
verbatim; only a date-folder prefix and a human-readable date/time prefix
on the filename are added. `_truncate_key`'s 1024-byte handling is
unaffected (same mechanism, longer input).

`_date_parts()` parses the persisted ISO string via
`datetime.fromisoformat()`, not fixed-width slicing (the string's width
varies with/without a time component), and is only ever used as a
formatting step — never round-tripped through `.astimezone()` or any
timezone-aware conversion, since the value is a naive device/camera local
time with no reliable offset (DST is a non-issue as long as this stays a
formatting-only string, which future changes to this function must
preserve).

**RAW-file memory note (risk-analyst Medium finding)**: unlike the video
walker's explicit "never reads the whole file" property, pure-Python EXIF
parsers commonly buffer for random IFD access — a `.dng`/`.cr2`/`.nef`/
`.arw` file can be tens-to-hundreds of MB, and `config.workers` threads
parsing large RAW files concurrently adds memory pressure on top of the
already-spooled copy. Verify this against `exifread` specifically during
implementation; if it buffers the whole file, note it as an accepted cost
(same order of magnitude as the existing spooled copy, not a new class of
resource use) rather than adding a cap in v1.

### 3.4 `pipeline.py` wiring

- `process_one`: after `spool_and_hash` returns `spooled`, call
  `content_date.extract_taken_at(spooled, ext)` **once** (seek(0) before,
  seek(0) after — same discipline already used before the upload call);
  reuse that single ISO string at every call site below (`mark_hashed`,
  `content_key`, `pointer_key`, `metadata_key`) rather than reformatting or
  re-deriving it independently at each one (risk-analyst Low finding —
  removes any chance of the three keys silently disagreeing on the date).

#### 3.4a Canonical-key reuse (closes the version-drift gap, §2)

Before computing a fresh `content_key` for a row, check
`state.find_uploaded_by_sha256(sha256_hex)` — **already defined in
`state.py`, currently unused anywhere in the codebase**. If a row with this
sha256 is already `uploaded`, reuse *its* recorded `content_key` instead of
recomputing one from this row's own `extract_taken_at` result:

```python
existing = state.find_uploaded_by_sha256(sha256_hex)
c_key = existing.content_key if existing and existing.content_key else uploader.content_key(
    config.prefix, sha256_hex, ext, taken_at
)
```

This makes "the first row to successfully upload a given sha256 sets its
canonical location" the actual, version-proof invariant: as long as the
local state DB survives an upgrade (it does — the migration only adds a
column, per §4), a duplicate row discovered *after* upgrading always lands
on the *already-recorded* key, regardless of whether `extract_taken_at`'s
logic changed in between. This is an efficiency-style guard in the same
spirit as the existing per-sha256 lock (`Sha256LockRegistry`) — it doesn't
replace `content_key`'s pure-function property, it prevents *ever calling*
the pure function with stale-vs-current-version inputs for content that's
already settled. Residual (explicitly accepted, not solved): a *full*
local state-DB loss **combined with** a code upgrade in between (both at
once) can still produce a second content object for the same sha256 — a
narrower, compounding version of the already-accepted "full state-DB loss"
scenario, not a new class of risk, and not worth defending against here
per this project's existing policy of stating rather than eliminating rare
compounding edge cases (`discovery.py::compute_id`'s zip-rename note is the
same style of trade-off).

#### 3.4b Legacy-key fallback in `reconcile_stuck_rows` (closes the upgrade-window gap, §2)

A row left `uploading` by a **pre-upgrade** version has no `taken_at`
(`NULL` after migration) and may have already had its content fully
uploaded under the *old* flat key, `f"{prefix}/content/{sha256}{ext}"`.
Computing only the new-scheme key (`unknown-date`, since `taken_at` is
`NULL`) would 404, reset the row to `pending`, and re-upload — orphaning
the real object. Fix: when the new-scheme key isn't found, `reconcile_stuck_rows`
also checks the pre-migration flat key before concluding "not uploaded":

```python
c_key = uploader.content_key(prefix, row.sha256, ext, row.taken_at)
if not uploader.already_uploaded(s3_client, bucket, c_key, row.sha256):
    legacy_key = f"{prefix}/content/{row.sha256}{ext}"
    if uploader.already_uploaded(s3_client, bucket, legacy_key, row.sha256):
        c_key = legacy_key  # content is real; record where it actually is
    else:
        content_ok = False
```

Scoped to `content_key` only — a stuck row's *pointer/metadata* object
possibly sitting at the old path-only key is a low-cost orphan (a few KB of
JSON, not media bytes) if reconciliation writes a fresh one at the new
location instead; that mismatch is accepted, not defended against, since
it costs nothing like what an orphaned multi-MB content object would.

### 3.5 Dependency

Add `exifread>=3.0` to `pyproject.toml` `[project.dependencies]`. Pure
Python, no C extension, MIT-licensed — consistent with this project's
otherwise-lean dependency set (`boto3`, `rich`).

## 4. What does NOT change

- No new S3 objects, no duplicated bytes — one content object per unique
  sha256, exactly as today.
- `already_uploaded` / `verify_uploaded` / `upload_content_if_missing` —
  unchanged; they operate on whatever key they're given.
- The per-sha256 in-process lock, the systemic-failure classifier, the
  single-instance lock — untouched.
- Existing uploaded rows already in a user's state DB keep their existing
  `content_key`/`pointer_key` values (schema migration only adds a column;
  it does not rewrite or move any already-uploaded object). This is a
  **going-forward** layout change, not a migration of previously-uploaded
  files — recomputing/moving old keys is out of scope for this plan (see
  §7 for the explicit limitation this leaves).

## 5. Tests

- `test_content_date.py` (new): crafted minimal JPEG+EXIF bytes with a
  known `DateTimeOriginal` extracts correctly; `DateTimeOriginal ==
  "0000:00:00 00:00:00"` (placeholder) returns `None`, not an exception; a
  plain PNG/GIF returns `None`; truncated/corrupted/empty bytes returns
  `None` and never raises; a crafted minimal MP4 with an `mvhd` box (both
  32-bit and 64-bit/`largesize` variants) extracts the QuickTime-epoch date
  correctly; `mvhd.creation_time == 0` returns `None`; an MP4 with `moov`
  placed after a large synthetic `mdat` is walked without reading the
  `mdat` body (assert via seek/read-call count, or a body that would fail
  to parse if actually read as a box stream); a deliberately
  circular/malformed IFD fixture completes in bounded time (no hang).
- `test_uploader.py`: update `content_key`/`pointer_key`/`metadata_key`
  call sites for the new `taken_at` parameter; add: date-folder grouping,
  `unknown-date` fallback, two different sha256 values with the *same*
  `taken_at` never collide (full hash still present), same inputs are
  still fully idempotent across repeated calls.
- `test_dedup.py` / `test_state_rebuild.py`: update call sites; assert the
  core invariant survives unchanged — identical content (mocked to return
  the same `taken_at` from `content_date.extract_taken_at`, since it's a
  pure function of the same bytes by construction) still resolves to one
  content object under concurrent workers and after full state-DB loss;
  **new** — two rows with the same sha256 processed under *different*
  mocked `extract_taken_at` outputs (simulating a version change between
  runs) still resolve to one content object, via the `find_uploaded_by_sha256`
  reuse path (§3.4a) — the only test structured to actually catch a
  cross-version divergence rather than a cross-concurrency one.
- `test_pipeline_resume.py` (or a new scenario in `test_pipeline_resume.py`):
  **new** — a row `uploading` with content already present at the
  *pre-migration* flat key and `taken_at IS NULL` is reconciled to
  `uploaded` at that legacy key, not re-uploaded under the new scheme
  (§3.4b regression test).
- `test_state.py`: schema migration test — open a v1 DB (no `taken_at`
  column) with the new code, assert the column is added and existing rows
  are preserved with `taken_at IS NULL`; **new** — two concurrent
  `open_state()` calls against a fresh v1 DB both succeed without a
  "duplicate column" error (migration-race regression test, §3.2).
- `test_pipeline_halt.py`: update any direct `mark_hashed` call sites for
  the new optional parameter (default `None`, so untouched call sites keep
  working).

## 6. Acceptance criteria

1. `content_key` remains, provably, a pure function of the file's own
   bytes — `test_state_rebuild.py`'s existing scenario (concurrent workers,
   full state-DB loss) still passes unmodified in spirit: no two distinct
   keys ever hold identical content, and the same content always resolves
   to the same key regardless of which row/run computes it.
2. No content object is ever duplicated: total distinct `content/` objects
   in the mock bucket for a set of rows with `N` unique sha256 values is
   `N`, exactly as before.
3. A photo with usable EXIF `DateTimeOriginal` lands under
   `content/YYYY/MM/DD/YYYY-MM-DD_HHMMSS__<sha256><ext>`.
4. A file with no extractable embedded date lands under
   `content/unknown-date/<sha256><ext>` — uploaded correctly, never
   dropped or failed because of the missing date.
5. `pytest` exits 0, `ruff check` + `ruff format --check` clean, `mypy`
   clean.
6. `PROJECT_MEMORY.md` records the embedded-date-vs-sidecar-date decision
   and the HEIC/AVI/MKV `unknown-date` limitation, so a future session
   doesn't "fix" the flat `content/` layout by reaching for the sidecar
   date and silently reopening the round-2 race.

## 7. Known limitation, stated rather than solved

This plan only changes where *newly uploaded* content lands. A bucket that
already has files under the old flat `content/{sha256}{ext}` / path-based
`library/` layout from a previous run will end up with **both** layouts
side by side after upgrading (old files stay where they are; new uploads
and re-verified duplicates of already-uploaded content also stay at their
already-recorded key — `content_key` is only computed for rows not yet
`uploaded`). A one-off backfill/rename pass (`aws s3 mv` per existing row,
driven by the local state DB) is a reasonable follow-up but is explicitly
out of scope here — this plan does not touch any already-uploaded row.
