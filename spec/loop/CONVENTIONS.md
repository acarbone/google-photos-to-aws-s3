# Loop State — Conventions

Each autonomous loop gets its own subfolder under `spec/loop/`, parallel to
how `spec/feat/` archives feature plans:

```
spec/loop/
├── CONVENTIONS.md          ← this file
├── <loop-name>/
│   ├── loop.md              ← the charter: purpose, cadence, scope, stop
│   │                          condition, output tier, turn cap, model/fan-out,
│   │                          audit cadence, owner
│   ├── state.md             ← progress cursor: what ran, when, where it stopped
│   ├── inbox.md             ← actionable findings awaiting action or review
│   └── archive.md           ← non-actionable findings, dated, with a reason
└── <another-loop>/
```

See `spec/design/06_loop_engineering.md` for the full loop-engineering model
(the ladder, output tiers, governance). This file covers only the on-disk
conventions for a loop's own state.

---

## Rules

1. `loop.md` is written before the loop runs for the first time, using the
   `loop-charter` skill. No charter, no loop.
2. `state.md` is overwritten each run with the latest cursor — it is not a
   log. Do not trigger a manual run of a loop while its own scheduled
   instance may still be active — two runs of the *same* loop writing
   `state.md`/`inbox.md` concurrently have no lock or run-id, so the
   loser's update can be silently lost. The attention budget (default 3
   concurrent loops per reviewer) bounds distinct loops running in
   parallel; it does not cover two instances of one loop.
3. `inbox.md` entries are removed only once actioned — cross-reference the
   resulting `spec/feat/<slug>/plan.md`, commit, or MR link before removing.
4. `archive.md` is append-only, dated, one line minimum: what, why
   non-actionable.
5. One folder per loop; do not share a folder across unrelated loops.
6. Changing a loop's output tier is a charter edit, reviewed like any other
   change — never an in-flight decision by the agent.

---

## `loop.md` charter template

```markdown
# Loop: <name>
- **Purpose**: one sentence.
- **Rung / primitive**: 3 (`/loop 24h`) | 4 (`/schedule`) | 2 (`/goal`, one-shot)
- **Output tier**: A (report-only) | B (local change) | C (external action)
- **Cadence**: e.g. weekday mornings; or on-demand
- **Scope — reads**: files/globs, connectors
- **Scope — never touches**: explicit exclusions
- **Stop / done condition**: mechanically checkable, verifiable by a separate model
- **Abort criteria**: turn cap; halt if 2 turns show no improvement; halt on red flags
- **Agents & models**: explorer = <fast model>; implementer = <model>; verifier = <strong model, high effort>
- **Fan-out**: max parallel worktrees/agents
- **Human audit cadence**: e.g. every Friday, a human reads two random findings end-to-end
- **Owner**: the human accountable for this loop's output
```
