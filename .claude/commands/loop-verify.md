---
name: loop-verify
description: Verification procedure run by the loop-verifier agent against output produced inside an autonomous loop, before the work is called done or any connector acts.
---

# Loop Verify

## When to use

Invoked by the `loop-verifier` agent after an implementer session completes
work triggered by a `spec/loop/<loop-name>/inbox.md` finding.

---

## Procedure

1. Run the project's test suite and linter for the touched area.
2. Runtime check where a runnable surface exists: start the dev server, open
   the changed page/route, interact with the change, capture before/after,
   read the console for new errors or warnings, run a performance trace
   where the finding mentions performance. A failure at any step means fix
   and restart from step 1 — never hand back partial work.
3. Compare output against the finding's acceptance criteria (and the
   relevant `spec/feat/<slug>/plan.md` if one was created).
4. Confirm no scope creep beyond the finding.
5. Confirm the output tier in `loop.md` was not exceeded.
6. Confirm traceability: commit/MR references the finding and skill(s) used.
7. Record Pass/Fail with reasons in the finding's entry.

---

## Output

- **Pass** → work is done; tier-C connector actions (MR, ticket) permitted.
- **Fail** → finding returned to `inbox.md` with the failure reason attached.

---

## Rules

1. **Must run as a session/identity distinct from the implementer**
   (governance rule 1).
2. **Never edits code** — only approves or bounces back.
3. **Never raises a turn cap or re-runs the implementer itself.**
