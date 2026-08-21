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
