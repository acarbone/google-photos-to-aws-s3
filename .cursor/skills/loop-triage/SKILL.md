---
name: loop-triage
description: Discovery and triage procedure for autonomous loops — reads the loop's charter, scans the sources in its scope, and writes classified findings to spec/loop/<loop-name>/inbox.md or archive.md.
---

# Loop Triage

## When to use

Invoked by the `explorer` agent at the start of every loop run.

---

## Procedure

1. Read `spec/loop/<loop-name>/loop.md` — scope, exclusions, output tier. If
   no charter exists, stop and report; do not improvise a scope.
2. Read `state.md` for where the last run stopped.
3. Scan only the sources the charter lists (repo files, CI status, open
   `spec/feat/*/plan.md` checklists, `PROJECT_MEMORY.md` "Recurring
   patterns", read-tier connectors).
4. Classify each finding: actionable (clear next step, bounded scope,
   mechanically checkable acceptance criteria) vs. non-actionable (needs
   human judgment, out of scope, duplicate, subjective). A finding without a
   checkable acceptance criterion is non-actionable by definition — say so
   rather than inventing one.
5. Write actionable findings to `inbox.md` with: what, where, why, proposed
   acceptance criteria, suggested output tier. Non-actionable → `archive.md`
   with a dated one-line reason.
6. Deduplicate against existing `inbox.md` entries; never file the same
   finding twice.
7. Update `state.md` with the run timestamp and cursor.
8. Before considering the run complete, confirm the run's own diff touched
   only `spec/loop/<loop-name>/{state,inbox,archive}.md` (e.g.
   `git status --short`). This holds even at output tier A, where no
   verifier is invoked — it is the only check that the declared output tier
   actually held for this run.

---

## Output

`inbox.md` and `archive.md` updated; `state.md` cursor advanced. No code
changes.

---

## Rules

1. **Read-only. Never implements.**
2. **Never removes an existing `inbox.md` entry** — that happens only once
   actioned, per `spec/loop/CONVENTIONS.md`.
3. **Never exceeds the charter's scope.**
4. **Never uses a write-tier connector.**
