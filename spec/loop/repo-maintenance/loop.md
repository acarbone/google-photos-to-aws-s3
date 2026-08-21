# Loop: repo-maintenance

- **Purpose**: Catch drift between this repo's own documented conventions
  (symlinks, skill/agent indexes, cross-links, plan hygiene, changelog
  currency, loop hygiene) and what is actually on disk, before a human
  notices it the hard way.
- **Rung / primitive**: 3 (`/loop 24h`, weekly cadence in practice)
- **Output tier**: A (report-only) — reads and analyses only; writes solely to
  `spec/loop/repo-maintenance/{inbox,archive,state}.md`. No CI, no git
  hosting, no PR required.
- **Cadence**: weekly (or on-demand via a manual dry-run)
- **Scope — reads**:
  - `.claude/agents/*`, `.claude/commands/*` (symlinks) and their
    `.cursor/agents/*`, `.cursor/skills/*/SKILL.md` targets
  - `SKILLS.md`, `AGENTS.md` (index tables)
  - `README.md`, `AGENTS.md`, `SKILLS.md`, `CLAUDE.md`, `docs/`,
    `spec/design/` (relative markdown links)
  - `spec/feat/*/plan.md` (checklists and outcome notes)
  - `PROJECT_MEMORY.md` § "Recurring patterns"
  - `CHANGELOG.md` and recent git log
  - `spec/loop/*/` (worktree hygiene, stale `inbox.md` entries)
- **Scope — never touches**: source code, any file outside the paths above,
  any connector (this loop uses none), `spec/feat/*/plan.md` bodies (read
  only — never edits a plan).
- **Stop / done condition**: every one of the seven checks below has run and
  every finding it produced is written to `inbox.md` (actionable) or
  `archive.md` (not actionable, dated, with a reason). Verifiable by a
  separate model reading `state.md` (all seven checks show a run timestamp)
  against `inbox.md` + `archive.md`.
- **Abort criteria**: turn cap 15 per run. Abort if 2 consecutive turns
  produce no new findings and no state change. Halt immediately on a red
  flag (same scan command repeating with an identical result).
- **Agents & models**: explorer = `explorer` agent, `model: inherit` (fast,
  read-only pass is cheap by construction — no code generation). No
  implementer or verifier — tier A never writes code, so neither role is
  invoked.
- **Fan-out**: 1 (single explorer pass; no parallel worktrees — this loop
  never branches).
- **Human audit cadence**: every Friday, the owner reads the week's
  `inbox.md` in full (it is expected to be short) plus two random
  `archive.md` entries, to confirm non-actionable calls were reasonable.
- **Owner**: the developer who runs `/loop-charter` to adopt this template
  into their own repo (placeholder until a team names a person).

---

## The seven checks

Each check declares its own threshold/ignore-list so a noisy check can be
tuned without dropping it — a noisy check becoming a charter-edit finding is
the loop working as intended, not a bug in the loop.

1. **Symlink integrity** — every `.claude/agents/*` and `.claude/commands/*`
   symlink resolves to an existing `.cursor/` target. *Threshold*: any
   broken symlink is actionable immediately (zero tolerance — a broken
   symlink silently disables a skill or agent).
2. **Index drift** — every skill folder in `.cursor/skills/` has a row in
   `SKILLS.md`, and vice-versa; every agent file in `.cursor/agents/` has a
   row in `AGENTS.md`. *Threshold*: any drift is actionable immediately.
3. **Cross-link integrity** — every relative markdown link in `README.md`,
   `AGENTS.md`, `SKILLS.md`, `CLAUDE.md`, `docs/`, and `spec/design/` points
   at a file that exists. *Ignore-list*: external URLs (`http(s)://`),
   in-page anchors (`#section`), and mailto/tel links are skipped — this
   check only follows repo-relative paths.
4. **Plan hygiene** — `spec/feat/*/plan.md` with unchecked checklist items
   and no git activity touching that folder, or a plan whose checklist is
   fully checked but is missing the outcome note required by
   `spec/feat/CONVENTIONS.md`. *Threshold*: flag a stalled plan only past 14
   days of inactivity, to avoid flagging plans mid-implementation.
5. **Skill-graduation candidates** — entries under `PROJECT_MEMORY.md`
   "Recurring patterns" seen 3+ times, per the graduation rule in
   `SKILLS.md`. *Threshold*: only entries explicitly noting 3+ occurrences;
   this check does not infer a count from prose.
6. **Changelog staleness** — commits landed since the last `CHANGELOG.md`
   entry. *Threshold*: only fires past 10 commits or 14 days since the last
   entry, whichever comes first, to avoid flagging normal day-to-day gaps.
7. **Loop hygiene** — orphaned worktrees (a `git worktree list` entry with no
   matching active loop/feature slug); `inbox.md` findings older than 30
   days with no action. *Threshold*: 30-day staleness on `inbox.md` entries;
   any orphaned worktree is actionable immediately (it represents a dead or
   crashed loop run).
