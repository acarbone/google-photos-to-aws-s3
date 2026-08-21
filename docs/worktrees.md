# Worktrees

Isolated working directories so parallel agents — or a loop running alongside
a live interactive session — don't collide on the same files or branch. This
is the "worktrees" building block from `spec/design/06_loop_engineering.md`.

---

## When to isolate

- Any time a loop (or a human) spawns more than one agent/session that could
  touch overlapping files.
- Any output-tier-B or -C loop (§ Output tiers in `06_loop_engineering.md`) —
  it writes code or docs and must not do so on the branch a human has
  checked out.
- Any implementation running in parallel with a live interactive session.

If none of these apply — a single agent, single session, single branch — a
worktree is unnecessary overhead.

---

## How, per tool

**Claude Code**:
- `isolation: "worktree"` on the `Agent` tool call, for a subagent that needs
  its own copy of the repo.
- `EnterWorktree` / `ExitWorktree` for a manual session that should work
  inside an isolated worktree for a span of turns.

**Any tool / CLI fallback**:
```bash
git worktree add ../<repo>-<slug> -b <branch>
# work in ../<repo>-<slug>
git worktree remove ../<repo>-<slug>
```

---

## Naming

- Worktree directory: `<repo>-<loop-or-feature-slug>`.
- Branch: matches the slug used in `spec/loop/<loop-name>/` or
  `spec/feat/<slug>/`, so the branch name, the worktree directory, and the
  spec folder all point at the same piece of work.

---

## Cleanup

A loop removes its own worktree after the verifier pass completes — success
or terminal failure. Worktrees do not accumulate. If a loop dies mid-run, the
next run's `loop-triage` reports orphaned worktrees as a finding (this is
check 7, "loop hygiene," in `spec/loop/repo-maintenance/loop.md`).

---

## Multi-worktree exploration (advanced)

Running the same finding in two worktrees with different approaches and
having an adversarial judge pick the winner is a legitimate advanced pattern.
It is explicitly **not** a default: it multiplies token cost and requires a
declared fan-out in the loop's `loop.md` (see the "Fan-out" field in the
charter template, `spec/loop/CONVENTIONS.md`). Use it deliberately, for a
finding where the approach itself — not just the execution — is the open
question.
