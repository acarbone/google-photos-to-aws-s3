# Amendments — Loop Engineering

Deviations from `plan.md` discovered during or after implementation. See
`spec/feat/CONVENTIONS.md` for the convention this file follows.

---

## [2026-08-18] Review cycle run retroactively, not as the pre-implementation gate

**What the plan said**: §13 acceptance criteria state "The multi-agent review
cycle reaches a Pass verdict before implementation begins," and the header
status (before this implementation) said the next gate was that cycle.

**What actually happened**: The user explicitly directed full implementation
of the plan immediately ("Fully implement the changes described... Do not
stop until all the changes have been fully implemented"), overriding the
plan's own pre-implementation gate. The multi-agent review cycle
(`architect-reviewer` → `consistency-reviewer` → `risk-analyst`) was run
**after** implementation instead, as a retroactive confirmation pass against
both the plan text and what actually landed on disk.

**Why this is noted here rather than silently accepted**: `plan.md`'s body
is preserved as a record of *intent* per `spec/feat/CONVENTIONS.md`, and the
gate ordering was a deliberate part of that intent (Tier 2 process, §Tier
line in the plan header). This amendment records the divergence rather than
editing §13 to make it look like the original sequencing happened.

**Outcome**: Flagged by the Consistency Reviewer as a Medium finding during
the retroactive review cycle — recommending this file be created. See the
plan's outcome note (top of `plan.md`) and §12 task checklist for the full
review verdicts.

---

## [2026-08-18] Retroactive review cycle — verdicts and fast-follow fixes

**Verdicts**: `architect-reviewer` Pass, `consistency-reviewer` Pass,
`risk-analyst` Pass (cycle complete). No Critical or High findings from any
of the three. Six advisory Medium/Low findings across the three reviews were
fixed in this same implementation pass rather than deferred:

1. (Consistency, Medium) No `amendments.md` existed to record the review-cycle
   sequencing deviation → this file created.
2. (Consistency, Low) `docs/connectors.md` Slack row listed a skill
   (`loop-triage`) as an actor alongside agent identities → changed to
   `explorer (via loop-triage)`.
3. (Architect, Medium) `docs/connectors.md` governance rule 5 claimed a
   cross-reference from `docs/quality-and-verification.md` §8/§11 that didn't
   actually exist → both sections now link to `docs/connectors.md`.
4. (Architect, Medium) `loop-verifier.md`'s `model: inherit` had no recorded
   rationale, risking the verifier silently sharing a model with the
   implementer it checks → rationale comment added to the frontmatter,
   recommending a team pin a distinct strong model at tiers B/C.
5. (Risk, Medium) No structural backstop stops a mis-scoped `explorer` run
   from writing outside `spec/loop/<name>/` beyond the prompt itself → an
   enforcement-layer note added to `06_loop_engineering.md` § Governance
   recommending tool-level path restrictions for unattended runs.
6. (Risk, Medium) No self-check confirms a tier-A run's diff actually stayed
   in scope → step 8 added to `loop-triage`'s procedure
   (`git status --short` scoped to `spec/loop/<name>/{state,inbox,archive}.md`).

**Not fixed, left as documented advisories** (Low severity, no action
required): Risk finding on Tier A's "requires nothing" wording being in
cosmetic tension with its optional Slack-post path (deliberate, from
annotation round 1 Q3); Risk finding on same-loop concurrent-run races
(mitigated with a documentation note in `spec/loop/CONVENTIONS.md` rather
than a locking mechanism, since no incident has occurred yet); Architect
finding that `/goal`'s exact invocation surface is unconfirmed in this
environment (informational, does not affect the rung-2 pattern's validity).

**Independently re-verified by the reviewers, not just re-read**: both
`repo-maintenance` dry-run findings (`inbox.md` #2, and the now-actioned
changelog staleness #1) were confirmed genuine by at least two of the three
reviewers via direct filesystem/git checks — not accepted on the strength of
this session's own claims.
