# Agents in this project

Agents are used as **domain-experts** and **executors of ancillary tasks**: they own specific concerns (documentation, security, reconciliation of requirements) so the main coding flow stays focused, and repetitive or cross-cutting work is done consistently.

## How they’re used

- **Invoked by you**: You assign or request an agent when a task fits its role (e.g. “have the documentation agent update the README”, “run the security agent on this PR”).
- **Defined by role**: Each agent has a clear responsibility and instructions so behavior is predictable and auditable.
- **Complementary to skills**: Agents perform roles; skills encode reusable procedures. Agents can use skills (e.g. changelog skill) when their task matches.

Agent-specific instructions and guidance live in **`.cursor/agents/`** (Cursor) and **`.claude/agents/`** (Claude Code). Use those files to tune how each agent behaves.

## Project memory

Agents do not remember across sessions — continuity lives in files, not model state. **`PROJECT_MEMORY.md`** (project root) is the institutional knowledge file all agents must read at session start. It captures:

- Bugs that required multiple attempts to fix (so the same reasoning error is not repeated)
- Architectural guardrails derived from past decisions
- Hard “never do this” rules born from incidents
- Non-obvious gotchas about the project that are not visible in the code

Update `PROJECT_MEMORY.md` whenever a session reveals something that would have saved time if known at the start.

## Sample agents

**Documentation Agent**
Responsible for continuously updating documentation when code changes. Keeps docs in sync with the system and removes outdated content so the corpus stays useful.

**Business Domain Expert Agent**
Reviews requirements and code so they make sense in the context of the system and domain you’re building. Surfaces mismatches between intent and implementation.

**Code Review & Rule Expert Agent**
Passive agent that flags: duplicated code, tests written to pass rather than to verify behaviour, and violations of architectural or project rules.

**Requirements Reconciliation Agent**
Tracks new work and compares it to past requirements. Surfaces logical conflicts between new and old requirements so they can be called out and reconciled.

**Security Agent**
Reviews code for security vulnerabilities and suggests mitigations.

---

## Multi-agent review cycle

For non-trivial plans, run a structured review pipeline before implementation begins. Three specialized reviewer agents each examine the plan from a different angle. The cycle repeats until the last reviewer finds only minor issues.

```
plan.md → Architect Reviewer → Consistency Reviewer → Risk Analyst → implementation
              ↑___________________________|___________________|
                       (revision round if needed)
```

| Agent | Focus | Cursor | Claude Code |
|---|---|---|---|
| **Architect Reviewer** | Structural integrity, component boundaries, ADR alignment | `.cursor/agents/architect-reviewer.md` | `.claude/agents/architect-reviewer.md` |
| **Consistency Reviewer** | Naming conventions, code patterns, style alignment | `.cursor/agents/consistency-reviewer.md` | `.claude/agents/consistency-reviewer.md` |
| **Risk Analyst** | Edge cases, failure modes, hidden dependencies, testing gaps | `.cursor/agents/risk-analyst.md` | `.claude/agents/risk-analyst.md` |

**When to use**: On plans for features, refactors, or any change where a wrong assumption in the plan would be costly to unwind after implementation. Skip for trivial or low-risk tasks (see pipeline tier guidance in `spec/design/00_pipeline_tiers.md`).

**How to invoke**: After the plan is drafted (Phase 2) and before or alongside the human annotation cycle (Phase 3):
- *"Have the architect reviewer check this plan."*
- *"Run the full review cycle on plan.md."*
- *"The architect reviewer and consistency reviewer have passed — have the risk analyst do the final check."*

The cycle is complete when the Risk Analyst produces a Pass verdict. That verdict is the gate before Phase 4 (Implementation) begins.

---

## Loop agents

Review-cycle agents (above) check a **plan** before code exists. Loop agents
check **discovery** and **output** in an unattended context — Tier 3,
`spec/design/06_loop_engineering.md`. The two sets serve different moments
and must never be conflated:

| Agent | Focus | Cursor | Claude Code |
|---|---|---|---|
| **Explorer** | Read-only discovery and triage for autonomous loops — scans the repo, CI, connectors, and trackers, writes findings to `spec/loop/<loop-name>/inbox.md` or `archive.md`. Never implements. | `.cursor/agents/explorer.md` | `.claude/agents/explorer.md` |
| **Loop Verifier** | Verifies output produced by a loop's implementer session against the finding's acceptance criteria and `docs/quality-and-verification.md`. Must be a separate identity from the implementer. Gates commit finalization and all connector actions. | `.cursor/agents/loop-verifier.md` | `.claude/agents/loop-verifier.md` |

**Never share an identity with the implementer.** The structural reason both
agents exist is the same one that motivates the review cycle: the agent that
produced a change cannot be the one that decides the change is correct.
Delegation covers execution, never the judgment call.

**When to use**: Any Tier 3 loop invokes `explorer` for discovery. Any loop
declared at output tier B or C invokes `loop-verifier` before the work is
called done. Tier A loops (report-only) have no implementer, so
`loop-verifier` is not invoked.
