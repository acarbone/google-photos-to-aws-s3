# Phase 6: Loop Engineering (Tier 3 only)

## Objective

Let scheduled or event-driven agent runs discover work, triage it, and either
act on it or surface it for a human — without a person prompting each step,
while preserving the same verification discipline the interactive phases
require.

This phase only applies to Tier 3 work (see `00_pipeline_tiers.md`). Tiers 1
and 2 — a human driving a session turn by turn — are unchanged by anything in
this document.

---

## Where loops fit

Loops are roughly the 20% of the work that is execution. The 80% — research,
exploration, understanding constraints — remains Phases 01–03. A loop is only
as safe as the plan, skills, and quality gates it runs against. This repo's
existing conventions (the plan as source of truth, skills as institutional
memory, `PROJECT_MEMORY.md`, the quality gates in
`docs/quality-and-verification.md`) are precisely the deterministic
scaffolding a loop needs in order to have a checkable "done."

**Tier 3 consumes Tiers 1–2. It does not replace them.**

---

## The primitives

| Primitive | Use | Stops when |
|---|---|---|
| `/goal` | One bounded task with a measurable finish line, checked by an *independent evaluator* against hard rules only (never taste) | Criteria met or turn cap reached |
| `/loop [interval]` | Recurring prompt on a fixed interval, cron-like, session-scoped | Manual stop or session end |
| `/schedule` | Persistent cloud routine | Disabled |

**Lifecycle facts that shape our conventions**: `/loop` is session-scoped,
recurring loops **expire ~7 days** after creation, and starting a new
conversation stops them. Use `--resume` / `--continue` to re-enter inside that
window; use `/schedule` for anything that must outlive a session. **Never
treat conversation context as loop memory** — this is the concrete reason
external memory (`spec/loop/<loop-name>/`, § below) is mandatory, not
stylistic.

---

## The ladder (rungs 1→4) and the promotion rule

| Rung | Loop type | Triggered by | Stopped by | This repo's mapping | Prerequisite before you climb here |
|---|---|---|---|---|---|
| 1 — Manual | Plain session | A human prompt each turn | Human direction | Already covered: Phases 01–05, Tiers 1–2 | — |
| 2 — Goal-based | `/goal` | Success criteria | Criteria met or turn limit | Bounded execution of a **single** `inbox.md` finding or `plan.md` checklist item, with acceptance criteria copied verbatim as the stop condition | The finding must have a criterion a *separate* model can check mechanically |
| 3 — Time-based | `/loop [interval]` (or `/schedule`) | A fixed interval | Manual stop or session end | Recurring `loop-triage` runs writing to `spec/loop/<name>/inbox.md`. **Output tier A** (report-only) | `spec/loop/<name>/loop.md` charter exists |
| 4 — Proactive | Events/schedules, no human present | Each task exits at goal; routine runs until disabled | Unattended discovery **plus** execution and verification, output tier B or C | Rung 3 has run for at least one full review cycle with a human reading the output |

**Determinism is the gate.** Loops excel when "done" is measurable (test
passes, metric threshold, lint clean). They fail on vague criteria ("until the
UI is good"), subjective taste, and open-ended creative exploration.

**Promotion rule**: never deploy a rung-4 loop for a task that has not already
succeeded at rung 3 under human observation. A loop is promoted by evidence,
not by ambition.

---

## The six components, in this repo's terms

| Article term | This repo's artifact |
|---|---|
| Automations | `/loop`, `/goal`, `/schedule`, or an external scheduler, invoking the `loop-triage` skill |
| Worktrees | `docs/worktrees.md` |
| Skills | `loop-charter`, `loop-triage`, `loop-verify` (existing skill mechanism, unchanged) |
| Connectors | Read/write permission tiers, declared per loop |
| Sub-agents | `explorer` (discovery) → implementer → `loop-verifier` (QA), never one identity |
| External memory | `spec/loop/<loop-name>/{loop,state,inbox,archive}.md` |

---

## Output tiers A / B / C

Every loop declares exactly one output tier in its `loop.md`. The tier bounds
what the loop may touch, and therefore what infrastructure it requires.

| Tier | The loop may… | Requires | Verifier needed? | Example |
|---|---|---|---|---|
| **A — Report only** | Read, analyse, and write to `spec/loop/<name>/{inbox,archive,state}.md`. Optionally post a summary via a write-only chat connector. | Nothing beyond a working session. **No CI, no git hosting, no PR.** | No (nothing was changed) | `repo-maintenance` in this repo; cost watchdog; incident digest |
| **B — Local change** | Everything in A, plus write code/docs in an **isolated worktree** on a dedicated branch, and commit there. Never pushes, never touches the checked-out branch. | git only | **Yes** — `loop-verifier` before the commit is considered done | Doc-drift fixes; dependency bumps prepared for human review |
| **C — External action** | Everything in B, plus push and open a merge/pull request, and/or update a ticket through a connector. **Never merges.** | git hosting + configured connectors | **Yes** — verifier pass gates every connector call | Bug-fix loop that opens a GitLab MR |

**Tier A is the default and the recommended starting point.** Teams promote a
loop to B or C deliberately, by editing `loop.md` — never implicitly because
the agent found it convenient.

---

## Loop lifecycle (reference, output tier B)

1. Scheduler (or the developer) triggers a run.
2. `explorer` runs `loop-triage`: reads `state.md`, then CI status (if any),
   open `plan.md` checklists, stale annotation cycles, `PROJECT_MEMORY.md`
   "Recurring patterns", connector sources in scope.
3. Findings → `inbox.md` (actionable) / `archive.md` (not, with a dated
   reason). Nothing is reported only in chat.
4. Per actionable finding, if the charter's tier allows it: create an isolated
   worktree (`docs/worktrees.md`); an implementer session executes it under
   `/goal` with the finding's acceptance criteria as the stop condition.
5. `loop-verifier` — a separate session/identity — runs `loop-verify` against
   the acceptance criteria and the quality gates. Fail → back to `inbox.md`
   with the reason. No silent retry.
6. Tier C only: on pass, connectors open an MR/PR and/or update a ticket.
   Never a merge.
7. `state.md` is updated with what ran and where it stopped.
8. Anything unresolved stays in `inbox.md` for a human. The worktree is
   removed.

---

## Writing a goal

```
/goal <task>. Done when <mechanically checkable condition>.
Do not change <explicit out-of-scope boundary>.
Each turn must improve at least one measured value;
abort if 2 consecutive turns show no improvement.
Stop after <N> turns.
```

Every element is mandatory. A `/goal` without an abort criterion and a turn
cap is a rejected loop definition, not a loop.

---

## When loops fail — red flags

- Same command repeating with no change in result → halt, log the stall.
- Same result twice without variation → halt.
- Completion criterion is subjective → the loop should never have been
  created.
- Turn cap reached → hand back to a human; do not raise the cap unattended.

Both stall conditions mean **stop, not "try harder."** The loop writes the
stall to `inbox.md` as a finding — it does not retry with a different
phrasing of the same command.

---

## Delegation boundary

| Delegate fully | Monitor closely | Never delegate |
|---|---|---|
| Docs for already-implemented features; test-coverage checks; low-risk, well-specified tasks with clear constraints | Ambiguous specs; anything touching auth, security, payments, or system access | The judgment call itself — whether the work is right and done |

Delegate *execution*, never the *judgment call*. One agent drafts, a
**separate** agent verifies — the drafting agent structurally cannot decide it
is "done" (an agent optimizing desktop performance can miss the mobile
regression it caused).

---

## Verification depth (from practical loop engineering)

Green tests are the floor, not the bar. Where the project has a runnable UI,
the verifier mimics human review: start the dev server, open the changed
page, interact, screenshot before/after, check the console for new errors,
run a performance trace. Any failure → fix and rerun from step 1; never hand
back partial work.

---

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

---

## Governance — non-negotiable rules

1. **Verifier ≠ implementer.** The identity that writes the change never
   approves it.
2. **Every loop has a written charter** (`loop.md`) with a mechanically
   checkable stop condition, a turn/abort cap, and a declared output tier. No
   charter, no loop.
3. **A loop never exceeds its declared output tier.** Tier A never writes
   code; tier B never pushes; tier C never merges to a protected branch.
4. **Full traceability.** Every autonomous commit, MR, or ticket update
   references the `inbox.md` finding and the skill(s) used. No anonymous
   autonomous changes.
5. **Non-actionable findings are archived, not deleted** — dated, with a
   reason, so patterns can be re-evaluated.
6. **Human audit cadence.** Loop output is sampled and *read* by a human on a
   declared cadence, not just diff-approved. This is the direct mitigation for
   comprehension debt and cognitive surrender.
7. **Cost and attention awareness.** Cadence, fan-out, and model choice are
   stated in the charter so cost is a conscious decision, not a surprise.
   **Default attention budget: 3 concurrent loops per reviewer.** A team may
   raise it only by writing the new number, and the reason for it, into its
   own docs.
8. **A loop is not exempt from `docs/quality-and-verification.md`.** Tests,
   lint, acceptance criteria, and artifact updates apply to loop-produced
   changes exactly as to human ones.
9. **Stalls halt.** Red-flag conditions stop the loop and produce a finding;
   they never trigger an unattended retry or a raised turn cap.

**A note on enforcement layers**: the connector boundary is enforced at the
credential layer — a tier-A loop cannot load a write-tier
MCP server, regardless of what any prompt says. The local-filesystem boundary
("explorer never edits source files," "tier A never writes code") does not
currently have an equivalent structural backstop in this template — it is
enforced the same way every other agent "never" rule in this repo is: as an
instruction, checked in practice by `loop-triage`'s own diff-scope
self-check (step 8) and by human audit. A team running loops unattended,
without a person available to catch a mis-scoped run, should pair the
charter with tool-level permissions (e.g. restrict `explorer`'s file-write
tools to `spec/loop/**` in Claude Code / Cursor settings) rather than relying
on the charter and agent prompt alone.

*(This document carries hard rules not derived from a repo incident — a
departure from how `PROJECT_MEMORY.md` is normally populated. That's
intentional for a design doc that defines a new capability from first
principles; `PROJECT_MEMORY.md` itself stays incident-only.)*

---

## Prompt / setup examples

Each recipe below names its rung, output tier, and the concrete waste it
removes. They are copy-pasteable, not theoretical.

### Repo maintenance — this template, on itself
**Rung 3 · Tier A · weekly · no CI required**

```
/loop 24h Run the loop-triage skill against spec/loop/repo-maintenance/loop.md.
Write findings to spec/loop/repo-maintenance/inbox.md. Do not implement anything.
```
Catches broken `.claude` → `.cursor` symlinks, `SKILLS.md`/`AGENTS.md` index
drift, dead cross-links, plans missing their outcome note, and
recurring-pattern entries that have earned a skill. **Value**: this
template's conventions currently rely on human memory; nothing enforces them.
A tier-A loop turns "we should keep the index in sync" into a weekly finding
list, at zero infrastructure cost.

### Plan-drift sentinel — the annotation cycle's blind spot
**Rung 3 · Tier A · daily**

Compares each `spec/feat/<slug>/plan.md` checklist against what actually
landed in git, and flags the divergence: items checked with no matching
commit, commits touching a feature area whose plan checklist never moved,
plans whose acceptance criteria were never confirmed. **Value**:
`docs/quality-and-verification.md` §10 says "code that contradicts the plan
without an updated plan is a defect" — this is the first mechanism that can
actually detect one.

### Bug-fix goal loop — bounded execution of one ticket
**Rung 2 · Tier B or C · on demand**

```
/goal Fix the finding in spec/loop/<name>/inbox.md#<id>.
Done when the failing test <name> passes, the full suite is green, and lint is clean.
Do not change the public API of <module>. Do not touch files outside <path>.
Abort if 2 consecutive turns show no improvement. Stop after 8 turns.
Then hand off to the loop-verifier agent before pushing anything.
```
Runs in its own worktree so it never collides with the developer's live
session. **Value**: the highest-confidence delegation in the article's own
matrix — well-specified, mechanically checkable, low risk — and the one that
reclaims the most hours.

### MR babysitter — GitLab
**Rung 3 · Tier C · every 15–30 min while an MR is open**

```
/loop 20m Check my open GitLab MRs. Summarize new review comments and failing
pipelines. For comments that are mechanical (lint, naming, missing test), apply
the fix in a worktree, run loop-verify, push to the MR branch. Anything requiring
a judgment call goes to spec/loop/mr-babysitter/inbox.md and a Slack ping to me.
```
**Value**: kills the review-latency dead time — the loop drains the mechanical
half of review feedback while you are in another context, and the judgment
half arrives in Slack as a short list instead of a notification stream.

### Deploy watch — AWS CloudWatch + Grafana
**Rung 4 · Tier A · triggered post-deploy, then hourly for 6h**

Reads error rates, alarms, and traces for the deployed change; compares
against the pre-deploy baseline; writes a verdict to `inbox.md` and posts a
one-paragraph summary to Slack; escalates on threshold breach. Never rolls
back — that is a judgment call. **Value**:
`docs/quality-and-verification.md` §8 already *requires* post-deployment
verification and it is the step most often skipped because a human has to
remember to look. This makes it automatic and read-only.

### Cost watchdog — AWS Cost Explorer + Google Sheets + Slack
**Rung 4 · Tier A · weekly**

Pulls week-over-week spend by service, flags anomalies above a declared
threshold, appends the numbers to a shared Google Sheet, posts the delta to
Slack. **Includes the loops' own model spend**, so the orchestration tax is
measured rather than assumed. **Value**: governance rule 7 says cost must be a
conscious choice; this is the instrument that makes it one.

### Documentation drift — the documentation-architect agent, on a schedule
**Rung 3 · Tier B · weekly**

`explorer` diffs the week's merged changes against `README.md`, `docs/`, and
the ADR set; actionable drift becomes an `inbox.md` finding; the
`documentation-architect` agent drafts the update in a worktree;
`loop-verifier` checks it references a real change and invents nothing.
Output stops at a reviewed branch. **Value**: documentation decay is the
textbook "delegate fully" task — well-specified, low risk, and reliably
deprioritized by humans.

### Skill-graduation loop — closing the SKILLS.md lifecycle
**Rung 3 · Tier A · fortnightly**

Reads `PROJECT_MEMORY.md` "Recurring patterns" plus recent session logs,
counts repeats, and when a pattern crosses the threshold already written in
`SKILLS.md` ("improvised more than twice"), files a finding proposing a new
skill and pointing at the `skill-evolution` procedure. **Value**:
`SKILLS.md` defines graduation but nothing counts. This does the counting.

### Requirements-intake loop — Google Drive/Docs + Slack
**Rung 4 · Tier A · daily**

Watches a designated Drive folder and Slack channel for new or edited
requirement docs; summarizes what changed; cross-references against open
`spec/feat/*/plan.md` files; flags contradictions between a new requirement
and a plan already in flight. **Value**: this is the "Requirements
Reconciliation Agent" that `AGENTS.md` describes but that has no trigger
today. A loop gives it one.

### Composition — the advanced pattern
**Rungs 2+4 combined · Tier C**

```
/schedule daily 09:00 Check GitLab for issues labelled "bug". For each, run
/goal to implement a fix until the reproducing test passes and the suite is
green; each fix in its own worktree, max 2 in parallel; loop-verifier gates
every MR; anything not fixed in 8 turns goes to inbox.md with the transcript.
```
**Value**: this is the top rung, and it is deliberately last on the list —
the promotion rule above means no team runs this until the same task has
succeeded at rung 3 under observation.

### Adoption sequence for a consumer project

1. Run `/loop-charter` to write `spec/loop/repo-maintenance/loop.md`, tier A.
   Run the loop manually once.
2. Read every finding by hand for two weeks. Fix the charter where it
   produced noise.
3. Promote one narrow, well-specified finding type to tier B behind
   `loop-verifier`.
4. Add connectors read-only first; promote a single connector to write only
   when a tier-C loop genuinely needs it.
5. Only then consider rung 4. Declare the attention budget before, not after.

---

## Appendix — optional: running a loop from GitLab CI

CI is one scheduler among several and is **never required**: tier-A loops run
fine from a developer's session via `/loop` or `/schedule`. The example below
exists to show the *shape* — a scheduled pipeline invoking `loop-triage`,
committing the updated `spec/loop/<name>/` files back on a branch — not to
imply a loop needs a pipeline. GitLab CI only; there is no GitHub Actions
variant.

```yaml
# .gitlab-ci.yml (excerpt) — optional, tier-A loop on a schedule
loop-repo-maintenance:
  stage: scheduled
  rules:
    - if: '$CI_PIPELINE_SOURCE == "schedule" && $LOOP_NAME == "repo-maintenance"'
  script:
    - claude -p "Run the loop-triage skill against spec/loop/repo-maintenance/loop.md. Write findings to spec/loop/repo-maintenance/inbox.md. Do not implement anything."
    - git add spec/loop/repo-maintenance/
    - git commit -m "chore(loop): repo-maintenance run $(date -u +%Y-%m-%dT%H:%MZ)" || echo "no changes"
    - git push origin HEAD:loop/repo-maintenance-findings
```

Configure a GitLab **Scheduled Pipeline** with `LOOP_NAME=repo-maintenance` on
the desired cadence. The job commits to a dedicated `loop/*` branch, never to
the protected default branch — output tier A never pushes code changes, only
its own state files, and even those land on a branch a human reviews before
merging.
