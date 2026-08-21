# Phase 4: Implementation

## Objective
To execute the validated plan mechanically. At this stage, all architectural decisions have been made. The implementation should be straightforward and "boring".

## Agent Instructions
The agent must write the code following the exact steps in the `plan.md` checklist, updating the document as it progresses, and maintaining high code quality without pausing for mid-flow confirmation.
The `plan.md` todo-list must always be updated with the status of each task.
The changelog must be kept updated with the related skill.

## Key Tricks & Best Practices
- **The Master Prompt:** Use a single, comprehensive prompt that enforces strict rules: complete all tasks, update the checklist, don't stop, don't add fluff, maintain strict typing, and run typechecks.
- **Let it Run:** Because you've spent time on the Annotation Cycle, you can confidently let the AI execute the whole plan autonomously.
- **Quality gates:** Before considering any task done, run tests and lint, and update the plan/changelog. See **docs/quality-and-verification.md** for the full checklist (testing, linting, patterns, edge cases, performance, security, verification steps).
- **Post-deployment verification:** If the change is deployed, extend verification into production: check error rates in monitoring dashboards (e.g. via Grafana MCP), pull traces, and confirm no regressions. Do not assume test success equals production correctness. For changes to shared code, use cross-repo code search (e.g. via Octocode MCP) to verify consistency across repositories. See **docs/quality-and-verification.md § 8**.

## Prompt Examples
- *"implement it all. when you're done with a task or phase, mark it as completed in the plan document. do not stop until all tasks and phases are completed. do not add unnecessary comments or jsdocs, do not use any or unknown types. continuously run typecheck to make sure you're not introducing new issues."*
