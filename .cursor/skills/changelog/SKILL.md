---
name: changelog
description: Keeps a structured changelog of work done by agents (completed, pending, learnings). Use after significant work sessions, at task completion, or when the user asks to update the log. Supports Spec-Driven development and continuity across sessions.
---

# Changelog – Agent work tracking

## When to use

- **After significant sessions**: changes that touch multiple files or require multiple steps.
- **At task completion**: when a spec/task is done or paused.
- **On request**: when the user asks to "update the changelog" or "record what you did".
- **Before switching context**: before moving to another task or closing, so state is not lost.

You don't need an entry for every single change; group by **goal/task** or **session**.

---

## Where to write

- **File**: `CHANGELOG.md` in the project root (or path specified in project rules / README).
- **Format**: Markdown, one section per date (order: most recent first).

---

## Entry structure

Each entry must be **self-contained**: whoever resumes (human or agent) should understand status and next steps without reading the chat.

```markdown
## [YYYY-MM-DD] Short title (task/session)

**Context**: 1–2 sentences (spec, ticket, goal).

**Completed**
- What was done (files/feature/bugfix).
- Relevant decisions (e.g. library choice, pattern).

**Pending / Next steps**
- What remains to do or verify.
- (Optional) Blockers or dependencies.

**Learnings** (only if any)
- Non-trivial issues and how they were solved.
- Notes for future sessions (workarounds, known limits).
```

---

## Rules

1. **Language**: same as the project (English or as defined in the repo).
2. **References**: include task/spec/IDs when they exist (e.g. `[spec: auth]`, `#TASK-42`).
3. **Files touched**: mention paths or areas (e.g. `api/auth/`, `docs/`) when it helps recover context.
4. **No duplicates**: if a session continues the next day, update the existing entry or add a subsection with date/time; don't repeat everything.
5. **Concise**: clear bullets; avoid logging every single commit.

---

## Example

```markdown
# Changelog – Agent work

## [2025-03-01] JWT auth setup [spec: auth]

**Context**: Login and token implementation per "Auth flow" spec.

**Completed**
- `POST /auth/login` endpoint and JWT validation middleware.
- Secret and expiry config in env.
- Unit tests for login and middleware.

**Pending / Next steps**
- Refresh token and logout (next sprint).
- Document API in `docs/api.md`.

**Learnings**
- Used `python-jose` for JWT; in tests mock `datetime.utcnow` for deterministic tokens.
```

---

## Spec-Driven integration

- Align entries with **task/spec** (requirements, planning phases, implementation).
- In "Context" or bullets, cite the spec or reference document.
- If a spec task is closed, note it under **Completed** (e.g. "Task #xyz marked Done in Notion/Jira/Other...").

This keeps the changelog as the single source of truth for work status and for bringing agents and developers back up to speed without losing the thread.
