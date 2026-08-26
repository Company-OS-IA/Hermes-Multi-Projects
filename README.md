# Hermes Multi-Projects

A standalone Hermes plugin for routing sessions into isolated project contexts without modifying Hermes core.

## Features

- maps a gateway origin to a Hermes profile and project;
- injects deterministic project context into routed messages;
- supports explicit project selection in CLI and other non-routed surfaces;
- keeps unrouted channels in the restricted `company` scope;
- provisions a consistent project directory structure;
- exposes `project_context` for checking the active scope;
- bundles the read-only `hermes-multi-projects:project-context` skill.

Project isolation is enforced by profile allowlists and canonical project roots. It is a context boundary, not an operating-system sandbox.

## Requirements

- Hermes Agent with native plugin support;
- Python 3.11+;
- PyYAML 6.x;
- a writable workspace, such as `~/.hermes`.

## Install

From a public Git repository:

```bash
hermes plugins install YOUR_GITHUB_ORG/hermes-multi-projects --enable
```

For a private repository, use an authenticated Git URL:

```bash
hermes plugins install git@github.com:YOUR_GITHUB_ORG/hermes-multi-projects.git --enable
```

Then validate and restart Hermes:

```bash
hermes plugins doctor hermes-multi-projects --ci
hermes plugins list
```

Update an installed copy with:

```bash
hermes plugins update hermes-multi-projects
```

## Configure

Plugin settings belong under the native `settings` namespace:

```yaml
plugins:
  enabled:
    - hermes-multi-projects
  entries:
    hermes-multi-projects:
      settings:
        workspace_root: ~/.hermes
        manifest: ~/.hermes/projects.yaml
        admin_profiles: [default]
```

| Setting | Purpose | Default |
|---|---|---|
| `workspace_root` | Root containing `projects/` and the default manifest | `$HERMES_HOME` |
| `manifest` | Optional projects manifest path | `<workspace_root>/projects.yaml` |
| `admin_profiles` | Profiles allowed to manage projects and routes | `[default]` |

Restart the gateway after enabling, updating, or changing plugin settings.

## Quick start

Initialize the manifest from an authorized profile:

```text
/project init
```

Create a project:

```text
/project create project-alpha | Project Alpha
```

This creates:

```text
projects/project-alpha/
├── PROJECT.md
├── CONTEXT.md
├── knowledge/
├── operations/
│   ├── decisions/
│   ├── pending/
│   ├── risks/
│   └── reports/
├── artifacts/
├── checkpoints/
│   └── project/
└── graph/
```

New projects have an empty profile allowlist and are inaccessible until an administrator grants access:

```text
/project add profile project-alpha operator
/project add route project-alpha telegram REPLACE_WITH_CHAT_ID REPLACE_WITH_THREAD_ID operator
```

Use `-` when the channel has no thread identifier.

## Commands

```text
/project                                      show the active context
/projects                                     list projects allowed for this profile
/project init                                 create the empty manifest (admin)
/project create <slug> | <name>               create and register a project (admin)
/project delete <slug> --confirm              remove a project and its directory (admin)
/project rename <slug> <new-name>             rename a project in the manifest (admin)
/project add profile <slug> <profile>         grant project access (admin)
/project add route <slug> <platform> <chat_id> <thread_id|-> <profile>
                                               add a deterministic route (admin)
/project use <slug>                           select a project outside routed channels
/project use company                          return to organization scope
```

Routed channels are authoritative: manual selection and administrative mutations are blocked there.

## Manifest example

```yaml
version: 1
projects:
  - slug: project-alpha
    name: Project Alpha
    enabled: true
    profiles:
      - operator
    routes:
      - platform: telegram
        chat_id: "REPLACE_WITH_CHAT_ID"
        thread_id: "REPLACE_WITH_THREAD_ID"
        profile: operator
```

## Non-routed sessions

In CLI, TUI, dashboard, and other non-routed surfaces:

```text
/project use project-alpha
/project
```

Return to organization scope with:

```text
/project use company
```

Manual selections are stored with Hermes' profile-scoped plugin state. Selections created by version 0.2 are migrated on first access.

## Security boundaries

- An empty `profiles` list denies access to everyone.
- A route is valid only when its profile is explicitly allowed by the project.
- Slugs are validated before filesystem paths are constructed.
- Runtime state uses Hermes' namespaced, atomic `ctx.state` storage.
- Settings are read only through the plugin-scoped `ctx.get_config()` API.
- Project facts must not enter global memory without an explicit promotion decision.
- External and time-sensitive facts require revalidation.
- The plugin does not create, copy, or manage credentials.

## Troubleshooting

| Symptom | Resolution |
|---|---|
| Plugin is not listed | Enable `hermes-multi-projects` and restart Hermes |
| `Project OS não inicializada` | Run `/project init` from an admin profile |
| Project is unavailable | Grant the current profile with `/project add profile` |
| `CONTEXTO BLOQUEADO` | Restore `PROJECT.md` and `CONTEXT.md` |
| Route already exists | Use a unique platform/chat/thread/profile tuple |
| Settings appear ignored | Ensure values are nested under `entries.hermes-multi-projects.settings` |

## Development

```bash
python3 -m unittest discover -v
python3 -m py_compile __init__.py scripts/project_os.py scripts/install.py
hermes plugins doctor . --ci
```

## License

MIT
