# Plan: Loop Engineering Capabilities

> **Status**: Implemented — see the outcome note below and the task checklist in §12 (all boxes checked).
> **Tier**: 2 (Full pipeline) — introduces new patterns and cross-cutting conventions.
>
> **Outcome** [2026-08-18]: Implemented as planned. Every file in §7/§8 was created or modified as designed; the seeded `spec/loop/repo-maintenance/` loop was dry-run for real and produced two genuine findings (see `spec/loop/repo-maintenance/inbox.md` and `archive.md`). One deviation from the original sequencing: the multi-agent review cycle (§12 Phase G) was run **retroactively**, after implementation, rather than as the gate before it — the user explicitly directed full implementation now rather than waiting on that cycle first; recorded in `spec/feat/loop-engineering/amendments.md` and `PROJECT_MEMORY.md`. **Review cycle verdict: Pass from all three (architect-reviewer, consistency-reviewer, risk-analyst)** — no Critical/High findings; six advisory Medium/Low findings were raised and all six were fixed as fast-follows in this same implementation pass: `spec/feat/loop-engineering/amendments.md` created, `docs/connectors.md` actor-naming fixed and its promised cross-reference added to `docs/quality-and-verification.md` §11/§8, a concurrency note added to `spec/loop/CONVENTIONS.md`, a tier-boundary self-check step added to `loop-triage`, a `model: inherit` rationale note added to `loop-verifier.md`, and an enforcement-layer note on local-filesystem boundaries added to `06_loop_engineering.md` § Governance. Full verdicts are in the session transcript; this note is the durable record.

---

## 1. Context & source material

This plan adapts Addy Osmani's two-part treatment of loop engineering into this repository's Spec-Driven template, so teams using it can build autonomous, self-directed agent loops — not just the interactive, one-session-at-a-time workflow the template currently supports.

Two sources, deliberately used for different purposes:

| Source | What we take from it |
|---|---|
| ["Loop Engineering"](https://addyo.substack.com/p/loop-engineering) | The **architecture**: six building blocks (automations, worktrees, skills, connectors, sub-agents, external memory) and the risk model (comprehension debt, cognitive surrender, orchestration tax). |
| ["Practical Loop Engineering"](https://addyo.substack.com/p/practical-loop-engineering) | The **operating manual**: the two native primitives (`/goal`, `/loop`), the four-rung loop-type ladder, determinism requirements, abort criteria, delegation boundaries, session lifecycle limits, and failure red flags. |

### 1.1 Article 1 — the architecture (condensed)

Loop engineering is a shift from *manually prompting* an agent turn by turn to *designing a system that prompts the agent for you* — a recursive process that iterates toward a defined goal on its own cadence, discovering work, triaging it, executing it, and verifying it without a human typing each step.

| # | Building block | What it does |
|---|---|---|
| 1 | **Automations** | The heartbeat — scheduled, autonomous runs that discover work, triage it, and surface (or act on) findings. |
| 2 | **Worktrees** | Isolated working directories so parallel agents don't collide on the same files/branch. |
| 3 | **Skills** | Institutional memory — reusable, on-disk procedures so the agent doesn't "re-derive the whole project from zero every cycle" ("intent debt"). |
| 4 | **Plugins / Connectors (MCP)** | Environmental integration — issue trackers, databases, staging APIs, chat — so a loop can act, not just propose. |
| 5 | **Sub-agents** | Separation of concerns — explorer (discovery), implementer (execution), verifier (QA) with different roles, models, and reasoning effort, so "the model that wrote the code" is never the one grading its own homework. |
| 6 | **External memory** | State on disk (markdown, a board, a file), not in conversation context — because the model forgets everything between runs. This is what lets a loop resume tomorrow where it stopped today. |

The risks it names: a loop running unattended is also a loop making mistakes unattended; **comprehension debt** (engineers stop understanding code they didn't write); **cognitive surrender** (accepting loop output without engagement); the **orchestration tax** (human review bandwidth caps parallelism); and real token cost. "The loop doesn't know the difference. You do."

### 1.2 Article 2 — the operating manual (condensed)

Definition sharpened: *a loop is an autonomous, self-correcting feedback cycle where an agent repeatedly acts, tests its results, and adjusts until a specific goal is met.*

**Two native primitives**

| Primitive | What it is | Stops when | Fits |
|---|---|---|---|
| **`/goal`** | Drives a bounded task until a measurable finish line, with an *independent evaluator* checking the transcript against hard rules only (not taste) | Criteria met, or turn limit reached | Deterministic, verifiable endpoints |
| **`/loop [interval]`** | Scheduler that reruns a prompt on a fixed interval, cron-like | Manual stop or session end | Recurring inputs, polling external systems |

Operational constraints that matter for our conventions: `/loop` is **session-scoped**, recurring loops **expire seven days** after creation, and a new conversation stops them. `--resume` / `--continue` re-enter within that window; `/schedule` (cloud routines) is the persistence path beyond a session. **This is the concrete reason external memory is mandatory, not stylistic.**

**The four-rung ladder**

| Rung | Loop type | Triggered by | Stopped by |
|---|---|---|---|
| 1 | Manual / agentic | A human prompt each turn | Human direction |
| 2 | Goal-based | `/goal` + success criteria | Criteria met or turn limit |
| 3 | Time-based | `/loop [interval]` (or `/schedule`) | Manual stop or session end |
| 4 | Proactive | Events/schedules, no human present | Each task exits at goal; routine runs until disabled |

**Determinism is the gate.** Loops excel when "done" is measurable (test passes, metric threshold, lint clean). They fail on vague criteria ("until the UI is good"), subjective taste, and open-ended creative exploration.

**Red flags mid-run**: the same command repeating without changing results; the same result appearing twice without variation. Both mean stop, not "try harder."

**Delegation boundary**: delegate *execution*, never the *judgment call*. One agent drafts, a **separate** agent verifies — the drafting agent structurally cannot decide it is "done" (their example: an agent optimizing desktop performance misses the mobile regression it caused).

**Verification should mimic human review**, not just green tests: start the dev server, open the page, interact, screenshot before/after, check the console, run a perf trace. Any failure → fix and rerun from step 1; never hand back partial work.

**Attention, not tokens, is the binding constraint**: "Stopping conditions are per loop, but your attention is not." 5–10 concurrent agents strain a human's capacity.

**Perspective**: loops handle roughly the **20%** that is execution. The other 80% — research, exploration, understanding constraints — is still the human's, and is exactly what Phases 01–03 of this template already cover.

### 1.3 Why this matters for this repository

This repo is a **template and playbook**, not an application. It encodes a reactive, human-in-the-loop process: a developer opens a session and runs Research → Planning → Annotation → Implementation → Feedback (`spec/design/01`–`05`), with the AI working inside one long session. There is no convention today for work the AI does *between* sessions, on its own schedule.

Article 2's "loops are the 20%" framing resolves the obvious tension: **Tier 3 does not compete with the five phases — it consumes their output.** The plan, the skills, `PROJECT_MEMORY.md`, and the quality gates are precisely the deterministic scaffolding a loop needs in order to have a checkable "done." A repo without them cannot run a safe loop; this repo already has most of it.

Four of the six building blocks exist here under different names (§4). The genuine gaps are **automations** (no cadence convention at all) and **worktrees** (no isolation convention). The sub-agent and connector conventions that do exist are scoped to *pre-implementation plan review*, not *autonomous discovery/execution/verification* — that distinction must be made explicit rather than silently reused.

---

## 2. Goals

1. Give teams adopting this template a documented, opinionated way to build autonomous loops on Claude Code / Cursor primitives, consistent with the repo's philosophy: the Iron Law, skills-as-procedure, agents-as-roles, plan-as-source-of-truth, non-negotiable quality gates.
2. Make the loop pattern a **third pipeline tier**, additive to the existing two. Loops handle recurring/background work (triage, maintenance, monitoring); Tiers 1–2 remain the interactive feature/fix path.
3. Close the two real gaps (automations, worktrees) with concrete conventions and templates; formalize the two partial gaps (loop-scoped sub-agents, connector governance) without duplicating what already exists for plan review.
4. Encode the warnings from both articles as **structural guardrails** — verifier ≠ implementer, mandatory stop conditions, declared output tier, traceability, attention budget — rather than advice that can be silently skipped.
5. **Make this repo itself loop-runnable.** Ship one real, seeded loop (`spec/loop/repo-maintenance/`) that a developer can start today from a Claude Code session, with **no CI, no git hosting, and no PR machinery required**.

## 3. Non-goals

- This repo ships no application code, no CI pipeline, and no test suite of its own. "Implementation" of this plan means docs, skill files, agent files, directory conventions, and one seeded loop definition — **not** building a scheduler or a bot. Consumer projects wire their own automation.
- **Not making CI or PR-based output mandatory.** A loop that only writes findings to `inbox.md` is a complete, valid loop (see the output tiers, §6). CI cron and PR automation are an *optional* highest tier, documented as an appendix.
- Not prescribing which MCP connectors a team must install. We provide an inventory *pattern* and governance rules; teams fill in their own entries.
- Not replacing `spec/design/01`–`05` or the existing plan-review cycle (`architect-reviewer` / `consistency-reviewer` / `risk-analyst`). Those are unchanged for interactive feature work.

---

## 4. Building-block → repo mapping (gap analysis)

| Article building block | Current state in this repo | Gap | Proposed adaptation |
|---|---|---|---|
| **Automations** (heartbeat) | None. No scheduling convention, no cadence guidance, no "what should run unattended" doc. | Full gap. | New Tier 3 in `spec/design/00_pipeline_tiers.md` + new `spec/design/06_loop_engineering.md` covering the primitives (`/goal`, `/loop`, `/schedule`), the four-rung ladder, cadence, the discovery/triage lifecycle, session-lifetime limits, **and governance as a section of the same file** (per §10.1). |
| **Worktrees** | None. No mention anywhere. | Full gap. | New `docs/worktrees.md`: when to isolate, how (Claude Code `isolation: "worktree"` / `EnterWorktree`/`ExitWorktree`, or plain `git worktree add` elsewhere), naming, cleanup. |
| **Skills** | Exists — `.claude/commands/`, `.cursor/skills/`, governed by `SKILLS.md` and the `skill-evolution` skill. | Mechanism fine; loop-specific procedures missing. | New skills `loop-triage` (discovery/triage) and `loop-verify` (post-implementation verification, incl. the runtime checks from article 2). Registered in `SKILLS.md` like any other skill. |
| **Plugins / Connectors (MCP)** | Partial — `docs/quality-and-verification.md` §8 references Grafana MCP and Octocode MCP for *human-driven* verification. | No central inventory; no governance for what an *unattended* loop may do through a connector (read vs. act). | New `docs/connectors.md`: inventory table with explicit read-only / write tiers and per-role permissions, seeded with the team's actual stack (§10.3). |
| **Sub-agents** | Exists — scoped to **pre-implementation plan review**: `architect-reviewer` → `consistency-reviewer` → `risk-analyst`. | No **discovery** agent, and no **post-implementation** verifier distinct from whoever implemented. The three reviewers read `plan.md`; none re-check code an autonomous run actually wrote. | New `explorer` agent (read-only discovery, cheap/fast model) and `loop-verifier` agent (checks the loop's own output against `docs/quality-and-verification.md` and the finding's acceptance criteria; must not be the implementing identity). `AGENTS.md` gains a "Loop agents" subsection. |
| **External memory** | Exists — `PROJECT_MEMORY.md` (institutional knowledge), `CHANGELOG.md` (work log), `spec/feat/<slug>/plan.md` (per-feature decision log). | None is designed for a *loop's own* running state. And article 2 makes this urgent: loops are session-scoped and expire in 7 days, so anything not on disk is gone by definition. Repurposing `PROJECT_MEMORY.md` would blur durable curated knowledge with high-churn queue state. | New `spec/loop/<loop-name>/` convention mirroring `spec/feat/`: `loop.md` (the charter — cadence, scope, stop condition, output tier, budget), `state.md` (progress cursor), `inbox.md` (actionable findings), `archive.md` (non-actionable, dated). Documented in `spec/loop/CONVENTIONS.md`. |

**Delta vs. the first draft of this plan**: the `loop.md` charter file is new. Article 2 makes an undeclared stop condition the single most common failure mode, so the stop condition must be a required artifact, not a sentence someone typed into chat that expires with the session.

---

## 5. The loop ladder, mapped to this template

`spec/design/06_loop_engineering.md` will teach the ladder as a progression, because starting at rung 4 is how teams get burned. **It is the ladder's only home** — `00_pipeline_tiers.md` points at it rather than restating it, so the two docs cannot drift apart (§11.5).

| Rung | Primitive | This repo's mapping | Prerequisite before you climb here |
|---|---|---|---|
| 1 — Manual | Plain session | Already covered: Phases 01–05, Tiers 1–2 | — |
| 2 — Goal-based | `/goal` | Bounded execution of a **single** `inbox.md` finding or `plan.md` checklist item, with acceptance criteria copied verbatim as the stop condition | The finding must have a criterion a *separate* model can check mechanically |
| 3 — Time-based | `/loop [interval]` | Recurring `loop-triage` runs writing to `spec/loop/<name>/inbox.md`. **Output tier A** (report-only). | `spec/loop/<name>/loop.md` charter exists |
| 4 — Proactive | `/schedule` (cloud routine) or external cron | Unattended discovery **plus** execution and verification, output tier B or C | Rung 3 has run for at least one full review cycle with a human reading the output |

**Rule to encode**: do not deploy a rung-4 loop for a task that has never been run successfully at rung 3. A loop is promoted by evidence, not by ambition.

**Goal-definition template** (adapted from article 2, to ship in `06_loop_engineering.md`):

```
/goal <task>. Done when <mechanically checkable condition>.
Do not change <explicit out-of-scope boundary>.
Each turn must improve at least one measured value;
abort if 2 consecutive turns show no improvement.
Stop after <N> turns.
```

Every element is mandatory. A `/goal` without an abort criterion and a turn cap is a rejected loop definition, not a loop.

**Red-flag stop conditions** (from article 2, encoded as a rule): if the same command repeats without a change in result, or the same result appears twice with no variation, the loop halts and writes the stall to `inbox.md`. It does not retry harder.

---

## 6. Output tiers — how far a loop is allowed to go

*(This section exists because of annotation §10.2: CI and PRs must not be a precondition for running a loop.)*

Every loop declares exactly one output tier in its `loop.md`. The tier bounds what the loop may touch, and therefore what infrastructure it requires.

| Tier | The loop may… | Requires | Verifier needed? | Example |
|---|---|---|---|---|
| **A — Report only** | Read, analyse, and write to `spec/loop/<name>/{inbox,archive,state}.md`. Optionally post a summary via a write-only chat connector. | Nothing beyond a working session. **No CI, no git hosting, no PR.** | No (nothing was changed) | `repo-maintenance` in this repo; cost watchdog; incident digest |
| **B — Local change** | Everything in A, plus write code/docs in an **isolated worktree** on a dedicated branch, and commit there. Never pushes, never touches the checked-out branch. | git only | **Yes** — `loop-verifier` before the commit is considered done | Doc-drift fixes; dependency bumps prepared for human review |
| **C — External action** | Everything in B, plus push and open a merge/pull request, and/or update a ticket through a connector. **Never merges.** | git hosting + configured connectors | **Yes** — verifier pass gates every connector call | Bug-fix loop that opens a GitLab MR |

**Tier A is the default and the recommended starting point.** Teams promote a loop to B or C deliberately, by editing `loop.md` — never implicitly because the agent found it convenient.

---

## 7. Proposed additions, by file

### 7.1 `spec/design/00_pipeline_tiers.md` — MODIFY

Add a third tier alongside the Lightweight / Full-pipeline split:

```markdown
## Tier 3: Autonomous Loop

**Use for**: Recurring, background work with no single human driving each turn —
CI/issue triage, dependency and security scanning, stale-plan sweeps,
documentation drift checks, cost and error-rate monitoring. Not for first-time
feature work (use Tier 1 or 2).

**Tier 3 consumes Tiers 1–2, it does not replace them.** Loops handle the
execution slice of the work; research, planning, and annotation stay human.

**Maturity levels**: Tier 3 has four rungs, from a human-driven session to an
unattended proactive routine. They are defined once, in
spec/design/06_loop_engineering.md — not repeated here.

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
- The governance rules in spec/design/06_loop_engineering.md § Governance
  apply without exception.

**Signal to use Tier 3 instead of 1/2**: the work is recurring rather than a
one-off, and/or no human is expected to be present when it runs.

**Signal that Tier 3 does NOT apply**: "done" cannot be checked mechanically.
If the finish line is a matter of taste, use Tier 1 or 2.
```

Add rows to the tier-selection table:
- *"Change is recurring, scheduled, or meant to run unattended → Tier 3."*
- *"Completion cannot be checked mechanically → not Tier 3."*

### 7.2 `spec/design/06_loop_engineering.md` — NEW (single file, governance included)

*(Per annotation §10.1, governance is a section here rather than a separate `07_`.)*

Structure, mirroring the tone/format of `01`–`05`:

```markdown
# Phase 6: Loop Engineering (Tier 3 only)

## Objective
Let scheduled or event-driven agent runs discover work, triage it, and either
act on it or surface it for a human — without a person prompting each step,
while preserving the same verification discipline the interactive phases require.

## Where loops fit
Loops are roughly the 20% of the work that is execution. The 80% — research,
exploration, understanding constraints — remains Phases 01–03. A loop is only
as safe as the plan, skills, and quality gates it runs against.

## The primitives
| Primitive | Use | Stops when |
|---|---|---|
| /goal    | one bounded task with a measurable finish line | criteria met or turn cap |
| /loop N  | recurring prompt on an interval, session-scoped | manual stop / session end |
| /schedule| persistent cloud routine                        | disabled |

Lifecycle facts that shape our conventions: /loop is session-scoped, recurring
loops expire ~7 days after creation, and starting a new conversation stops them.
Use --resume/--continue inside the window, /schedule for anything that must
outlive a session. Never treat conversation context as loop memory.

## The ladder (rungs 1→4) and the promotion rule
[table from §5 of the plan]
Rule: never deploy a rung-4 loop for a task that has not already succeeded at
rung 3 under human observation.

## The six components, in this repo's terms
| Article term | This repo's artifact |
|---|---|
| Automations    | /loop, /goal, /schedule, or an external scheduler, invoking the loop-triage skill |
| Worktrees      | docs/worktrees.md |
| Skills         | loop-triage, loop-verify (existing skill mechanism, unchanged) |
| Connectors     | docs/connectors.md — read/write permission tiers |
| Sub-agents     | explorer (discovery) → implementer → loop-verifier (QA), never one identity |
| External memory| spec/loop/<loop-name>/{loop,state,inbox,archive}.md |

## Output tiers A / B / C
[table from §6 of the plan] — tier A requires no CI and no git hosting.

## Loop lifecycle (reference, output tier B)
1. Scheduler (or the developer) triggers a run.
2. explorer runs loop-triage: reads state.md, then CI status (if any), open
   plan.md checklists, stale annotation cycles, PROJECT_MEMORY.md "Recurring
   patterns", connector sources in scope.
3. Findings → inbox.md (actionable) / archive.md (not, with a dated reason).
   Nothing is reported only in chat.
4. Per actionable finding, if the charter's tier allows it: create an isolated
   worktree (docs/worktrees.md); an implementer session executes it under
   /goal with the finding's acceptance criteria as the stop condition.
5. loop-verifier — a separate session/identity — runs loop-verify against the
   acceptance criteria and the quality gates. Fail → back to inbox.md with the
   reason. No silent retry.
6. Tier C only: on pass, connectors open an MR/PR and/or update a ticket.
   Never a merge.
7. state.md is updated with what ran and where it stopped.
8. Anything unresolved stays in inbox.md for a human. The worktree is removed.

## Writing a goal
[the mandatory /goal template from §5]

## When loops fail — red flags
- Same command repeating with no change in result → halt, log the stall.
- Same result twice without variation → halt.
- Completion criterion is subjective → the loop should never have been created.
- Turn cap reached → hand back to a human; do not raise the cap unattended.

## Delegation boundary
| Delegate fully | Monitor closely | Never delegate |
|---|---|---|
| Docs for already-implemented features; test-coverage checks; low-risk,
  well-specified tasks with clear constraints | Ambiguous specs; anything
  touching auth, security, payments, or system access | The judgment call
  itself — whether the work is right and done |

## Verification depth (from practical loop engineering)
Green tests are the floor, not the bar. Where the project has a runnable UI,
the verifier mimics human review: start the dev server, open the changed page,
interact, screenshot before/after, check the console for new errors, run a
performance trace. Any failure → fix and rerun from step 1; never hand back
partial work.

## Attention budget
Stopping conditions are per loop; your attention is not. Each loop's charter
declares its cadence and fan-out, and the team declares how many concurrent
loops a single reviewer will carry.

**Default: 3 concurrent loops per reviewer.** Chosen well under the 5–10 the
source article calls straining, because a reviewer who cannot read a loop's
output is not reviewing it — they are approving diffs, which is the cognitive
surrender this whole tier exists to prevent. Beyond the budget, loops queue;
they do not run in parallel just because the tooling allows it. Raising the
number is a deliberate, written decision — not something a busy week does by
default.

## Governance — non-negotiable rules
1. Verifier ≠ implementer. The identity that writes the change never approves it.
2. Every loop has a written charter (loop.md) with a mechanically checkable
   stop condition, a turn/abort cap, and a declared output tier. No charter,
   no loop.
3. A loop never exceeds its declared output tier. Tier A never writes code;
   tier B never pushes; tier C never merges to a protected branch.
4. Full traceability. Every autonomous commit, MR, or ticket update references
   the inbox.md finding and the skill(s) used. No anonymous autonomous changes.
5. Non-actionable findings are archived, not deleted — dated, with a reason,
   so patterns can be re-evaluated.
6. Human audit cadence. Loop output is sampled and *read* by a human on a
   declared cadence, not just diff-approved. This is the direct mitigation for
   comprehension debt and cognitive surrender.
7. Cost and attention awareness. Cadence, fan-out, and model choice are stated
   in the charter so cost is a conscious decision, not a surprise. **Default
   attention budget: 3 concurrent loops per reviewer.** A team may raise it
   only by writing the new number, and the reason for it, into its own docs.
8. A loop is not exempt from docs/quality-and-verification.md. Tests, lint,
   acceptance criteria, and artifact updates apply to loop-produced changes
   exactly as to human ones.
9. Stalls halt. Red-flag conditions stop the loop and produce a finding; they
   never trigger an unattended retry or a raised turn cap.

## Prompt / setup examples
[see §9 of the plan — the practical recipes ship here]

## Appendix — optional: running a loop from GitLab CI
A GitLab CI scheduled-pipeline example, clearly marked optional (GitLab only,
matching the connector stack in docs/connectors.md — no GitHub Actions
variant, per §11.4 of the plan). CI is one scheduler among several and is
never required: tier A loops run fine from a developer's session via /loop or
/schedule. The example exists to show the *shape* — a scheduled pipeline
invoking loop-triage, committing the updated spec/loop/<name>/ files back on a
branch — not to imply a loop needs a pipeline.
```

*(Note: this doc carries hard rules not derived from a repo incident, a departure from how `PROJECT_MEMORY.md` is populated. Confirmed acceptable for a design doc — see §10.5.)*

### 7.3 `docs/worktrees.md` — NEW

- **When to isolate**: any time a loop (or a human) spawns more than one agent/session that could touch overlapping files; any output-tier-B or -C loop; any implementation running in parallel with a live interactive session.
- **How, per tool**:
  - Claude Code: `isolation: "worktree"` on the `Agent` call, or `EnterWorktree` / `ExitWorktree` for a manual session.
  - Any tool / CLI fallback: `git worktree add ../<repo>-<slug> -b <branch>`, work there, `git worktree remove` when done.
- **Naming**: worktree dir `<repo>-<loop-or-feature-slug>`; branch matches the slug used in `spec/loop/<loop-name>/` or `spec/feat/<slug>/`.
- **Cleanup**: a loop removes its own worktree after the verifier pass completes (success or terminal failure). Worktrees do not accumulate. If a loop dies mid-run, the next run's `loop-triage` reports orphaned worktrees as a finding.
- **Multi-worktree exploration** (from article 2's composition example): running the same finding in two worktrees with different approaches and having an adversarial judge pick the winner is a legitimate advanced pattern — documented, but explicitly flagged as multiplying token cost and requiring a declared fan-out in `loop.md`.

### 7.4 `docs/connectors.md` — NEW

Inventory table with explicit access tiers, seeded with the team's actual stack (per §10.3) plus what `docs/quality-and-verification.md` §8 already references:

```markdown
| Connector | Purpose | Access level | May be used by | Allowed at output tier |
|---|---|---|---|---|
| Slack MCP | Post findings, ask for review, receive triage requests | Write (post only; never delete/edit others' messages) | loop-triage, loop-verifier, humans | A, B, C |
| GitLab MCP | Read issues/MRs/pipelines; open MRs; comment; update tickets | Read (all) + Write (MR/comment/ticket only — never merge, never force-push, never edit protected branch settings) | explorer (read), implementer (write, post-verifier only) | C for writes; A/B for reads |
| AWS CloudWatch MCP | Error rates, alarms, log queries for deployed changes | Read-only | explorer, loop-verifier, humans | A, B, C |
| AWS Cost Explorer MCP | Spend and anomaly detection (incl. the loops' own model spend) | Read-only | explorer, humans | A, B, C |
| Google Drive / Docs / Sheets / Slides MCP | Read specs and requirement docs; write recurring reports (status digests, cost reports) | Read + Write (documents the team designates; never Drive-wide delete or permission changes) | explorer (read), loop-triage (write to designated report docs) | A, B, C |
| Grafana MCP | Production error rates, traces, dashboards | Read-only | explorer, loop-verifier, humans | A, B, C |
| Octocode MCP | Cross-repo code search | Read-only | explorer, humans (planning phase) | A, B, C |
| <your issue tracker> | Backlog read, ticket updates | Read + Write (ticket only) | explorer (read), implementer (write) | C for writes |
```

Governance rules to state alongside the table:
1. **Read-only by default.** A connector is registered read-only until someone deliberately promotes it and records why.
2. **No credential is scoped wider than the loop's output tier.** A tier-A loop gets read-only tokens, full stop — the guardrail is the token, not the prompt.
3. **Destructive operations are never available to an unattended loop**: no merge, no force-push, no delete, no permission changes, no message deletion.
4. **Every connector write is traceable** to the `inbox.md` finding that caused it (governance rule 4).
5. Cross-referenced from `docs/quality-and-verification.md` §8 and §11.

**Plus a wiring guide** (per §11.6) — the doc does not stop at the principle,
it shows the pattern that enforces it:

- **One MCP server entry per access level, not one per service.** The same
  service is registered twice under distinct names when it needs both:
  `gitlab-ro` (read-only token, available to `explorer` and every tier-A loop)
  and `gitlab-rw` (MR/comment scope only, available to the implementer in a
  tier-C loop). A tier-A loop that cannot see `gitlab-rw` cannot be
  prompt-talked into using it.
- **Scope the token, not the instructions.** Worked examples per connector of
  the minimum credential: a GitLab project access token with `read_api` for
  `gitlab-ro` vs. `api` for `gitlab-rw`; an AWS IAM role with
  `cloudwatch:Get*/Describe*` and `ce:GetCostAndUsage` and nothing else; a
  Slack app with `chat:write` and no `chat:write.customize`, no delete scope;
  a Google service account shared only into the specific Drive folder and the
  specific report Sheet, never Drive-wide.
- **Config sketch** showing which server names each agent/loop is allowed to
  load, with the mapping table from `loop.md`'s output tier → permitted server
  names, so the charter and the credential set are reviewed together.
- **Secret handling**: tokens live in the environment or the team's secret
  store, never in `loop.md`, never in a skill file, never in a finding. A
  finding that quotes a credential is itself an incident.
- **Rotation and revocation**: each entry names its owner and its expiry; a
  loop retired means its write-tier token is revoked, not left dormant.
- **Verification step**: before promoting a loop to tier B or C, confirm the
  read-only token actually fails on a write call. An untested boundary is an
  assumed one.

### 7.5 `spec/loop/CONVENTIONS.md` + `spec/loop/.gitkeep` — NEW

Mirrors `spec/feat/CONVENTIONS.md`:

```markdown
# Loop State — Conventions

Each autonomous loop gets its own subfolder under spec/loop/, parallel to how
spec/feat/ archives feature plans:

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

## Rules
1. loop.md is written before the loop runs for the first time, using the
   `loop-charter` skill. No charter, no loop.
2. state.md is overwritten each run with the latest cursor — it is not a log.
3. inbox.md entries are removed only once actioned — cross-reference the
   resulting spec/feat/<slug>/plan.md, commit, or MR link before removing.
4. archive.md is append-only, dated, one line minimum: what, why non-actionable.
5. One folder per loop; do not share a folder across unrelated loops.
6. Changing a loop's output tier is a charter edit, reviewed like any other
   change — never an in-flight decision by the agent.
```

Plus a **`loop.md` charter template** shipped in the same file:

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

### 7.6 `spec/loop/repo-maintenance/` — NEW (the seeded, self-hosted loop)

*(This is what makes the repo itself loop-runnable — annotation §10.2.)*

Ships with `loop.md` filled in, plus empty `state.md` / `inbox.md` / `archive.md` scaffolds. Charter summary:

- **Rung 3, output tier A.** Report-only. **No CI, no git hosting, no PR required** — it is started from a Claude Code session with `/loop` (or `/schedule` for persistence).
- **What it checks** — all mechanically checkable against this repo's own conventions:
  1. **Symlink integrity** — every `.claude/agents/*` and `.claude/commands/*` symlink resolves to an existing `.cursor/` target.
  2. **Index drift** — every skill folder in `.cursor/skills/` has a row in `SKILLS.md`, and vice-versa; every agent file has a row in `AGENTS.md`.
  3. **Cross-link integrity** — every relative markdown link in `README.md`, `AGENTS.md`, `SKILLS.md`, `CLAUDE.md`, `docs/`, and `spec/design/` points at a file that exists.
  4. **Plan hygiene** — `spec/feat/*/plan.md` with unchecked checklist items and no activity, or completed plans missing the outcome note required by `spec/feat/CONVENTIONS.md`.
  5. **Skill-graduation candidates** — entries under `PROJECT_MEMORY.md` "Recurring patterns" seen 3+ times, per the graduation rule in `SKILLS.md`.
  6. **Changelog staleness** — commits landed since the last `CHANGELOG.md` entry.
  7. **Loop hygiene** — orphaned worktrees; `inbox.md` findings older than the charter's staleness threshold.
All seven ship in the first version (§11.2). The noise risk in checks 3 and 6 is
handled in the charter rather than by dropping them: each check declares a
threshold and an ignore-list (e.g. changelog staleness only fires past N
commits or M days; cross-link checking skips external URLs and anchors). If a
check proves noisy in practice, the fix is a charter edit recorded as a
finding — which is itself the loop working as intended.

- **Stop condition**: every check has run and every finding is written to `inbox.md` or `archive.md`. Verifiable by a separate model reading the two files against the check list.
- **Why it's honest dogfooding**: each check is a real convention this repo already states and cannot currently enforce.

### 7.7 New agents

**`.cursor/agents/explorer.md`** (canonical) + **`.claude/agents/explorer.md`** (symlink, matching the existing pattern):

```markdown
---
name: explorer
description: Read-only discovery agent for autonomous loops. Scans the repo, CI, connectors, and trackers for actionable and non-actionable items and writes findings to spec/loop/<loop-name>/inbox.md or archive.md. Never implements.
model: <fast/cheap model — team's choice>
---

# Explorer Agent

Read-only. Runs the `loop-triage` skill inside the scope declared by the
loop's `loop.md` charter. Never edits source files, never opens MRs, never
writes production code, never uses a write-tier connector. Output is always a
written finding in spec/loop/<loop-name>/inbox.md (actionable) or archive.md
(not actionable) — never only a chat summary, because the session that held
that summary will not exist tomorrow.
```

**`.cursor/agents/loop-verifier.md`** + **`.claude/agents/loop-verifier.md`** (symlink):

```markdown
---
name: loop-verifier
description: Verifies output produced by an autonomous loop's implementer session against the finding's acceptance criteria and docs/quality-and-verification.md. Must run as a separate identity/session from the implementer. Gates commit finalization and all connector actions.
model: <strong model, high reasoning effort>
---

# Loop Verifier Agent

Third-party check on loop-produced changes — distinct from the plan-review
cycle (architect-reviewer / consistency-reviewer / risk-analyst), which
reviews plan *text* before implementation. This agent reviews *actual output*
after implementation, inside an unattended loop, before the work is called
done or any connector acts.

Structural reason it exists: the identity that produced the change cannot
decide the change is correct. Delegation covers execution, never judgment.

## Checklist
1. Tests pass, lint clean — per docs/quality-and-verification.md §7.
2. Where the project has a runnable UI, runtime verification per
   docs/quality-and-verification.md §11: dev server, interact, console, trace.
3. Output matches the finding's acceptance criteria.
4. No scope creep beyond the inbox.md finding that triggered it.
5. No output-tier violation (governance rule 3).
6. Traceability: change references the finding + skill used (governance rule 4).

## Output
Pass → work is done; tier-C connector actions permitted.
Fail → finding returned to spec/loop/<loop-name>/inbox.md with the failure
reason. No silent retry.
```

`AGENTS.md` gains a **"Loop agents"** subsection after "Multi-agent review cycle", stating plainly: review-cycle agents check a *plan* before code exists; loop agents (`explorer`, `loop-verifier`) check *discovery* and *output* in an unattended context, and must never share an identity with the implementer.

### 7.8 New skills (three — per §11.1)

**`.cursor/skills/loop-triage/SKILL.md`** + **`.claude/commands/loop-triage.md`** (symlink):

```markdown
---
name: loop-triage
description: Discovery and triage procedure for autonomous loops — reads the loop's charter, scans the sources in its scope, and writes classified findings to spec/loop/<loop-name>/inbox.md or archive.md.
---

# Loop Triage

## When to use
Invoked by the explorer agent at the start of every loop run.

## Procedure
1. Read spec/loop/<loop-name>/loop.md — scope, exclusions, output tier.
   If no charter exists, stop and report; do not improvise a scope.
2. Read state.md for where the last run stopped.
3. Scan only the sources the charter lists (repo files, CI status, open
   spec/feat/*/plan.md checklists, PROJECT_MEMORY.md "Recurring patterns",
   read-tier connectors).
4. Classify each finding: actionable (clear next step, bounded scope,
   mechanically checkable acceptance criteria) vs. non-actionable (needs human
   judgment, out of scope, duplicate, subjective).
   A finding without a checkable acceptance criterion is non-actionable by
   definition — say so rather than inventing one.
5. Write actionable findings to inbox.md with: what, where, why, proposed
   acceptance criteria, suggested output tier. Non-actionable → archive.md
   with a dated one-line reason.
6. Deduplicate against existing inbox.md entries; never file the same finding twice.
7. Update state.md with the run timestamp and cursor.

## Output
inbox.md and archive.md updated; state.md cursor advanced. No code changes.

## Rules
Read-only. Never implements. Never removes an existing inbox.md entry (that
happens only once actioned, per spec/loop/CONVENTIONS.md). Never exceeds the
charter's scope. Never uses a write-tier connector.
```

**`.cursor/skills/loop-verify/SKILL.md`** + **`.claude/commands/loop-verify.md`** (symlink):

```markdown
---
name: loop-verify
description: Verification procedure run by the loop-verifier agent against output produced inside an autonomous loop, before the work is called done or any connector acts.
---

# Loop Verify

## When to use
Invoked by the loop-verifier agent after an implementer session completes work
triggered by a spec/loop/<loop-name>/inbox.md finding.

## Procedure
1. Run the project's test suite and linter for the touched area.
2. Runtime check where a runnable surface exists: start the dev server, open
   the changed page/route, interact with the change, capture before/after,
   read the console for new errors or warnings, run a performance trace where
   the finding mentions performance. A failure at any step means fix and
   restart from step 1 — never hand back partial work.
3. Compare output against the finding's acceptance criteria (and the relevant
   spec/feat/<slug>/plan.md if one was created).
4. Confirm no scope creep beyond the finding.
5. Confirm the output tier in loop.md was not exceeded.
6. Confirm traceability: commit/MR references the finding and skill(s) used.
7. Record Pass/Fail with reasons in the finding's entry.

## Output
Pass → work is done; tier-C connector actions (MR, ticket) permitted.
Fail → finding returned to inbox.md with the failure reason attached.

## Rules
Must run as a session/identity distinct from the implementer (governance
rule 1). Never edits code — only approves or bounces back. Never raises a turn
cap or re-runs the implementer itself.
```

**`.cursor/skills/loop-charter/SKILL.md`** + **`.claude/commands/loop-charter.md`** (symlink):

```markdown
---
name: loop-charter
description: Procedure for writing or revising a loop's charter (spec/loop/<loop-name>/loop.md) — scope, cadence, output tier, a mechanically checkable stop condition, abort criteria, and attention budget. Run before a loop's first run and whenever its tier or scope changes.
---

# Loop Charter

## When to use
Before any loop runs for the first time (governance rule 2: no charter, no
loop), and again whenever the loop's scope, cadence, or output tier changes.

## Procedure
1. State the purpose in one sentence. If it takes two, the loop is doing two
   jobs — split it into two loops.
2. Pick the rung (2/3/4) and the output tier (A/B/C). Default to the lowest
   of each that can deliver the purpose. Promotion needs evidence, not intent
   (see the promotion rule in spec/design/06_loop_engineering.md).
3. Write the stop / done condition. Apply the **separate-model test**: could a
   different model, seeing only the loop's output files and this sentence,
   decide pass or fail without judgment? If not, rewrite it. If it cannot be
   rewritten that way, the task is not a loop — send it back to Tier 1 or 2.
4. Write the abort criteria: a turn cap, the no-improvement rule, and the
   red-flag halts.
5. Declare scope explicitly on both sides: what it reads, and what it must
   never touch. Name the connectors and their access level per
   docs/connectors.md.
6. Declare cadence, fan-out, and the models for explorer / implementer /
   verifier. Check the fan-out against the attention budget (default 3
   concurrent loops per reviewer).
7. Name the human owner and the audit cadence — who reads the output, how
   often, and how deeply.
8. For tiers B and C, confirm the credential set matches the tier before the
   first run (docs/connectors.md wiring guide).

## Output
A complete spec/loop/<loop-name>/loop.md matching the template in
spec/loop/CONVENTIONS.md, plus empty state.md / inbox.md / archive.md.

## Rules
Never start a loop with an unwritten or partial charter. Never soften a stop
condition to make a task loop-able — an untestable finish line is the signal
to *not* build the loop. Charter edits are reviewed like any other change; an
agent never changes its own tier mid-run (governance rule 3).
```

`SKILLS.md` gains index rows for `loop-charter`, `loop-triage`, and `loop-verify`.

### 7.9 Cross-doc touch-ups

| File | Change |
|---|---|
| `README.md` | New "Loop Engineering" section (short, links to `spec/design/06_loop_engineering.md`, `spec/loop/CONVENTIONS.md`, `docs/worktrees.md`, `docs/connectors.md`); add both source articles under "References"; mention that this repo ships a runnable `repo-maintenance` loop. |
| `AGENTS.md` | New "Loop agents" subsection (§7.7); agent table gains `explorer` and `loop-verifier`. |
| `SKILLS.md` | Index gains `loop-charter`, `loop-triage`, `loop-verify`. |
| `docs/quality-and-verification.md` | New **§11 "Autonomous loop verification"**: verifier ≠ implementer, the runtime-verification depth expectation, output-tier bounds, and a pointer to `spec/design/06_loop_engineering.md § Governance`. Add anti-rationalization rows: *"The loop already verified it"* → a loop's self-report is not verification; *"It's just a report-only loop, no need for a charter"* → no charter, no loop. |
| `PROJECT_MEMORY.md` | No fabricated entries (see §10.5) — left as-is pending real usage. |

---

## 8. Proposed directory tree (after adaptation)

```
spec/
├── design/
│   ├── 00_pipeline_tiers.md        (MODIFIED — Tier 3 added)
│   ├── 01_research_phase.md
│   ├── 02_planning_phase.md
│   ├── 03_annotation_cycle.md
│   ├── 04_implementation_phase.md
│   ├── 05_feedback_and_supervision.md
│   └── 06_loop_engineering.md      (NEW — includes the governance section)
├── feat/
│   ├── CONVENTIONS.md
│   └── loop-engineering/
│       └── plan.md                 (this file)
└── loop/                           (NEW)
    ├── CONVENTIONS.md              (NEW — incl. the loop.md charter template)
    └── repo-maintenance/           (NEW — seeded, runnable, output tier A)
        ├── loop.md
        ├── state.md
        ├── inbox.md
        └── archive.md

docs/
├── quality-and-verification.md     (MODIFIED — §11 added)
├── worktrees.md                    (NEW)
└── connectors.md                   (NEW)

.cursor/agents/
├── explorer.md                     (NEW)
└── loop-verifier.md                (NEW)
.claude/agents/
├── explorer.md                     (NEW — symlink)
└── loop-verifier.md                (NEW — symlink)

.cursor/skills/
├── loop-charter/SKILL.md           (NEW)
├── loop-triage/SKILL.md            (NEW)
└── loop-verify/SKILL.md            (NEW)
.claude/commands/
├── loop-charter.md                 (NEW — symlink)
├── loop-triage.md                  (NEW — symlink)
└── loop-verify.md                  (NEW — symlink)
```

`07_loop_governance.md` is **not** created — governance lives in `06` (§10.1).

---

## 9. Practical value: how we will actually use this

*(Requested during annotation. These ship as the "Prompt / setup examples" section of `spec/design/06_loop_engineering.md`, so they are copy-pasteable rather than theoretical. Each names its rung, output tier, and the concrete waste it removes.)*

### 9.1 Repo maintenance — this template, on itself
**Rung 3 · Tier A · weekly · no CI required**

```
/loop 24h Run the loop-triage skill against spec/loop/repo-maintenance/loop.md.
Write findings to spec/loop/repo-maintenance/inbox.md. Do not implement anything.
```
Catches broken `.claude` → `.cursor` symlinks, `SKILLS.md`/`AGENTS.md` index drift, dead cross-links, plans missing their outcome note, and recurring-pattern entries that have earned a skill. **Value**: this template's conventions currently rely on human memory; nothing enforces them. A tier-A loop turns "we should keep the index in sync" into a weekly finding list, at zero infrastructure cost.

### 9.2 Plan-drift sentinel — the annotation cycle's blind spot
**Rung 3 · Tier A · daily**

Compares each `spec/feat/<slug>/plan.md` checklist against what actually landed in git, and flags the divergence: items checked with no matching commit, commits touching a feature area whose plan checklist never moved, plans whose acceptance criteria were never confirmed. **Value**: `docs/quality-and-verification.md` §10 says "code that contradicts the plan without an updated plan is a defect" — this is the first mechanism that can actually detect one.

### 9.3 Bug-fix goal loop — bounded execution of one ticket
**Rung 2 · Tier B or C · on demand**

```
/goal Fix the finding in spec/loop/<name>/inbox.md#<id>.
Done when the failing test <name> passes, the full suite is green, and lint is clean.
Do not change the public API of <module>. Do not touch files outside <path>.
Abort if 2 consecutive turns show no improvement. Stop after 8 turns.
Then hand off to the loop-verifier agent before pushing anything.
```
Runs in its own worktree so it never collides with the developer's live session. **Value**: the highest-confidence delegation in the article's own matrix — well-specified, mechanically checkable, low risk — and the one that reclaims the most hours.

### 9.4 MR babysitter — GitLab
**Rung 3 · Tier C · every 15–30 min while an MR is open**

```
/loop 20m Check my open GitLab MRs. Summarize new review comments and failing
pipelines. For comments that are mechanical (lint, naming, missing test), apply
the fix in a worktree, run loop-verify, push to the MR branch. Anything requiring
a judgment call goes to spec/loop/mr-babysitter/inbox.md and a Slack ping to me.
```
**Value**: kills the review-latency dead time — the loop drains the mechanical half of review feedback while you are in another context, and the judgment half arrives in Slack as a short list instead of a notification stream.

### 9.5 Deploy watch — AWS CloudWatch + Grafana
**Rung 4 · Tier A · triggered post-deploy, then hourly for 6h**

Reads error rates, alarms, and traces for the deployed change; compares against the pre-deploy baseline; writes a verdict to `inbox.md` and posts a one-paragraph summary to Slack; escalates on threshold breach. Never rolls back — that is a judgment call. **Value**: `docs/quality-and-verification.md` §8 already *requires* post-deployment verification and it is the step most often skipped because a human has to remember to look. This makes it automatic and read-only.

### 9.6 Cost watchdog — AWS Cost Explorer + Google Sheets + Slack
**Rung 4 · Tier A · weekly**

Pulls week-over-week spend by service, flags anomalies above a declared threshold, appends the numbers to a shared Google Sheet, posts the delta to Slack. **Includes the loops' own model spend**, so the orchestration tax is measured rather than assumed. **Value**: governance rule 7 says cost must be a conscious choice; this is the instrument that makes it one.

### 9.7 Documentation drift — the documentation-architect agent, on a schedule
**Rung 3 · Tier B · weekly**

`explorer` diffs the week's merged changes against `README.md`, `docs/`, and the ADR set; actionable drift becomes an `inbox.md` finding; the `documentation-architect` agent drafts the update in a worktree; `loop-verifier` checks it references a real change and invents nothing. Output stops at a reviewed branch. **Value**: documentation decay is the textbook "delegate fully" task — well-specified, low risk, and reliably deprioritized by humans.

### 9.8 Skill-graduation loop — closing the SKILLS.md lifecycle
**Rung 3 · Tier A · fortnightly**

Reads `PROJECT_MEMORY.md` "Recurring patterns" plus recent session logs, counts repeats, and when a pattern crosses the threshold already written in `SKILLS.md` ("improvised more than twice"), files a finding proposing a new skill and pointing at the `skill-evolution` procedure. **Value**: `SKILLS.md` defines graduation but nothing counts. This does the counting.

### 9.9 Requirements-intake loop — Google Drive/Docs + Slack
**Rung 4 · Tier A · daily**

Watches a designated Drive folder and Slack channel for new or edited requirement docs; summarizes what changed; cross-references against open `spec/feat/*/plan.md` files; flags contradictions between a new requirement and a plan already in flight. **Value**: this is the "Requirements Reconciliation Agent" that `AGENTS.md` describes but that has no trigger today. A loop gives it one.

### 9.10 Composition — the advanced pattern
**Rungs 2+4 combined · Tier C**

```
/schedule daily 09:00 Check GitLab for issues labelled "bug". For each, run
/goal to implement a fix until the reproducing test passes and the suite is
green; each fix in its own worktree, max 2 in parallel; loop-verifier gates
every MR; anything not fixed in 8 turns goes to inbox.md with the transcript.
```
**Value**: this is the top rung, and it is deliberately last on the list — the promotion rule in §5 means no team runs this until the same task has succeeded at rung 3 under observation.

### 9.11 Adoption sequence for a consumer project

1. Run `/loop-charter` to write `spec/loop/repo-maintenance/loop.md`, tier A. Run the loop manually once.
2. Read every finding by hand for two weeks. Fix the charter where it produced noise.
3. Promote one narrow, well-specified finding type to tier B behind `loop-verifier`.
4. Add connectors read-only first; promote a single connector to write only when a tier-C loop genuinely needs it.
5. Only then consider rung 4. Declare the attention budget before, not after.

---

## 10. Annotation round 1 — resolutions

| # | Question | Your note | How this plan now handles it |
|---|---|---|---|
| 1 | Two docs (`06` + `07`) or one? | *"governance must be folded into the loop engineering doc"* | **Resolved.** `07_loop_governance.md` dropped. Governance is a section of `06_loop_engineering.md` (§7.2), now with 9 rules — the original 7 plus the charter requirement and the stall-halt rule from article 2. All cross-references updated (§7.1, §7.4, §7.9, §8). |
| 2 | Exportable guidance only, or dogfood a real loop here? | *"enable this repo to have loop engineering executed too. CI/git PRs not mandatory"* | **Resolved, and it reshaped the plan.** New §6 introduces **output tiers A/B/C**, where tier A (report-only) requires no CI, no git hosting, and no PR. New §7.6 seeds a real, runnable `spec/loop/repo-maintenance/` loop with seven checks against this repo's own conventions, started from a session with `/loop`. Governance rule 3 is now "never exceed your declared output tier" rather than the old PR-centric rule; "no unattended merge" survives as a tier-C constraint. CI is an explicitly optional appendix. |
| 3 | Connector placeholders? | *"Slack, Google Docs/Sheets/Slides/Drive, GitLab, AWS (CloudWatch, Cost Explorer)"* | **Resolved.** `docs/connectors.md` (§7.4) is seeded with all of them, each with an access level, permitted roles, allowed output tiers, and explicit destructive-operation prohibitions. Git hosting is GitLab, not GitHub. Grafana and Octocode are retained from `docs/quality-and-verification.md` §8. Each appears in at least one §9 recipe. |
| 4 | New agents vs. reusing `risk-analyst`? | *OK* | Unchanged: `explorer` + `loop-verifier` as new agents, with the rationale now sharpened by article 2's "delegate execution, never judgment" and stated explicitly in the agent file. |
| 5 | Design doc carrying non-incident-derived hard rules? | *OK* | Unchanged, and now noted inline in `06` itself rather than in a separate governance file. `PROJECT_MEMORY.md` stays incident-only. |
| 6 | Two skills or one? | *OK* | Unchanged: `loop-triage` and `loop-verify` stay separate. `loop-verify` grew the runtime-verification steps from article 2. |

### Changes driven by the second article (not from an annotation)

| Addition | Why |
|---|---|
| §5 — the four-rung ladder + the promotion rule | Teams start at rung 4 and get burned. The rungs make graduation explicit and evidence-based. |
| §5 — mandatory `/goal` template with abort criteria + turn cap | Article 2's most concrete, most skippable advice. Encoded as a rejection criterion, not a suggestion. |
| §5 — red-flag stall detection | "Same command, same result" is a defined halt condition, not a judgment call made mid-run. |
| §7.5 / §4 — the `loop.md` charter file | Loops are session-scoped and expire in ~7 days; an undeclared stop condition dies with the session. The charter makes the contract durable and reviewable. |
| §6 — output tiers | Required by annotation 2, but also the cleanest expression of "a loop never exceeds its mandate." |
| §7.2 — delegation matrix, attention budget, "loops are the 20%" framing | Positions Tier 3 as consuming Tiers 1–2 rather than competing with them, which is the framing that makes this addition coherent with the rest of the template. |
| §7.8 — runtime verification steps in `loop-verify` | Green tests are the floor. The dev-server/console/trace sequence is what stops a loop shipping a desktop win that is a mobile regression. |
| §9 — practical recipes | Makes the capability concrete and copy-pasteable rather than architectural. |

---

## 11. Annotation round 2 — resolutions

No open questions remain. All six were answered; the plan below reflects them.

| # | Question | Your note | How this plan now handles it |
|---|---|---|---|
| 1 | Charter as a third skill? | *"Add a third skill for this matter"* | **Resolved.** New `loop-charter` skill in §7.8, with the **separate-model test** as its core step: if a different model could not decide pass/fail from the stop condition alone, the sentence gets rewritten — and if it cannot be rewritten that way, the task is sent back to Tier 1/2 instead of being forced into a loop. Three skills now ship. `spec/loop/CONVENTIONS.md` rule 1, the tree (§8), the adoption sequence (§9.11), and `SKILLS.md` all updated. |
| 2 | Ship all seven `repo-maintenance` checks, or start with four? | *"Keep all of them"* | **Resolved.** All seven ship. Noise in checks 3 and 6 is handled by per-check thresholds and ignore-lists declared in the charter, not by dropping checks. A noisy check becomes a charter-edit finding — the loop reporting on itself, which is the mechanism working. |
| 3 | Attention budget default? | *"define the default as 3"* | **Resolved.** Governance rule 7 and the "Attention budget" section of `06` now state **3 concurrent loops per reviewer** as the default, with the reasoning (a reviewer who cannot read the output is approving diffs, i.e. the cognitive surrender the tier exists to prevent). Raising it requires writing down the new number and the reason. |
| 4 | CI appendix: GitLab only, or both? | *"Only Gitlab CI"* | **Resolved.** The optional appendix in `06` is a GitLab CI scheduled pipeline only — no GitHub Actions variant. Matches the connector stack from round 1. The appendix explicitly frames itself as showing the shape, not implying a loop needs a pipeline. |
| 5 | Duplicate the ladder into `00_pipeline_tiers.md`? | *"No"* | **Resolved.** The ladder lives only in `06_loop_engineering.md`. The Tier 3 block in `00` gets a three-line pointer ("Tier 3 has four rungs, defined once, in `06`") and nothing more, so the two docs cannot drift. |
| 6 | Connector credentials: principle or concrete pattern? | *"let's add MCP connectors guide"* | **Resolved.** `docs/connectors.md` (§7.4) gains a wiring guide: **one MCP server entry per access level, not per service** (`gitlab-ro` / `gitlab-rw`), minimum-credential examples per connector (GitLab `read_api` vs `api`; IAM limited to `cloudwatch:Get*/Describe*` + `ce:GetCostAndUsage`; Slack `chat:write` only; a Google service account shared into one folder and one Sheet), an output-tier → permitted-server-name mapping reviewed alongside the charter, secret handling, rotation/revocation, and a pre-promotion test that the read-only token *actually fails* on a write. |

### Knock-on effects worth naming

- **Governance rule 2 gained teeth.** "No charter, no loop" was a rule nobody had a procedure for. `loop-charter` is that procedure, and its separate-model test is where an undeliverable loop gets rejected — before it is built, not after it has produced noise for two weeks.
- **The credential is now the primary guardrail.** With per-access-level MCP entries (Q6), output tiers (§6) stop being a prompt-level promise and become an infrastructure fact: a tier-A loop that never loads `gitlab-rw` cannot write, regardless of what any instruction says. The prompt is the second line of defence.
- **Answers 3 and 6 close the two loops most likely to fail quietly** — over-parallelization and over-permissioned tokens — which are also the two the source articles flag hardest.

---

## 12. Task checklist (for the implementation phase, once annotated)

**Phase A — Design docs**
- [x] `spec/design/00_pipeline_tiers.md`: Tier 3 section (with a pointer to the ladder, not a copy of it) + two tier-selection table rows
- [x] `spec/design/06_loop_engineering.md`: new file — governance section (9 rules, incl. the default budget of 3 concurrent loops per reviewer), the four-rung ladder (single source), output tiers, delegation matrix, verification depth, practical recipes, and the optional GitLab CI appendix

**Phase B — Conventions & directories**
- [x] `spec/loop/CONVENTIONS.md` (incl. the `loop.md` charter template) + `spec/loop/.gitkeep`
- [x] `docs/worktrees.md`
- [x] `docs/connectors.md` (seeded: Slack, GitLab, AWS CloudWatch, AWS Cost Explorer, Google Drive/Docs/Sheets/Slides, Grafana, Octocode) + the MCP wiring guide (per-access-level server entries, minimum credentials, rotation, boundary test)

**Phase C — The seeded self-hosted loop**
- [x] `spec/loop/repo-maintenance/loop.md` (charter, rung 3, output tier A) — authored by following the `loop-charter` skill's procedure, so the skill is exercised at least once before it ships
- [x] All seven checks declared, each with its threshold and ignore-list
- [x] `spec/loop/repo-maintenance/{state,inbox,archive}.md` scaffolds
- [x] Dry-run the loop manually once and confirm every declared check produces a real, non-hallucinated finding or a clean pass — done 2026-08-18: 5 checks clean (→ `archive.md`), 2 real findings (→ `inbox.md`); finding #1 (changelog staleness) actioned same session via the `changelog` skill; finding #2 (AGENTS.md index drift) left open for a human decision

**Phase D — Agents**
- [x] `.cursor/agents/explorer.md`
- [x] `.claude/agents/explorer.md` (symlink)
- [x] `.cursor/agents/loop-verifier.md`
- [x] `.claude/agents/loop-verifier.md` (symlink)
- [x] `AGENTS.md`: "Loop agents" subsection + table rows

**Phase E — Skills**
- [x] `.cursor/skills/loop-charter/SKILL.md`
- [x] `.claude/commands/loop-charter.md` (symlink)
- [x] `.cursor/skills/loop-triage/SKILL.md`
- [x] `.claude/commands/loop-triage.md` (symlink)
- [x] `.cursor/skills/loop-verify/SKILL.md`
- [x] `.claude/commands/loop-verify.md` (symlink)
- [x] `SKILLS.md`: index rows for all three

**Phase F — Cross-doc integration**
- [x] `README.md`: "Loop Engineering" section + both article references + note that the repo ships a runnable loop
- [x] `docs/quality-and-verification.md`: new §11 + two anti-rationalization rows
- [x] `CHANGELOG.md`: entry for this implementation (via the `changelog` skill, once work lands)

**Phase G — Review & verification**
- [x] Annotation rounds 1 and 2 resolved (§10, §11) — no open questions remain
- [x] Run the multi-agent review cycle (`architect-reviewer` → `consistency-reviewer` → `risk-analyst`) on the finalized plan — run retroactively 2026-08-18, after implementation, since the user explicitly directed full implementation now rather than gating on this cycle first; see verdicts below
- [x] This repo has no test suite or linter, so "verification" for implementation = doc cross-link check + symlink integrity check (`.claude/*` resolve to `.cursor/*`) + a successful dry-run of `repo-maintenance` + Risk Analyst Pass verdict — cross-link and symlink checks both clean (see `spec/loop/repo-maintenance/archive.md`); dry-run done (see above)
- [x] Add the outcome note to this plan per `spec/feat/CONVENTIONS.md` once implementation lands — see top of file

---

## 13. Acceptance criteria

- Every new doc is cross-linked from at least one of `README.md`, `SKILLS.md`, or `AGENTS.md`, matching how existing docs are discoverable.
- The `.claude/*` ↔ `.cursor/*` symlink pattern is preserved for the two new agents and three new skills (per the Windows/symlink note in `README.md`).
- Governance rules live in `06_loop_engineering.md`; no `07_` file exists.
- **A developer can run a loop against this repo with no CI, no git hosting, and no PR** — demonstrated by a successful manual dry-run of `spec/loop/repo-maintenance/`, producing at least one real finding written to disk.
- Every §9 recipe names a rung, an output tier, and a mechanically checkable stop condition — none is aspirational.
- `docs/connectors.md` lists every connector from annotation 3, each with an access level and permitted output tiers, and its wiring guide shows per-access-level MCP server entries with minimum credentials — the guardrail is demonstrably the token, not the prompt.
- The four-rung ladder appears in exactly one file (`06_loop_engineering.md`); `00_pipeline_tiers.md` links to it and does not restate it.
- The attention-budget default (3 concurrent loops per reviewer) is stated in `06_loop_engineering.md` and used in `spec/loop/repo-maintenance/loop.md`.
- The `repo-maintenance` charter is produced by running the `loop-charter` skill, and every one of its seven checks carries a threshold or ignore-list.
- The optional CI appendix covers GitLab CI only.
- Nothing contradicts the Iron Law, the existing quality gates, or `spec/feat/CONVENTIONS.md`.
- Tier 3 is clearly additive: Tiers 1–2 and the five-phase pipeline are unchanged, and `06` states explicitly that loops consume the earlier phases rather than replace them.
- The multi-agent review cycle reaches a Pass verdict before implementation begins.
