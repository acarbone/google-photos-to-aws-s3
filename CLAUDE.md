# Claude Code – Project Instructions

These rules apply to every session. Read them before planning or writing any code.

---

## The Iron Law

**Before acting on any message — including casual or ambiguous ones — check whether a skill exists for the task at hand.**

Skills live in `.claude/commands/`. Each file is a slash command (`/skill-name`) describing when and how to use it. If a matching skill exists, follow its procedure exactly. Do not improvise a different approach.

This rule has no exceptions. It is **not negotiable. Not optional.** It applies to every request, regardless of how small or routine the task appears.

### Why this matters

Agents optimize for the shortest path to an answer. The shortest path typically skips established procedures. The Iron Law makes bypassing skills structurally impossible by requiring the check to happen first — before any other reasoning about how to proceed.

### How to apply

1. Read the task or message.
2. Scan `.claude/commands/` for a skill whose description matches the task.
3. If a match exists → follow the skill's procedure (invoke it as a slash command if the user hasn't already).
4. If no match exists → proceed using judgment, and consider whether a new skill should be proposed.

Full skill index: **SKILLS.md**.

---

## Language

Always respond in **English** in this project: explanations, comments in code, documentation, and chat replies. Keep code identifiers and user-facing strings in English unless the user explicitly requests another language.

---

## Project Memory

At the start of every session, **read `PROJECT_MEMORY.md`** before planning or writing any code.

This file contains institutional knowledge that is not derivable from the code or git history: bugs that required multiple attempts, architectural guardrails, hard prohibitions, and non-obvious project gotchas. Rules documented there override shortcuts and intuition.

After any session that reveals a non-obvious rule, a repeated mistake, or a hard-won constraint: **update `PROJECT_MEMORY.md`** so the next session inherits it.

Full guidance: **AGENTS.md § Project memory**.

---

## Quality and Verification

Before marking any task or phase as **done**, you must:

1. **Run the test suite** – All tests pass. Fix or document any failure before reporting completion.
2. **Run the linter (and formatter)** – No lint/format errors. Fix or document exceptions.
3. **Confirm acceptance criteria** – Implementation matches the plan/spec for that task.
4. **Update artifacts** – Plan/checklist and changelog (per project practice) are updated.

Do not report completion without having run tests and lint. Follow project patterns and code style; address edge cases and security/performance where the spec requires it.

For changes deployed to a real environment, extend verification into production: check error rates, pull traces, and confirm no regressions in monitoring dashboards. For changes touching shared code across repositories, use cross-repo code search to verify consistency. See **docs/quality-and-verification.md § 8** for tools and guidance.

Full rules: **docs/quality-and-verification.md**.

---

## Agents

Specialized sub-agents are defined in `.claude/agents/`. Invoke them by role when appropriate:

- **architect-reviewer** – Structural integrity, component boundaries, ADR alignment (first pass in review cycle).
- **consistency-reviewer** – Naming conventions, code patterns, style alignment (second pass).
- **risk-analyst** – Edge cases, failure modes, hidden dependencies, testing gaps (final pass, gates implementation).
- **documentation-architect** – Keeps README, docs/, and ADRs up to date.
- **security-auditor** – Full-stack security review (frontend, backend, system integration).

Full guidance: **AGENTS.md**.
