# Changelog – Agent work

## [2026-08-21] Google Photos → AWS S3 backup tool [spec: spec/feat/google-photos-s3-backup/plan.md]

**Context**: Full Tier 2 (research → plan → 4-round multi-agent review cycle → implementation) build of `gphotos2s3`, a freely-distributable, open-source Python CLI that backs up a Google Takeout export of Google Photos to the user's own AWS S3 bucket. Business goal: free up Google Account storage by leveraging low-cost S3 storage, without executing any real upload as part of this session — implementation and mocked tests only.

**Completed**
- **`spec/feat/google-photos-s3-backup/research.md`** (new): Google Takeout export format (multi-part zips, unstable JSON sidecar naming across export requests, filename truncation), S3 storage-class/multipart-upload mechanics, the idempotency/resume pattern, and the credential-UX decision — all grounded via web search, cited.
- **`spec/feat/google-photos-s3-backup/plan.md`** (new): full architecture, data model, module layout, testing plan, and acceptance criteria. **Went through 4 rounds of the multi-agent review cycle** (architect-reviewer / consistency-reviewer / risk-analyst) before implementation began, per `AGENTS.md`'s gate — not run retroactively this time:
  - Round 1: architect-reviewer and risk-analyst both **Needs revision** (1 Critical each — untracked metadata-object loss; an untested reconciliation code path — plus several High findings on concurrency, credential-file safety, corrupt-input handling). consistency-reviewer **Pass with advisories**.
  - Round 2 (risk-analyst re-review): found a **new Critical** — the round-1 fix still assigned S3 object ownership by runtime processing order, so a state-DB loss combined with concurrent workers could silently duplicate stored content. Root-caused with a redesign to **content-addressed S3 keys** (`content_key = f(sha256, ext)`, a pure function independent of any row or processing order) rather than patched.
  - Round 3 (risk-analyst re-review): found the content-addressed redesign itself introduced 2 new High findings — `pointer_key`/`metadata_key` had dropped the same zip-basename disambiguator row `id` uses (a real collision risk across independently re-requested Takeout exports), and the systemic-failure classifier's exact-error-type matching could let a mixed-subtype outage never halt.
  - Round 4 (risk-analyst re-review, final gate): **Pass with advisories.** Both round-3 Highs confirmed closed; 2 residual Low advisories (path-sanitizer reject-vs-collapse asymmetry; systemic-classifier allowlist-vs-denylist) folded in as a final hardening pass.
- **`src/gphotos2s3/`** (new package, 13 modules): `state.py` (SQLite, WAL mode, migration runner, no boto3 imports), `discovery.py` (zip walking, dual JSON-sidecar-naming pairing, truncated-name fallback, unsafe-path rejection), `hashing.py` (streaming spool+hash), `metadata.py` (sidecar parsing), `uploader.py` (content-addressed keys, HEAD idempotency, S3-native checksum, `verify_uploaded`), `aws_credentials.py` (read-merge-write `~/.aws/credentials`, `getpass`, shared client factory), `iam_policy.py` (two-tier least-privilege policy), `config.py`, `pipeline.py` (orchestration: atomic PID lock, per-sha256 dedup lock, `SystemicFailureTracker`, reconciliation, bounded incremental worker pool), `wizard.py`, `report.py`, `cli.py` (`init`/`run`/`status`/`verify`/`retry-failed`).
- **`tests/`** (13 files, 77 tests, `pytest` + `moto`, zero real AWS/Google access): covers dual sidecar naming, truncated-name fallback, corrupt-archive and corrupt-entry isolation, WAL concurrency, mid-transfer crash resume (both S3-succeeded-DB-not-committed and mid-multipart sub-cases), full state-DB-loss rebuild under `workers>=2` with an explicit distinct-content-object-count assertion, cross-export-session pointer-key collision, systemic-failure halting (denylist classification, mixed-subtype streaks, thread safety), atomic lock acquisition, credential wizard flow (unrelated-profile preservation, `getpass`, validate-before-persist, no-secret-leak), and `docs/iam-policy-example.json`↔`iam_policy.py` equality.
- **`pyproject.toml`, `LICENSE` (MIT), `.gitignore`**: `src/`-layout package, `ruff` + `mypy` config, `hatchling` build backend, console-script entry point.
- **`README.md`**: fully rewritten from the template's process-overview content to be product-facing (install, quick start, resumability model, cost notes, security, FAQ), with a "Development" section linking back to the plan/research for contributors.
- **`docs/iam-policy-example.json`** (new): generated from `iam_policy.py`, kept in sync by a dedicated test.

**Pending / Next steps**
- No real upload was executed against real AWS or a real Google Takeout export in this session, per explicit scope — a user's first real `gphotos2s3 init && gphotos2s3 run` is the next real-world validation step.
- Not yet published to PyPI (`pip install -e .` from source only).
- `spec/feat/google-photos-s3-backup/plan.md`'s outcome note added; §13 checklist fully checked.

**Learnings**
- **Local dev environment**: this machine's Homebrew Python 3.14 has a broken `platform.mac_ver()` (returns empty strings), which crashes `pip`/`ensurepip`'s bundled `truststore` SSL context setup on *any* `pip install`, even `--no-index` local ones — a pip regression triggered by this specific environment, not a sandbox permission issue (confirmed with the sandbox disabled too). Workaround: use `uv venv` + `uv pip install` instead of `python -m venv` + `pip install` — `uv` doesn't hit this path. Recorded in `PROJECT_MEMORY.md`.
- **Content-addressing beats locking for dedup correctness.** The round-1→round-2 sequence is the clearest example in this repo's history of the review cycle's actual value: a plausible-looking fix (a claim-lock around a runtime-assigned "canonical row") reduced a race's likelihood without closing it, because the underlying design still had a stateful, order-dependent concept for a later round to find a hole in. The real fix was removing that concept entirely (pure-function keys), not tightening the lock further.
- **A redesign must re-earn scrutiny for every key it introduces, not just the one a finding was about.** Round 3 only existed because the round-2 fix was checked against the *same* "is this really ownerless" test it had just been used to justify — applied to the *new* keys (`pointer_key`/`metadata_key`) the redesign itself introduced, not just `content_key`.
- **Discovered a real bug via the tests the plan required**, not code review: `discovery.py`'s sidecar-path joining double-prefixed the directory (`_find_sidecar` already returns a full entry name, not a bare basename) — caught immediately by `test_discovery.py`'s sidecar-pairing tests, which the plan's review cycle had specifically called for.

---

## [2026-08-18] Loop Engineering — Tier 3 (autonomous loops) [spec: spec/feat/loop-engineering/plan.md]

**Context**: Fully implement `spec/feat/loop-engineering/plan.md` — add a third, additive pipeline tier for recurring/unattended agent work (triage, maintenance, monitoring), built on Addy Osmani's "Loop Engineering" architecture and "Practical Loop Engineering" operating manual, adapted to this repo's Iron Law / skills-as-procedure / agents-as-roles conventions.

**Completed**
- **`spec/design/00_pipeline_tiers.md`**: added a "Tier 3: Autonomous Loop" section (pointing at the ladder in `06`, not restating it) and two rows to the tier-selection table.
- **`spec/design/06_loop_engineering.md`** (new): the full Tier 3 model — `/goal` / `/loop` / `/schedule` primitives, the four-rung loop ladder + promotion rule, output tiers A/B/C, the reference loop lifecycle, the mandatory `/goal` template, red-flag stall handling, the delegation boundary, verification depth, the attention budget (default 3 concurrent loops/reviewer), 9 governance rules, 10 copy-pasteable prompt/setup recipes, and an optional GitLab-CI-only appendix.
- **`spec/loop/CONVENTIONS.md`** + **`spec/loop/.gitkeep`** (new): the `loop.md`/`state.md`/`inbox.md`/`archive.md` per-loop folder convention, plus the `loop.md` charter template.
- **`spec/loop/repo-maintenance/`** (new, seeded, runnable): a real rung-3/tier-A loop charter (`loop.md`, authored per the `loop-charter` skill) with seven mechanically-checkable checks (symlink integrity, index drift, cross-link integrity, plan hygiene, skill-graduation candidates, changelog staleness, loop hygiene), each with its own threshold/ignore-list. **Dry-run executed manually** (no CI, no git hosting, no PR) — 5 checks passed clean (logged to `archive.md`), 2 real findings written to `inbox.md`: (1) `CHANGELOG.md` was 132 days stale — resolved by this same entry; (2) `AGENTS.md` has no explicit index row for `documentation-architect.md` / `security-auditor.md` — left open, needs a human decision on doc structure (see `spec/loop/repo-maintenance/inbox.md`).
- **`docs/worktrees.md`** (new): when/how to isolate loops or parallel agents (Claude Code `isolation: "worktree"` / `EnterWorktree`/`ExitWorktree`, or `git worktree` fallback), naming, cleanup, and the multi-worktree adversarial-judge pattern.
- **`docs/connectors.md`** (new): MCP connector inventory (Slack, GitLab, AWS CloudWatch, AWS Cost Explorer, Google Drive/Docs/Sheets, Grafana, Octocode) with access levels and permitted output tiers, plus a wiring guide — one MCP server entry per access level (`gitlab-ro` / `gitlab-rw`), minimum-credential examples, a tier→server config sketch, secret handling, rotation, and a pre-promotion boundary test.
- **New agents**: `explorer` (read-only discovery for loops) and `loop-verifier` (verifies loop output; must be a separate identity from the implementer) — `.cursor/agents/*.md` + `.claude/agents/*.md` symlinks.
- **New skills**: `loop-charter` (charter authoring, with the separate-model test on the stop condition), `loop-triage` (discovery/triage procedure run by `explorer`), `loop-verify` (verification procedure run by `loop-verifier`) — `.cursor/skills/*/SKILL.md` + `.claude/commands/*.md` symlinks.
- **`AGENTS.md`**: new "Loop agents" subsection distinguishing plan-review agents (check plan text) from loop agents (check unattended discovery/output).
- **`SKILLS.md`**: index rows for all three new skills.
- **`README.md`**: new "Loop Engineering" section; both source articles added under References.
- **`docs/quality-and-verification.md`**: new § 11 "Autonomous loop verification" + two anti-rationalization rows ("the loop already verified it", "it's just a report-only loop, no need for a charter").

**Update (same session)**: ran the multi-agent review cycle (architect-reviewer → consistency-reviewer → risk-analyst) retroactively against the finalized plan and the implemented state, as required by Phase G. **All three: Pass** (no Critical/High findings). Six advisory Medium/Low findings were fixed as fast-follows in this same pass — see `spec/feat/loop-engineering/amendments.md` for the full list (new `amendments.md`, `docs/connectors.md` actor-naming + missing cross-reference, `spec/loop/CONVENTIONS.md` concurrency note, `loop-triage` tier-boundary self-check, `loop-verifier.md` model-choice rationale, `06_loop_engineering.md` enforcement-layer note). `spec/feat/loop-engineering/plan.md`'s outcome note and §12 checklist updated accordingly.

**Pending / Next steps**
- The `AGENTS.md` agent-index-drift finding in `spec/loop/repo-maintenance/inbox.md` (#2) is a judgment call left for a human — resolve by either adding explicit file references to the "Sample agents" prose, or documenting that section as intentionally non-1:1.
- Consumer teams adopting this template still need to fill in `docs/connectors.md` with their own real credentials/tokens (the table is seeded with placeholders/patterns only).
- A team running loops unattended (no human present) should pair `explorer`'s charter with tool-level path restrictions and pin `loop-verifier` to a model distinct from the implementer's — both are documented as advisory, not yet enforced structurally (see `06_loop_engineering.md` § Governance closing note).

**Learnings**
- Running the seeded `repo-maintenance` loop as a real dry-run (not a hypothetical) surfaced a genuine pre-existing gap (`AGENTS.md` index drift) that predates this session — confirms the loop's checks are non-hallucinated and worth having.
- The review cycle, even run retroactively, still earned its keep: two of its six findings (the `docs/connectors.md` self-reference gap, and the missing `amendments.md`) were real drift this session would not have caught on its own.

---

## [2026-04-08] Claude Code dual-IDE integration

**Context**: Extend the template to support Claude Code (CLI/extension) alongside Cursor, so agents, skills, and documentation work correctly in both tools.

**Completed**
- **AGENTS.md**: updated agent-location reference to include both `.cursor/agents/` (Cursor) and `.claude/agents/` (Claude Code); expanded the review-cycle table with a Claude Code column pointing to `.claude/agents/` counterparts.
- **SKILLS.md**: rewrote "Where they live" as a two-row table (Cursor vs Claude Code); updated skill index with both paths; updated "graduation" instructions to create files in both locations; removed Cursor-specific language from invocation examples.
- **README.md**: updated tagline to mention Claude Code alongside Cursor; added `CLAUDE.md` to the patterns & style quality-gate row; added a new "Notes → Windows and symlinks" section explaining that `.claude/agents/` and `.claude/commands/changelog.md` are symlinks and how to handle them on Windows.
- **Agent files** (`.cursor/agents/`): minor copy fixes — removed "cursor" from "cursor rules" references, removed stray parentheses around "English", normalised whitespace in security-auditor and documentation-architect.
- **`.cursor/skills/changelog/SKILL.md`**: replaced `.cursor/rules` reference with "project rules" for tool-agnostic language.

**Pending / Next steps**
- Verify symlinks in `.claude/` resolve correctly after clone on macOS/Linux CI.
- Consider adding a GitHub Actions check to confirm symlink integrity.

---

## [2025-03-01] Security Auditor agent – full-stack and integration coverage

**Context**: User asked to make the Security Auditor agent complete for web development (frontend, backend, system integration) and to add any missing aspects.

**Completed**
- Rewrote `.cursor/agents/security-auditor.md`: (1) role and scope by layer (frontend, backend, system integration); (2) checklists per layer—frontend (XSS, CSP, client storage, tokens, third-party/SRI, open redirects, deps), backend (injection, auth/session, authorization, validation, secrets, crypto, logging, SSRF, deserialization, rate limiting, deps), integration (API auth, TLS/certs, webhooks, service-to-service, CI/CD, data in transit/rest); (3) cross-cutting (CSRF, sensitive data, headers); (4) when to act; (5) reporting format (scope, severity Critical/High/Medium/Low, mitigations, positive findings); (6) rules (concrete, context-aware, prioritized, actionable).

**Pending / Next steps**
- None for this task.

---

## [2025-03-01] Quality gates and verification (docs + README + rule)

**Context**: User asked to give structured visibility to testing, linting, patterns & code style, edge cases, performance, security, verification steps, and other non-negotiable rules.

**Completed**
- Created **docs/quality-and-verification.md**: sections for Testing, Linting, Preferred patterns & code style, Edge cases, Performance, Security, Verification steps before “task done”, and Other non-negotiable rules (scope creep, artifacts as source of truth, traceability, a11y). Each with do’s/don’ts and a clear rule. Added summary checklist table.
- **README.md**: new “Quality and verification” section with table of areas and link to docs/quality-and-verification.md.
- **.cursor/rules/quality-verification.mdc**: always-applied rule stating run tests + lint before “task done”, confirm acceptance criteria, update artifacts; points to full doc.
- **04_implementation_phase.md**: added “Quality gates” bullet referencing docs/quality-and-verification.md.

**Pending / Next steps**
- None for this task.

---

## [2025-03-01] Documentation Agent: docs folder and README as entry point

**Context**: User asked to focus the Documentation Agent on a dedicated `docs/` folder, with README.md as the entry point for project meaning, scope, and documentation references.

**Completed**
- Updated `.cursor/agents/DOCUMENTATION.md`: (1) added “Documentation layout” stating all doc content in `docs/`, README as entry point only; (2) “What to maintain” table now has a Location column (root vs `docs/`); (3) README limited to meaning, scope, and links to `docs/`; (4) rules updated so README links to `docs/` and cross-links stay within `docs/`.

**Pending / Next steps**
- None for this task.

---

## [2025-03-01] Documentation Agent restructured

**Context**: User asked to structure and format the Documentation Agent so it is clearly responsible for keeping documentation updated for requirements and architectural decisions.

**Completed**
- Rewrote `.cursor/agents/DOCUMENTATION.md` with: (1) role and scope (requirements + architectural decisions); (2) table of artifacts to maintain (README, architecture, principles/rules, ADRs, requirements log); (3) when to act; (4) rules (remove outdated content, self-contained entries, consistency, audit trail); (5) benefits section. Preserved original intent (single source of truth, audit trail, reconciliation, pruning stale docs).

**Pending / Next steps**
- None for this task.

---

## [2025-03-01] AGENTS.md structured

**Context**: User asked to structure `AGENTS.md` in the project root so it explains how agents are meant and used, while keeping the existing sample agents.

**Completed**
- Rewrote `AGENTS.md` with: (1) intro on agents as domain-experts and executors of ancillary tasks; (2) “How they’re used” (invoked by user, role-based, complementary to skills); (3) note that agent guidance lives in `.cursor/agents/`; (4) “Sample agents” section keeping all five (Documentation, Business Domain Expert, Code Review & Rule Expert, Requirements Reconciliation, Security).
- Changelog updated with this entry.

**Pending / Next steps**
- None for this task.

---

## [2025-03-01] SKILLS.md enrichment

**Context**: User asked to enrich `SKILLS.md` so it explains how skills are used in the project and where they live.

**Completed**
- Expanded `SKILLS.md` with: (1) kept existing philosophy (skills as reusable prompts for repetitive/frequent tasks); (2) “How they’re used” (by agents and by user request); (3) “Where they live” (`.cursor/skills`, one folder per skill with `SKILL.md`).
- Changelog created and entry added per changelog skill.

**Pending / Next steps**
- None for this task.
