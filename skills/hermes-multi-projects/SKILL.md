---
name: hermes-multi-projects
description: Operate Hermes agents across isolated project contexts.
version: 0.1.0
author: Alan Mosko, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [projects, multi-agent, context, isolation]
    related_skills: []
---

# Hermes Multi-Projects

Use this skill when operating an agent with a selected project context. The plugin resolves the active project; this skill defines the working discipline. Do not use it to infer a project from conversation wording.

## Procedure

1. Run `/project` before work that may read or write project data. Completion: the project slug or `company` is explicit.
2. In a project context, read `PROJECT.md`, `CONTEXT.md`, and `AGENTS.md` before material work. Completion: objective, constraints, and locations are known.
3. Read or write only under the active project root. Completion: every artifact path is project-scoped.
4. Record decisions in `operations/decisions/` and shared state in project checkpoints. Completion: durable decisions have an auditable file.
5. Revalidate time-sensitive or external facts. Completion: no checkpoint or old artifact is treated as current external truth.

## Pitfalls

- Do not change a project selected by a routed channel; the route is authoritative.
- Do not transfer project facts into global agent memory without an explicit cross-project promotion decision.
- `company` context cannot access project-specific material.
