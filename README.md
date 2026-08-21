# Spec-Driven Development Template

This repo is a **blueprint for a Spec-Driven approach** to developing new projects or updating existing ones. It gives you a repeatable process: research → planning → annotation cycles → implementation → feedback, so that the spec (not the chat) drives what gets built.

---

## What this repo is

- A **template and playbook** for running Spec-Driven development with AI (e.g. Cursor, Claude Code).
- Usable for **new projects** (scaffold and follow the phases) or **current projects** (apply the same phases to new features or refactors).
- The markdown artifacts (plans, research, phase guides) act as **shared mutable state** between you and the AI: you can think at your own pace, annotate exactly where something is wrong, and re-engage without losing context. You’re not explaining everything in chat—you’re pointing at the document and writing your correction there.

That is fundamentally different from steering implementation through chat. The plan is a structured, complete specification you can review as a whole. A chat is something you’d have to scroll through to reconstruct decisions. The plan wins every time.

---

## Why it works

- **Annotation cycles**: A few rounds of “I added notes, update the plan” turn a generic implementation plan into one that fits your system. The AI is strong at code and proposals; it doesn’t know your product priorities, user pain points, or the trade-offs you’re willing to make. The annotation cycle is where you inject that judgment.
- **Spec as the driver**: Implementation becomes mechanical, not creative—by design. You want implementation to be boring; the creative work happens in the annotation cycles. Once the plan is right, execution should be straightforward. Without a planning phase, the AI often makes a reasonable-but-wrong assumption early, builds on it, and you end up unwinding a long chain. A “don’t implement yet” guard removes that.
- **Single long sessions**: Research, planning, and implementation run in one long session instead of being split. One session can go from deep-reading a folder, through several plan-annotation rounds, to full implementation. The plan document is the persistent artifact that survives context compaction and stays in full fidelity; you can point the AI at it anytime.

---

## Documentation and process

Not every task needs the full process. Start here:

- **spec/design/00_pipeline_tiers.md** – When to use the lightweight path vs. the full pipeline.

The full five-phase process:

- **spec/design/01_research_phase.md** – Deep-read and research before planning.
- **spec/design/02_planning_phase.md** – Produce and refine the implementation plan.
- **spec/design/03_annotation_cycle.md** – How to annotate the plan and iterate with the AI.
- **spec/design/04_implementation_phase.md** – Executing the plan.
- **spec/design/05_feedback_and_supervision.md** – Feedback and oversight.

See also **AGENTS.md** (how agents are used, including the multi-agent review cycle and project memory), **SKILLS.md** (how skills are used and how they evolve), **PROJECT_MEMORY.md** (accumulated institutional knowledge), and **CHANGELOG.md** (work log). When a `docs/` folder is used, README remains the entry point and links into it.

---

## Loop Engineering

Tiers 1 and 2 above are the interactive path — a human driving a session
turn by turn. **Tier 3** is additive: recurring or unattended work (triage,
maintenance, monitoring) that an autonomous loop discovers, triages, and
either acts on or surfaces for a human, on its own cadence, consuming the
same plans, skills, and quality gates the interactive phases already
produce.

- **spec/design/06_loop_engineering.md** – The full model: the `/goal` /
  `/loop` / `/schedule` primitives, the four-rung loop ladder, output tiers
  (report-only / local change / external action), governance, and
  copy-pasteable prompt recipes.
- **spec/loop/CONVENTIONS.md** – How a loop's own state (charter, progress
  cursor, findings) lives on disk.
- **docs/worktrees.md** – Isolating parallel agents so they don't collide on
  the same files or branch.
- **docs/connectors.md** – The MCP connector inventory and access-tier
  governance for what an unattended loop may reach outside the repo.

This repo ships a real, runnable loop on itself:
**`spec/loop/repo-maintenance/`** — a report-only (tier A) loop that checks
this template's own conventions (symlinks, skill/agent indexes, cross-links,
plan hygiene, changelog staleness, loop hygiene). It needs no CI, no git
hosting, and no PR — start it from a Claude Code or Cursor session with
`/loop-triage` or `/loop 24h`.

---

## Quality and verification

Before any task or phase is considered done, the project enforces **quality gates** and **non-negotiable rules**. These include:

| Area | Expectation |
|------|--------------|
| **Testing** | Tests verify behaviour; new or changed behaviour has tests where the project has a test suite. |
| **Linting** | Code passes the project linter (and formatter); no “task done” with lint errors. |
| **Patterns & style** | Follow project patterns and code style (do’s and don’ts); see `CLAUDE.md`, `.cursor/rules`, and docs. |
| **Edge cases** | Plan/spec edge cases and error handling are addressed or explicitly deferred. |
| **Performance** | No known regressions; performance is non-negotiable when required by spec. |
| **Security** | Input handling, secrets, and auth follow project security rules. |
| **Verification** | Before “task done”: run tests, run lint, confirm acceptance criteria, update plan and changelog. |

Full details, do’s and don’ts, and the verification checklist: **[docs/quality-and-verification.md](docs/quality-and-verification.md)**.

---

## Notes

### Windows and symlinks

Several files in `.claude/agents/` and `.claude/commands/changelog.md` are symlinks pointing to their canonical counterparts in `.cursor/`. On macOS and Linux, git handles these transparently. On Windows, symlinks require either **Developer Mode** enabled or git configured with `core.symlinks=true` (run `git config core.symlinks true` before cloning, or clone with `git clone -c core.symlinks=true <url>`). Without this, the symlinked files will be checked out as plain text files containing the target path, and both Cursor and Claude Code will fail to read them correctly.

---

## References (inspiration and further reading)

Links used for inspiration and informational purpose:

- [How I use Claude Code](https://boristane.com/blog/how-i-use-claude-code/) – Process inspiration.
- [Software engineering with AI – beyond the basics](https://www.principalengineer.com/p/software-engineering-with-ai-beyond) – Deeper context on AI-assisted development.
- [Stop prompting, start managing](https://medium.com/wix-engineering/stop-prompting-start-managing-9eac9426930f) – Treating AI agents as team members needing structure: Iron Law, project memory, anti-rationalization, multi-agent review cycles, skill evolution.
- [Agent Skill collection by Addy Osmani](https://github.com/addyosmani/agent-skills)
- [Loop Engineering](https://addyo.substack.com/p/loop-engineering) – The architecture behind Tier 3: automations, worktrees, skills, connectors, sub-agents, external memory, and the risk model (comprehension debt, cognitive surrender, orchestration tax).
- [Practical Loop Engineering](https://addyo.substack.com/p/practical-loop-engineering) – The operating manual behind Tier 3: `/goal` and `/loop`, the four-rung loop ladder, determinism requirements, abort criteria, and delegation boundaries.
