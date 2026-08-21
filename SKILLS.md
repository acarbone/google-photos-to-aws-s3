# Skills in this project

**Skills** are reusable prompts for repetitive or frequently used tasks. If you think of them that way, you can quickly identify what skills you need: anything you do often and want done consistently.

## How they’re used

- **By agents**: Agents can invoke skills when a task matches a skill’s description (e.g. “update the changelog”, “create a rule”). Skills give agents a fixed procedure so the same kind of work is done the same way every time.
- **By you**: You can ask an agent to “use the changelog skill” or invoke a slash command (e.g. `/changelog`) so the agent follows the documented steps instead of improvising.

Skills are best for workflows that should be repeatable and predictable—documentation updates, changelog entries, rule creation, code-review checks, and similar recurring operations.

## Where they live

Skills are stored in two locations depending on the AI tool:

| Tool | Location | Format |
|------|----------|--------|
| **Cursor** | `.cursor/skills/<skill-name>/SKILL.md` | Folder per skill with a `SKILL.md` file |
| **Claude Code** | `.claude/commands/<skill-name>.md` | Single markdown file, invoked as `/skill-name` |

Both locations contain the same procedure content; the Iron Law applies equally — check for a matching skill before acting.

---

## Skill lifecycle

Skills are not static. They must evolve based on observed failures, and recurring problems should graduate into new dedicated skills.

### Evolution

A skill should be updated when:
- A verification failure reveals that the skill’s procedure did not prevent a class of mistake.
- A skill is applied to a real task and the output is wrong or incomplete — the gap is the skill’s problem to fix.
- The project’s conventions change in a way that affects how the skill’s procedure should run.

When updating a skill, record what changed and why in a brief comment at the top of the `SKILL.md`, or in the relevant `CHANGELOG.md` entry.

### Graduation

When the same kind of work appears repeatedly across sessions without a skill to handle it, it is a candidate for a new skill. The signal:

- The same procedure is improvised more than twice.
- A recurring pattern is logged in `PROJECT_MEMORY.md` under “Recurring patterns”.
- A verification failure keeps happening in the same area.

To graduate a pattern into a skill: create the skill file in both `.cursor/skills/<skill-name>/SKILL.md` and `.claude/commands/<skill-name>.md` following the existing format, and add it to the index below.

### Retirement

A skill should be removed or merged when:
- The workflow it encodes no longer exists in the project.
- Two skills overlap significantly — merge them into one.
- The skill is never invoked and the pattern it addresses has not recurred.

---

## Skill index

| Skill | When to use | Cursor | Claude Code |
|---|---|---|---|
| **changelog** | After significant sessions, at task completion, before context switch | [.cursor/skills/changelog/SKILL.md](.cursor/skills/changelog/SKILL.md) | [.claude/commands/changelog.md](.claude/commands/changelog.md) |
| **skill-evolution** | When updating an existing skill or graduating a pattern into a new one | [.cursor/skills/skill-evolution/SKILL.md](.cursor/skills/skill-evolution/SKILL.md) | [.claude/commands/skill-evolution.md](.claude/commands/skill-evolution.md) |
| **loop-charter** | Before a loop's first run, and whenever its scope, cadence, or output tier changes | [.cursor/skills/loop-charter/SKILL.md](.cursor/skills/loop-charter/SKILL.md) | [.claude/commands/loop-charter.md](.claude/commands/loop-charter.md) |
| **loop-triage** | At the start of every autonomous loop run (invoked by the `explorer` agent) | [.cursor/skills/loop-triage/SKILL.md](.cursor/skills/loop-triage/SKILL.md) | [.claude/commands/loop-triage.md](.claude/commands/loop-triage.md) |
| **loop-verify** | After an implementer session completes work from a loop finding, before it's called done | [.cursor/skills/loop-verify/SKILL.md](.cursor/skills/loop-verify/SKILL.md) | [.claude/commands/loop-verify.md](.claude/commands/loop-verify.md) |
