# Amendments — chronological-s3-layout

## [2026-09-06] Migration locking: simpler mechanism than planned, same guarantee

**Planned** (§3.2): wrap the v1→v2 migration in an explicit
`BEGIN IMMEDIATE ... COMMIT` transaction, re-checking `schema_meta.version`
inside the lock, so a concurrent second process blocks on the existing
`busy_timeout` and finds the migration already applied.

**Built instead**: no explicit `BEGIN IMMEDIATE`. `ALTER TABLE` is issued
directly; SQLite's own per-statement locking (still governed by the same
`busy_timeout` set in `_connect`) serializes two concurrent connections
without any Python-level transaction management, and the loser hits
`ALTER TABLE ... ADD COLUMN`'s "duplicate column name" error, caught as an
already-applied no-op — the same catch that was already needed for the
brand-new-DB case (`_SCHEMA_SQL` creates `taken_at` directly there).

**Why**: manually issuing `BEGIN`/`COMMIT` through Python's `sqlite3`
module interacts with that module's own implicit transaction handling in
ways that have shifted across Python versions (pre-3.12 vs 3.12+ DDL
transaction semantics). Relying purely on SQLite's built-in statement-level
locking sidesteps that entirely — it's the same serialization guarantee
(confirmed via `test_schema_migration_race_two_processes_on_same_v1_db`),
with less surface area and no version-dependent behavior to reason about.

## [2026-09-06] Verified, not just asserted: exifread's IFD-chain hang risk

§3.1 flagged (risk-analyst Finding 6) that IFD-chain-based EXIF parsers are
a known hazard class for circular "next IFD offset" values causing
unbounded loops. Verified empirically before shipping: a hand-crafted JPEG
with a self-referencing IFD (next-IFD offset pointing back to IFD0, with no
tag in IFD0 that would let `exifread` short-circuit via `stop_tag`) returns
`None` in ~0ms — `exifread` has its own loop protection. Not added as a
permanent test (asserting on wall-clock timing in CI is flaky by nature),
but the finding itself is resolved: no hang risk observed.
