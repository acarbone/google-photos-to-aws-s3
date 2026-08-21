# Inbox: repo-maintenance

Actionable findings awaiting action or review. Entries are removed only once
actioned — cross-reference the resulting plan, commit, or MR link before
removing (see `spec/loop/CONVENTIONS.md`).

## [2026-08-18] #2 — AGENTS.md has no explicit index row for two existing agent files
- **Check**: 2 — Index drift
- **Where**: `AGENTS.md` vs. `.cursor/agents/documentation-architect.md` and
  `.cursor/agents/security-auditor.md`
- **Why**: `AGENTS.md` maintains explicit index tables for the review-cycle
  agents (Architect Reviewer, Consistency Reviewer, Risk Analyst) and now
  for the loop agents (Explorer, Loop Verifier), each with a direct
  `.cursor/agents/*.md` / `.claude/agents/*.md` file mapping. The "Sample
  agents" section describing a Documentation Agent and a Security Agent is
  generic prose and does not explicitly cross-reference
  `documentation-architect.md` / `security-auditor.md` by filename, so a
  literal file → row check does not find a match for either.
- **Proposed acceptance criteria**: `AGENTS.md` either (a) adds an explicit
  file reference next to the Documentation Agent / Security Agent prose
  entries, or (b) documents that "Sample agents" is intentionally generic
  and not meant to be a 1:1 file index, so this check's ignore-list can
  exclude that section.
- **Suggested output tier**: A (report only) until a human decides which of
  the two resolutions is correct — this is a judgment call about doc
  structure, not a mechanical fix.
- **Note**: pre-existing gap, not introduced by the loop-engineering
  implementation — surfaced by running check 2 for the first time.
