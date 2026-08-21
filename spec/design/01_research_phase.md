# Phase 1: Research

## Objective
To ensure the AI agent thoroughly understands the relevant parts of the codebase before any planning or coding begins. This prevents the AI from building features that work in isolation but break the surrounding system.

## Agent Instructions
The agent must perform a deep-read directive of the codebase and document its findings in a persistent markdown file (e.g., `research.md`). The AI must **never** just provide a verbal summary in the chat.

## Key Tricks & Best Practices
- **Anti-Skimming Keywords:** AI tends to skim files at the signature level. You must use specific trigger words to force a deep analysis: **"deeply"**, **"in great details"**, **"intricacies"**, **"go through everything"**.
- **The Artifact:** The written `research.md` is your review surface. If the AI's understanding is flawed here, everything that follows will be flawed ("Garbage in, garbage out").

## Prompt Examples
- *"read this folder in depth, understand how it works deeply, what it does and all its specificities. when that's done, write a detailed report of your learnings and findings in research.md"*
- *"study the notification system in great details, understand the intricacies of it and write a detailed research.md document with everything there is to know about how notifications work"*
- *"go through the task scheduling flow, understand it deeply and look for potential bugs... keep researching the flow until you find all the bugs... write a detailed report of your findings in research.md"*
