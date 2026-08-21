# Pipeline Tiers

Not all work warrants the full five-phase Spec-Driven process. Applying the same ceremony to a two-line fix as to a major feature wastes time and trains people to skip the process entirely. This document defines two tiers and the criteria for choosing between them.

---

## Tier 1: Lightweight

**Use for**: Small, well-understood changes with low risk of downstream impact — bug fixes, copy updates, minor configuration changes, isolated refactors within a single module.

**What to skip**: The formal research phase, a standalone `plan.md`, and the multi-agent review cycle.

**What to keep** (non-negotiable regardless of scope):

- A brief intent statement before coding (one sentence in chat or a comment in the task/ticket is enough).
- Quality gates: tests run, lint clean, acceptance criteria met, changelog updated.
- Annotation if the approach is not obvious — even a quick "I'll do X because Y, does that seem right?" before implementing.

**Signal to upgrade to Tier 2**: If during implementation you discover the change is larger, touches more files, or has more edge cases than expected — stop, write a plan, and upgrade.

---

## Tier 2: Full pipeline

**Use for**: New features, significant refactors, cross-cutting changes, anything with architectural implications, or any change where a wrong assumption in the plan would be costly to unwind.

**The full sequence**:

```
Research (01) → Planning (02) → Annotation cycle (03) → [Review cycle] → Implementation (04) → Feedback (05)
```

**Multi-agent review cycle** (optional but recommended for high-risk plans):

```
plan.md → Architect Reviewer → Consistency Reviewer → Risk Analyst → implementation
```

Run the review cycle when:
- The plan introduces new patterns or architectural changes.
- The change touches shared infrastructure or cross-repository contracts.
- The team is unfamiliar with the area being changed.
- The cost of a wrong implementation is high (e.g. data migrations, auth, billing).

Skip the review cycle when:
- The plan is short and the approach is well-established.
- The annotation cycle has already resolved all significant open questions.
- Time constraints are real and the risk is low (document the decision in `PROJECT_MEMORY.md`).

**Artifacts required**: `research.md`, `plan.md` (with checklist), updated `CHANGELOG.md`. Plans are preserved in `spec/feat/` as a decision log — see `spec/feat/CONVENTIONS.md`.

---

## Tier 3: Autonomous Loop

**Use for**: Recurring, background work with no single human driving each turn —
CI/issue triage, dependency and security scanning, stale-plan sweeps,
documentation drift checks, cost and error-rate monitoring. Not for first-time
feature work (use Tier 1 or 2).

**Tier 3 consumes Tiers 1–2, it does not replace them.** Loops handle the
execution slice of the work; research, planning, and annotation stay human.

**Maturity levels**: Tier 3 has four rungs, from a human-driven session to an
unattended proactive routine. They are defined once, in
`spec/design/06_loop_engineering.md` — not repeated here.

**What it requires** (non-negotiable):
- A `spec/loop/<loop-name>/loop.md` charter: cadence, scope, a written stop
  condition a *separate* model can verify mechanically, a declared output
  tier, and a turn/abort cap.
- Discovery and triage by a read-only **explorer** agent — never the agent
  that will implement.
- For output tiers B and C: any change is checked by a **loop-verifier**
  agent that is not the implementer, before the work is called done.
- Findings and progress persisted to `spec/loop/<loop-name>/` — never left
  only in conversation context. Loops are session-scoped and expire; disk is
  the only memory.
- The governance rules in `spec/design/06_loop_engineering.md` § Governance
  apply without exception.

**Signal to use Tier 3 instead of 1/2**: the work is recurring rather than a
one-off, and/or no human is expected to be present when it runs.

**Signal that Tier 3 does NOT apply**: "done" cannot be checked mechanically.
If the finish line is a matter of taste, use Tier 1 or 2.

---

## Choosing a tier

| Signal | Tier |
|---|---|
| Change touches one file or one isolated function | 1 |
| Change is a bug fix with a clear root cause | 1 |
| Change introduces a new feature or capability | 2 |
| Change affects multiple modules or services | 2 |
| Change has architectural implications | 2 |
| Change touches auth, payments, data integrity | 2 |
| You are unsure which tier applies | 2 |
| Change is recurring, scheduled, or meant to run unattended | 3 |
| Completion cannot be checked mechanically | not 3 (use 1 or 2) |

When in doubt, default to Tier 2. The cost of a research and planning phase is low compared to the cost of unwinding a wrong implementation.
