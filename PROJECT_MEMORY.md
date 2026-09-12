# Project Memory

This file is **living institutional knowledge** accumulated across sessions. It captures what a new agent (or developer) must know that cannot be derived from reading the code or git history alone: bugs that required multiple attempts to fix, architectural guardrails born from past failures, and hard-won "never do this" rules.

Read this file at the start of every session. Update it whenever a session reveals a non-obvious rule, a tricky gotcha, or a decision that will save future effort.

---

## How to use this file

- **Agents**: Read this before planning or coding. Rules here override intuition and shortcuts.
- **Developers**: Update this after any incident, near-miss, or session where something surprising was discovered.
- **Format**: Each entry is self-contained. State the rule clearly, then explain the context that produced it.

---

## Architectural guardrails

> Rules about how the system must (or must not) be structured. Add entries when a structural decision is locked in and must not be reversed without deliberate discussion.

<!--
Example entry:
### Never split the plan across multiple files
**Why**: Splitting caused context drift in multi-session work — the AI lost track of which fragment was authoritative. All planning lives in a single `plan.md` per feature.
-->

*(No entries yet — add the first one after your first incident.)*

---

## Bugs that required multiple attempts

> Document bugs where the first (or second) fix was wrong. Record what failed and why, so future sessions don't repeat the same reasoning error.

<!--
Example entry:
### Annotation cycle: AI implemented code despite "don't implement yet" instruction
**What happened**: The AI treated inline plan annotations as a trigger to start coding rather than refining the plan.
**Fix that worked**: Separate the annotation prompt ("I added notes, update the plan") from any phrasing that resembles an implementation request. Reinforce with "strictly update the document only — no code".
-->

*(No entries yet.)*

---

## Never-do rules

> Hard prohibitions derived from incidents. These are **not negotiable. Not optional.**

<!--
Example entry:
- **NEVER git commit without explicit user permission.** Agents have autonomy over code changes; commits are a shared-state operation that requires human sign-off.
-->

*(No entries yet — add the first one when a prohibition is established.)*

---

## Gotchas and non-obvious facts

> Things that are true about this project that are not obvious from reading the code — e.g. environment quirks, integration behaviours, implicit constraints.

<!--
Example entry:
- The linter treats `any` as a warning in most files but an error in `src/api/` — do not use `any` there even when it seems harmless.
-->

- **2026-09-06 — `content_key`'s date folder MUST come from the file's own embedded bytes (EXIF/mvhd), never from Google's Takeout sidecar JSON.** The sidecar (`photoTakenTime`) is per-occurrence, external data — two rows sharing an identical sha256 could in principle carry different sidecar dates, which would make `content_key` occurrence-dependent again and reopen the round-2-Critical dedup-after-state-loss race (`spec/feat/google-photos-s3-backup/plan.md` §6/§7) that took 4 review rounds to close. `content_date.py`'s embedded-date extraction is a true pure function of content bytes, so the invariant is extended, not weakened. See `spec/feat/chronological-s3-layout/plan.md` §2 for the full reasoning — do not "simplify" this by switching to the sidecar date, even though it would be easier and more format-uniform.
- **2026-09-06 — Even embedded-date extraction isn't automatically version-proof; the fix is `find_uploaded_by_sha256` reuse, not just "pure function of bytes."** If `content_date.extract_taken_at`'s logic ever changes (new format support, a bug fix), two rows with the same sha256 hashed under different code versions could compute different keys. `pipeline.process_one` guards against this by reusing an already-`uploaded` row's recorded `content_key` (via `state.find_uploaded_by_sha256`, previously defined but unused) instead of recomputing — this only works as long as the local state DB survives the upgrade (the normal case; schema migrations only add columns, never wipe rows). Don't remove this reuse check when touching `content_date.py`.
- **2026-09-06 — HEIC/HEIF, AVI, MKV, 3GP get no embedded-date extraction (land in `unknown-date`), by deliberate choice, not an oversight.** `exifread` doesn't parse HEIC's ISO-BMFF-based EXIF box; AVI/MKV have entirely different metadata formats (RIFF/EBML) this project doesn't parse. Before adding support for any of these, re-read `spec/feat/chronological-s3-layout/plan.md` §2/§3.4a — a new format needs to keep the pure-content-function property (never read row/path/sidecar data) or it reopens the same class of bug.
- **2026-09-06 — `exifread`'s IFD-chain following does NOT hang on a circular "next IFD offset" — verified empirically, not assumed.** See `spec/feat/chronological-s3-layout/amendments.md` for the exact fixture and result before relying on this again after an `exifread` version bump.
- **2026-09-06 — `tests/test_cli.py`'s 3 failures (rich ANSI color codes appearing in `capsys` output: `test_status_command_prints_counts`, `test_run_command_uploads_and_reports`, `test_retry_failed_picks_up_failed_and_verify_failed`) are PRE-EXISTING and environment-specific, not caused by any feature work.** Confirmed via `git stash` — they fail identically on a clean checkout. Root cause not yet investigated (likely `rich`'s terminal-color auto-detection behaving differently on this machine/its installed `rich` version than whatever environment last had these passing). Don't spend time "fixing" these as a side effect of an unrelated change; if you do investigate, this note is stale and should be updated or removed.
- **2026-08-21 — On this machine, `python -m venv` + `pip install` is broken; use `uv venv` + `uv pip install` instead.** The local Homebrew Python 3.14 has a broken `platform.mac_ver()` (returns empty strings instead of the actual macOS version — confirmed reproducible both inside and outside the bash sandbox, so it is not a sandbox permission issue). Any `pip install` — including `ensurepip`'s own bootstrap of pip into a fresh venv, and even fully offline `--no-index` installs — crashes, because pip's bundled `truststore` SSL-context setup calls `platform.mac_ver()` unconditionally and chokes on the empty string. `uv venv` / `uv pip install` (Homebrew `uv`, already present on this machine) does not hit this code path and works normally. If venv/pip setup fails with a `truststore`/`_macos.py`/`ValueError: invalid literal for int()` traceback, don't debug pip — switch to `uv`.
- **2026-08-18 — `spec/feat/loop-engineering/plan.md` was implemented before its own Phase G review-cycle gate ran.** The plan's §13 acceptance criteria required a Pass verdict from the multi-agent review cycle *before* implementation began. The user explicitly directed full implementation immediately instead; the review cycle (architect-reviewer → consistency-reviewer → risk-analyst) was run retroactively afterward and returned Pass from all three, with only advisory findings (see `spec/feat/loop-engineering/amendments.md`). This is not a template for future work — a direct, explicit user instruction is what authorized skipping the gate here; absent that, the gate applies as written in `spec/design/00_pipeline_tiers.md`.

---

## Recurring patterns (candidates for new skills)

> When the same kind of work keeps appearing across sessions, record it here. If it appears three or more times, consider graduating it into a dedicated skill in `.cursor/skills/`.

<!--
Example entry:
- Updating OpenAPI spec after every endpoint change — appears in most feature sessions. Candidate for a dedicated skill.
-->

*(No entries yet.)*
