# Phase 2: Planning

## Objective
To create a structured, complete specification (`plan.md`) that outlines exactly how the feature will be built, ensuring the architecture and approach are solid before a single line of production code is written.

## Agent Instructions
The agent must generate a detailed implementation plan in a separate markdown file. The plan must include an explanation of the approach, concrete code snippets, exact file paths to be modified, considerations, and trade-offs.

## Key Tricks & Best Practices
- **Use Custom `.md` Files:** Do not use the AI's built-in "plan mode" (if any). A real markdown file gives you full control to edit and persist it as a project artifact.
- **Provide Reference Code:** When building a standard feature, paste a good implementation from an open-source repo or an existing part of the codebase. The AI works dramatically better with a concrete reference.
- **Search Prior Plans First:** Before writing a new plan, check `spec/feat/` for prior work on the same area. Rejected approaches, prior trade-offs, and past decisions are documented there — no need to rediscover them.
- **Plans are preserved:** After implementation, move `plan.md` into `spec/feat/<feature-slug>/` as a permanent decision log. See `spec/feat/CONVENTIONS.md` for the full convention.

## Prompt Examples
- *"I want to build a new feature <name and description> that extends the system to perform <business outcome>. write a detailed plan.md document outlining how to implement this. include code snippets"*
- *"the list endpoint should support cursor-based pagination instead of offset. write a detailed plan.md for how to achieve this. read source files before suggesting changes, base the plan on the actual codebase"*
- **Reference Trick:** *"this is how they do sortable IDs [paste reference code], write a plan.md explaining how we can adopt a similar approach."*
- **Prior art search:** *"before planning, check spec/feat/ for any prior work on authentication or session handling, and factor in any documented trade-offs or rejected approaches."*
