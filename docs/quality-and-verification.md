# Quality gates and non-negotiable rules

This document defines the **quality gates** and **non-negotiable rules** for work done under the Spec-Driven process. Agents and developers must respect these before considering any task or phase complete.

---

## 1. Testing

- **Do**: Write tests that verify behaviour and requirements; cover happy path and critical failure modes; keep tests maintainable and readable.
- **Don’t**: Write tests that only pass; skip tests for new or changed behaviour; rely on tests that are flaky or environment-dependent without documenting it.
- **Rule**: New or changed behaviour must have corresponding tests where the project has a test suite. Tests are the primary way to verify that the implementation matches the spec.

---

## 2. Linting

- **Do**: Run the project linter (and formatter, if configured) before considering work done; fix all reported issues or document why a rule is disabled in that spot.
- **Don’t**: Leave lint errors “for later”; disable rules globally without team/repo agreement; ignore lint in CI.
- **Rule**: Code must pass the project’s lint (and format) checks. No “task done” with outstanding lint failures.

---

## 3. Preferred patterns and code style (do’s and don’ts)

- **Do**: Follow the patterns and style already used in the codebase; respect `.cursor/rules`, project style guides, and conventions; keep naming and structure consistent.
- **Don’t**: Introduce a new pattern or style without alignment; mix styles within the same module; add unnecessary comments, JSDoc, or types (e.g. `any` / `unknown`) where the project standard is to avoid them.
- **Rule**: Implementation must match the project’s preferred patterns and code style. When in doubt, mimic existing code and refer to project rules (e.g. in `docs/` or `.cursor/rules`).

---

## 4. Edge cases

- **Do**: Identify and handle edge cases (empty input, null/undefined, limits, errors); document assumptions and known limitations; align with the spec and acceptance criteria.
- **Don’t**: Implement only the happy path; ignore error handling or boundary conditions mentioned in the plan or requirements.
- **Rule**: Edge cases called out in the plan or requirements must be addressed or explicitly deferred with a reason. Unexplored edge cases that could break the feature must be raised, not silently ignored.

---

## 5. Performance

- **Do**: Avoid obvious performance regressions (e.g. N+1 queries, unnecessary allocations, blocking the main thread); consider scale and resource use when the spec or domain implies it.
- **Don’t**: Optimise prematurely without evidence; ignore performance when the spec or acceptance criteria mention it.
- **Rule**: Performance is a non-negotiable when it is part of the requirements or when a change clearly degrades existing behaviour. Otherwise, follow “make it right, then make it fast” and document any known limits.

---

## 6. Security

- **Do**: Sanitise/validate input where it affects safety; avoid hardcoded secrets and insecure defaults; follow project and ecosystem security practices.
- **Don’t**: Introduce known vulnerabilities (e.g. injection, unsafe deserialisation); leave credentials or sensitive data in code or logs.
- **Rule**: Security-sensitive areas (auth, permissions, input handling, secrets) must follow the project’s security rules. When in doubt, treat security as a constraint that cannot be relaxed to “ship faster”.

---

## 7. Verification steps before “task done”

Before marking any task or phase as complete, the following must be done:

1. **Run the test suite** – All tests pass. Fix or skip (with a documented reason) any failing tests before saying the task is done.
2. **Run the linter (and formatter)** – No lint/format errors. Fix or document exceptions.
3. **Confirm acceptance criteria** – The implementation matches the plan/spec for that task (behaviour, edge cases, non-functionals where specified).
4. **Update artifacts** – Plan/checklist and changelog (or other required docs) are updated to reflect completion.

**Rule**: “Task done” means: tests green, lint clean, acceptance criteria met, and artifacts updated. Do not report completion without having run tests and lint.

---

## 8. Production observability and code intelligence (post-deployment verification)

Local tests passing and lint being clean are necessary but not sufficient. For changes deployed to a real environment, verification must extend into production.

### Production observability

After deployment, agents and developers must check the real environment before declaring the task complete:

- **Error rates**: Confirm no new error spikes in monitoring dashboards (e.g. Grafana).
- **Traces**: Pull post-deployment traces to verify the code path executes as expected under real traffic.
- **Logs**: Check for unexpected warnings or failures introduced by the change.

Do not assume that test success equals production correctness. Production state is the only ground truth.

**Useful tools**: [Grafana MCP](https://github.com/grafana/mcp-grafana) provides agents with direct access to Grafana dashboards, traces, and error rate data via the Model Context Protocol — enabling agents to query production state without leaving the development workflow.

### Code intelligence (cross-repository search)

Before planning or implementing changes that touch shared infrastructure, libraries, or patterns used across multiple repositories, agents must search beyond the current repository:

- Verify the change does not contradict how the same pattern is implemented elsewhere.
- Identify other repositories that consume the interface being changed and may be affected.
- Use cross-repo search to find reference implementations when the local codebase lacks a clear precedent.

**Useful tools**: [Octocode MCP](https://github.com/nicholasgasior/octocode) provides agents with semantic cross-repository code search via the Model Context Protocol. [Superpowers](https://github.com/superpowers/superpowers) is an open-source framework that organizes skills and MCP integrations (including Octocode) into a composable agent toolchain.

### When this tier applies

This extended verification tier applies when:
- The change is deployed to a staging or production environment.
- The change touches a shared interface, library, or pattern used across multiple services or repositories.
- The plan explicitly calls out production verification as an acceptance criterion.

For local-only changes (e.g. refactors, internal utilities), the standard verification checklist (§ 7) is sufficient.

---

## 9. Anti-rationalization rules

Agents optimize for the shortest path to completion. The shortest path typically skips verification steps. The rules below map common agent excuses to the required behavior. They are **not negotiable. Not optional.**

| Agent excuse | Required behavior |
|---|---|
| "The tests already cover this" | Run the test suite. Do not assume coverage — verify it. |
| "This is a minor change" | Minor changes still require lint, tests, and artifact updates. Scope does not override process. |
| "I'm confident it works" | Confidence is not verification. Run tests and lint before reporting completion. |
| "The plan is clear enough, I'll figure out the details during implementation" | Ambiguities must be resolved in the annotation cycle, not during coding. Raise them before implementing. |
| "I'll update the changelog / plan later" | Artifacts are updated as part of the task, not after. "Later" is a commitment that does not get kept. |
| "The linter has some warnings but nothing critical" | Warnings must be fixed or explicitly documented with a reason. "Not critical" is not a valid exception. |
| "I reverted and re-implemented, so the previous state doesn't matter" | Update `PROJECT_MEMORY.md` with what went wrong. The failure is institutional knowledge. |
| "The loop already verified it" | A loop's self-report is not verification. `loop-verifier` must be a session/identity distinct from the implementer — see § 11. |
| "It's just a report-only loop, no need for a charter" | No charter, no loop — governance rule 2 in `spec/design/06_loop_engineering.md` applies at every output tier, including tier A. |

---

## 10. Other non-negotiable rules

- **No scope creep**: Implement what the plan says. New ideas or out-of-scope changes go into the plan (or backlog), not into the current implementation unless explicitly agreed.
- **Artifacts as source of truth**: The plan (e.g. `plan.md`) is the reference for what to build. Code that contradicts the plan without an updated plan is a defect.
- **Traceability**: Requirements and decisions that affect implementation should be traceable (e.g. from spec to plan to code to tests). Don’t remove or bypass this without a documented reason.
- **Accessibility and inclusivity**: When the project or spec defines a11y/inclusivity rules, they are non-negotiable in the same way as security or correctness.

---

## 11. Autonomous loop verification

Tier 3 work (`spec/design/06_loop_engineering.md`) does not get a lighter
verification bar because no human is present when it runs — it gets the same
bar, enforced by a different identity.

- **Verifier ≠ implementer.** The identity that writes a loop-produced
  change never approves it. `loop-verifier` (`.cursor/agents/loop-verifier.md`
  / `.claude/agents/loop-verifier.md`) runs as a separate session and gates
  the change before it is called done and before any connector acts on it.
- **Runtime-verification depth.** Green tests are the floor, not the bar.
  Where the project has a runnable UI, the `loop-verify` skill mimics human
  review: start the dev server, open the changed page, interact, capture
  before/after, read the console for new errors, run a performance trace
  where relevant. A failure at any step means fix and restart from the top —
  never hand back partial work.
- **Output-tier bounds.** A loop never exceeds its declared output tier:
  tier A never writes code, tier B never pushes, tier C never merges to a
  protected branch. `loop-verifier` confirms this on every pass (see the
  output tiers table in `spec/design/06_loop_engineering.md`).
- **Connector access is tiered, not just documented.** The read/write access
  level per connector, and the wiring that scopes MCP credentials — not just
  prompt instructions — to a loop's declared output tier.
- **Full checklist and governance**: see
  `spec/design/06_loop_engineering.md § Governance` for the complete,
  numbered rule set (charter requirement, traceability, stall handling,
  attention budget, and more). This section is a pointer, not a duplicate —
  the rules live in one place.

---

## Summary checklist (before “task done”)

| Check | Required |
|-------|----------|
| Tests run and pass | Yes |
| Lint (and format) run and pass | Yes |
| Acceptance criteria from plan/spec met | Yes |
| Edge cases and error handling as per spec | Yes |
| No known security or performance regressions introduced | Yes |
| Plan/checklist and changelog updated | Yes |
| Code follows project patterns and style | Yes |

This checklist can be referenced in prompts, agent instructions, and phase docs (e.g. Phase 4: Implementation, Phase 5: Feedback).

If any item is skipped, check the anti-rationalization table (§ 8) before accepting the excuse.
