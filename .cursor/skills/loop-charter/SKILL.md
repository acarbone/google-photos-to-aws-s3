---
name: loop-charter
description: Procedure for writing or revising a loop's charter (spec/loop/<loop-name>/loop.md) — scope, cadence, output tier, a mechanically checkable stop condition, abort criteria, and attention budget. Run before a loop's first run and whenever its tier or scope changes.
---

# Loop Charter

## When to use

Before any loop runs for the first time (governance rule 2 in
`spec/design/06_loop_engineering.md`: no charter, no loop), and again
whenever the loop's scope, cadence, or output tier changes.

---

## Procedure

1. **State the purpose in one sentence.** If it takes two, the loop is doing
   two jobs — split it into two loops.
2. **Pick the rung (2/3/4) and the output tier (A/B/C).** Default to the
   lowest of each that can deliver the purpose. Promotion needs evidence, not
   intent (see the promotion rule in `spec/design/06_loop_engineering.md`).
3. **Write the stop / done condition.** Apply the **separate-model test**:
   could a different model, seeing only the loop's output files and this
   sentence, decide pass or fail without judgment? If not, rewrite it. If it
   cannot be rewritten that way, the task is not a loop — send it back to
   Tier 1 or 2.
4. **Write the abort criteria**: a turn cap, the no-improvement rule, and the
   red-flag halts.
5. **Declare scope explicitly on both sides**: what it reads, and what it
   must never touch. Name the connectors and their access level.
6. **Declare cadence, fan-out, and the models** for explorer / implementer /
   verifier. Check the fan-out against the attention budget (default 3
   concurrent loops per reviewer).
7. **Name the human owner and the audit cadence** — who reads the output, how
   often, and how deeply.
8. **For tiers B and C, confirm the credential set matches the tier** before
   the first run.

---

## Output

A complete `spec/loop/<loop-name>/loop.md` matching the template in
`spec/loop/CONVENTIONS.md`, plus empty `state.md` / `inbox.md` / `archive.md`.

---

## Rules

1. **Never start a loop with an unwritten or partial charter.**
2. **Never soften a stop condition to make a task loop-able** — an
   untestable finish line is the signal to *not* build the loop.
3. **Charter edits are reviewed like any other change**; an agent never
   changes its own tier mid-run (governance rule 3).
