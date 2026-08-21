---
name: skill-evolution
description: Procedure for updating an existing skill based on observed failures, or graduating a recurring pattern into a new dedicated skill. Use when a skill produced wrong output, a gap is identified, or a pattern has recurred enough times to warrant its own skill.
---

# Skill Evolution – Update or Graduate

## When to use

- **Update an existing skill**: A skill was applied and the result was wrong, incomplete, or caused a verification failure. The gap is the skill's problem to fix.
- **Graduate a new skill**: The same kind of work has been improvised across multiple sessions without a skill to standardize it, or `PROJECT_MEMORY.md` lists it under "Recurring patterns".
- **Retire a skill**: A workflow is obsolete, or two skills overlap and should be merged.

---

## Updating an existing skill

1. **Identify the gap**: What specifically went wrong? Which step in the skill procedure was missing, ambiguous, or wrong?
2. **Edit the skill file**: Update the procedure to close the gap. Be precise — vague instructions produce vague output.
3. **Record the change**: Add a brief note to the relevant `CHANGELOG.md` entry (or create one) describing what changed and why.
4. **Verify**: Apply the updated skill to a real or representative task and confirm the gap is closed.

---

## Graduating a new skill

1. **Confirm the pattern**: The procedure has been improvised at least twice, OR it appears in `PROJECT_MEMORY.md` under "Recurring patterns".
2. **Create the skill file**:
   - **Cursor**: `mkdir .cursor/skills/<skill-name>/` and write `SKILL.md`
   - **Claude Code**: Create `.claude/commands/<skill-name>.md`
3. **Write the skill** following this structure:
   ```markdown
   ---
   name: <skill-name>
   description: <one-line description — used by the Iron Law check>
   ---

   # <Skill name>

   ## When to use
   <Clear trigger conditions>

   ## Procedure
   <Numbered, concrete steps>

   ## Output
   <What a correct application of this skill produces>

   ## Rules
   <Non-negotiable constraints on how the skill is applied>
   ```
4. **Register the skill**: Add it to the skill index in `SKILLS.md` (both Cursor and Claude Code paths if applicable).
5. **Remove from PROJECT_MEMORY.md**: If the pattern was listed under "Recurring patterns", remove or update that entry.
6. **Record in changelog**: Note the new skill in `CHANGELOG.md`.

---

## Retiring a skill

1. **Confirm it is obsolete or redundant**: The workflow no longer exists, or the skill overlaps with another.
2. **If merging**: Incorporate any unique steps into the surviving skill.
3. **Delete the skill**:
   - **Cursor**: Remove `.cursor/skills/<skill-name>/`
   - **Claude Code**: Remove `.claude/commands/<skill-name>.md`
4. **Remove from skill index**: Update `SKILLS.md`.
5. **Record in changelog**: Note the retirement and the reason.

---

## Rules

1. **Never update a skill without a real failure or gap as the trigger.** Speculative improvements add noise.
2. **Each skill must have a unique, precise description.** The Iron Law check relies on descriptions to match skills to tasks — duplicates and vague descriptions break the check.
3. **Skills evolve; they do not accumulate.** An updated skill replaces its predecessor — do not keep both.
