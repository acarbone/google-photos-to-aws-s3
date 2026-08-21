# Feature Specs — Conventions

This folder stores **completed feature specs** as a persistent decision log. Plans created during the Spec-Driven process are not deleted after implementation — they are the primary record of *why* the system is built the way it is.

Think of this folder as "git log for engineering decisions": a searchable archive of root causes, trade-offs, and constraints that shaped each feature.

---

## Folder structure

Each feature or significant change gets its own subfolder:

```
spec/feat/
├── CONVENTIONS.md          ← this file
├── <feature-slug>/
│   ├── plan.md             ← the implementation plan (preserved after completion)
│   ├── research.md         ← research findings (if produced)
│   └── amendments.md       ← optional: scope changes or post-implementation notes
└── <another-feature>/
    └── plan.md
```

Use a short, descriptive slug for the folder name (e.g. `cursor-pagination`, `auth-refresh-tokens`, `notification-dedup`).

---

## What goes in plan.md

A completed `plan.md` should be preserved as-is after implementation, with one addition: a brief **outcome note** at the top or bottom:

```markdown
> **Outcome** [YYYY-MM-DD]: Implemented as planned. / Deviated from plan in section X — see amendments.md.
```

Do not edit the plan body retroactively to match what was built. The plan's value is as a record of *intent*; divergences are meaningful and should be documented in `amendments.md`, not erased.

---

## What goes in amendments.md

Record any significant deviations from the plan that occurred during or after implementation:

- Scope changes (what was added or cut and why)
- Approaches that were tried and abandoned
- Post-implementation findings that would have changed the plan

Keep entries dated and self-contained.

---

## How to use this archive

When starting a new feature or refactor, search this folder for prior art:

- Similar features may have faced the same trade-offs.
- Rejected approaches are documented here — no need to rediscover why they were rejected.
- Cross-referencing plans helps identify patterns that recur across features (candidates for new skills or rules).

Prompt example: *"Before planning, check spec/feat/ for any prior work on authentication or session management."*

---

## Rules

1. **Never delete plans after implementation.** The folder is append-only except for `amendments.md`.
2. **Keep plans self-contained.** A plan should be understandable without reading the chat or other sessions.
3. **One folder per feature.** Do not put multiple unrelated plans in the same folder.
4. **Link from changelog.** Each `CHANGELOG.md` entry for a feature should reference its plan: `[spec: spec/feat/<slug>/plan.md]`.
