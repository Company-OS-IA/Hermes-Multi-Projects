---
name: project-context
description: Work safely within the project context selected by Hermes Multi-Projects.
version: 1.0.0
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [projects, context, isolation]
    related_skills: []
---

# Project Context

Use this skill when work must stay inside the project selected by the plugin. Never infer or switch projects from conversational wording.

## Procedure

1. Run `/project` before reading or writing project data. Completion: the active project slug or `company` scope is explicit.
2. In a project context, read `PROJECT.md` and `CONTEXT.md` before material work. Completion: the objective, constraints, and canonical locations are known.
3. Read and write only under the active project root. Completion: every artifact path is project-scoped.
4. Record durable decisions under `operations/decisions/` and shared state under project checkpoints. Completion: decisions and state remain auditable.
5. Revalidate time-sensitive or external facts. Completion: cached context is not treated as current external truth.

## Pitfalls

- A routed channel's project cannot be changed manually.
- Do not transfer project facts into global memory without an explicit promotion decision.
- `company` scope does not authorize access to project-specific material.
