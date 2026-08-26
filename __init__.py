"""Hermes Multi-Projects — project context routing and isolation."""
from __future__ import annotations

import contextvars
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

import yaml

_PLUGIN_KEY = "hermes-multi-projects"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

_PLUGIN_CTX: Any | None = None

_CMD_PROFILE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "multi_projects_command_profile", default=None
)
_CMD_ROUTE: contextvars.ContextVar[
    tuple[dict[str, Any], dict[str, Any]] | None
] = contextvars.ContextVar("multi_projects_command_route", default=None)

_GATEWAY_PLATFORMS = {
    "telegram", "discord", "slack", "whatsapp", "signal",
    "teams", "google_chat", "email", "matrix", "imessage",
}

_REQUIRED_FILES = ("PROJECT.md", "CONTEXT.md")

_DIR_STRUCTURE = (
    "knowledge",
    "operations/decisions",
    "operations/pending",
    "operations/risks",
    "operations/reports",
    "artifacts",
    "checkpoints/project",
    "graph",
)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _cfg() -> dict[str, Any]:
    """Read this plugin's settings through the public Hermes API."""
    if _PLUGIN_CTX is None:
        return {}
    return {
        key: _PLUGIN_CTX.get_config(key, default)
        for key, default in (
            ("workspace_root", ""),
            ("manifest", ""),
            ("admin_profiles", ["default"]),
        )
    }


def _workspace_root() -> Path:
    cfg = _cfg()
    raw = cfg.get("workspace_root") or os.environ.get("HERMES_HOME", "~/.hermes")
    return Path(str(raw)).expanduser().resolve()


def _manifest_path() -> Path:
    cfg = _cfg()
    root = _workspace_root()
    return Path(
        str(cfg.get("manifest") or root / "projects.yaml")
    ).expanduser().resolve()


def _legacy_state_path() -> Path:
    return _workspace_root() / ".hermes-project-context.json"


def _project_root(slug: str) -> Path:
    if not _SLUG.fullmatch(slug):
        raise ValueError("Slug must be lowercase alphanumeric with hyphens.")
    projects_root = (_workspace_root() / "projects").resolve()
    path = (projects_root / slug).resolve()
    if not path.is_relative_to(projects_root):
        raise ValueError("Project path escapes the configured projects root.")
    return path


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------

def _load_manifest() -> dict[str, Any]:
    path = _manifest_path()
    if not path.is_file():
        return {"projects": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not isinstance(data.get("projects", []), list):
        raise ValueError(f"Invalid manifest: {path}")
    return data


def _write_manifest(data: dict[str, Any]) -> None:
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    temp.replace(path)


# ---------------------------------------------------------------------------
# State (per-profile manual selection)
# ---------------------------------------------------------------------------

def _legacy_state() -> dict[str, str]:
    """Read v0.2 selections for one-time migration to ``ctx.state``."""
    path = _legacy_state_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _set_selection(profile: str, slug: str) -> None:
    if _PLUGIN_CTX is not None:
        _PLUGIN_CTX.state.set(f"selection:{profile}", slug)
        return

    # Test/development fallback when the module is used outside Hermes.
    path = _legacy_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state = _legacy_state()
    state[profile] = slug
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _selected(profile: str) -> dict[str, Any] | None:
    slug: str | None = None
    if _PLUGIN_CTX is not None:
        slug = _PLUGIN_CTX.state.get(f"selection:{profile}")
        if slug is None:
            slug = _legacy_state().get(profile)
            if slug:
                _PLUGIN_CTX.state.set(f"selection:{profile}", slug)
    else:
        slug = _legacy_state().get(profile)

    if not slug or slug == "company":
        return None
    project = _project(slug)
    if project is None:
        _set_selection(profile, "company")
    return project


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------

def _projects() -> list[dict[str, Any]]:
    return [
        p for p in _load_manifest().get("projects", [])
        if isinstance(p, dict)
        and p.get("enabled", True)
        and _SLUG.fullmatch(str(p.get("slug", "")))
    ]


def _project(slug: str) -> dict[str, Any] | None:
    key = slug.strip().lower()
    return next(
        (p for p in _projects() if str(p.get("slug", "")).lower() == key),
        None,
    )


def _allowed(project: dict[str, Any], profile: str) -> bool:
    raw = project.get("profiles", [])
    if not isinstance(raw, list):
        return False
    profiles = [str(p).lower() for p in raw]
    return profile.lower() in profiles


def _admin(profile: str) -> bool:
    raw = _cfg().get("admin_profiles", ["default"])
    values = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    allowed = [str(p).lower() for p in values if str(p).strip()]
    return profile.lower() in allowed


def _slugify(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", normalized)).strip("-")[:63]


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

def _profile(event: Any = None) -> str:
    source = getattr(event, "source", None)
    return str(getattr(source, "profile", "") or "default").lower()


def _platform_value(value: Any) -> str:
    """Normalize Hermes Platform enums and plain string platform names."""
    raw = getattr(value, "value", value)
    return str(raw or "").lower()


def _route(
    event: Any,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    source = getattr(event, "source", None)
    platform = _platform_value(getattr(source, "platform", ""))
    chat_id = str(getattr(source, "chat_id", "") or "")
    thread_id = str(getattr(source, "thread_id", "") or "")
    profile = _profile(event)

    for project in _projects():
        for route in project.get("routes", []) or []:
            if not isinstance(route, dict):
                continue
            if (
                str(route.get("platform", "")).lower() == platform
                and str(route.get("chat_id", "")) == chat_id
                and str(route.get("thread_id", "")) == thread_id
                and str(route.get("profile", "")).lower() == profile
                and _allowed(project, profile)
            ):
                return project, route
    return None


def _active_profile() -> str:
    if _PLUGIN_CTX is not None:
        return str(_PLUGIN_CTX.profile_name or "default").lower()
    hermes_home = os.environ.get("HERMES_HOME", "")
    env_profile = os.environ.get("HERMES_PROFILE")
    if env_profile:
        return env_profile.lower()
    if "/profiles/" in hermes_home:
        return Path(hermes_home).name.lower()
    return "default"


# ---------------------------------------------------------------------------
# Context generation
# ---------------------------------------------------------------------------

def _context(
    project: dict[str, Any] | None, profile: str, source: str
) -> str:
    if project is None:
        return (
            "## Contexto operacional ativo\n"
            "Escopo: company\n"
            "Regra: não leia ou grave dados específicos de projeto "
            "sem selecionar um projeto com `/project use <slug>`."
        )

    slug = str(project.get("slug", ""))
    if not _SLUG.fullmatch(slug):
        return "## CONTEXTO BLOQUEADO\nManifesto contém slug de projeto inválido."

    path = _project_root(slug)
    required = [path / name for name in _REQUIRED_FILES]
    missing = [p.name for p in required if not p.is_file()]

    if missing:
        return (
            f"## CONTEXTO BLOQUEADO\n"
            f"Projeto: {slug}\n"
            f"O projeto está mal provisionado; faltam: {', '.join(missing)}. "
            f"Não leia/escreva artefatos deste projeto até corrigir."
        )

    return (
        f"## Contexto operacional ativo\n"
        f"Projeto: {project.get('name', slug)}\n"
        f"Slug: {slug}\n"
        f"Perfil: {profile}\n"
        f"Origem: {source}\n"
        f"Raiz canônica: {path}\n\n"
        f"Antes de trabalho material, leia PROJECT.md e CONTEXT.md "
        f"na raiz do projeto. Use somente este namespace para conhecimento, "
        f"decisões, artefatos e checkpoints. Não leia, cite ou grave dados "
        f"de outro projeto. Dados externos/temporais exigem revalidação."
    )


# ---------------------------------------------------------------------------
# Admin commands
# ---------------------------------------------------------------------------

def _project_init(profile: str) -> str:
    if not _admin(profile):
        return "Perfil não autorizado a inicializar o Project OS. / Not authorized to initialize Project OS."

    path = _manifest_path()
    if path.exists():
        return f"Project OS já está inicializado: `{path}`. / Already initialized."

    _write_manifest({"version": 1, "projects": []})
    return (
        f"Project OS inicializada em `{path.parent}`. "
        f"Use `/project create <slug> | <nome>` para criar o primeiro projeto."
    )


def _project_create(raw: str, profile: str) -> str:
    if not _admin(profile):
        return "Perfil não autorizado a criar projetos. / Not authorized to create projects."
    if not _manifest_path().is_file():
        return "Project OS não inicializada. Use `/project init` primeiro. / Not initialized."

    parts = [p.strip() for p in raw.split("|", 1)]
    candidate = parts[0]
    explicit_slug = _SLUG.fullmatch(candidate.lower()) is not None
    slug = candidate.lower() if explicit_slug else _slugify(candidate)

    if not _SLUG.fullmatch(slug):
        return "Uso: `/project create <slug> | <nome>` ou `/project create <nome>`."

    name = (
        parts[1] if len(parts) == 2 and parts[1]
        else (slug.replace("-", " ").title() if explicit_slug else candidate)
    )

    data = _load_manifest()
    if _project(slug) is not None:
        return f"Projeto `{slug}` já está cadastrado. / Already registered."

    dest = _project_root(slug)
    if dest.exists():
        return f"Diretório do projeto já existe: `{dest}`. / Directory already exists."

    templates = Path(__file__).resolve().parent / "templates"
    try:
        for item in _DIR_STRUCTURE:
            (dest / item).mkdir(parents=True, exist_ok=True)
        for filename in _REQUIRED_FILES:
            text = (templates / filename).read_text(encoding="utf-8")
            text = text.replace("{{PROJECT_NAME}}", name)
            text = text.replace("{{PROJECT_SLUG}}", slug)
            (dest / filename).write_text(text, encoding="utf-8")

        data["projects"].append({
            "slug": slug,
            "name": name,
            "enabled": True,
            "profiles": [],
            "routes": [],
        })
        _write_manifest(data)
    except Exception as exc:
        if dest.exists():
            shutil.rmtree(dest)
        return f"Falha ao criar projeto: {exc} / Failed to create project."

    return (
        f"Projeto `{slug}` criado e cadastrado. "
        f"Próximo passo: `/project add profile {slug} <perfil>` "
        f"e `/project add route {slug} <plataforma> <chat_id> <thread_id|-> <perfil>`."
    )


def _project_delete(raw: str, profile: str) -> str:
    if not _admin(profile):
        return "Perfil não autorizado a deletar projetos. / Not authorized to delete projects."

    parts = raw.split()
    slug = parts[0].lower() if parts else ""
    if len(parts) != 2 or parts[1] != "--confirm" or not _SLUG.fullmatch(slug):
        return "Uso: `/project delete <slug> --confirm`. Esta ação remove o diretório do projeto."

    data = _load_manifest()
    project = next(
        (p for p in data["projects"]
         if isinstance(p, dict) and str(p.get("slug", "")).lower() == slug),
        None,
    )
    if not project:
        return f"Projeto `{slug}` não existe. / Project not found."

    # Remove from manifest
    data["projects"] = [
        p for p in data["projects"]
        if not isinstance(p, dict) or str(p.get("slug", "")).lower() != slug
    ]
    _write_manifest(data)

    # Remove directory
    dest = _project_root(slug)
    if dest.exists():
        shutil.rmtree(dest)

    if _selected(profile) is None:
        _set_selection(profile, "company")

    return f"Projeto `{slug}` deletado. / Project deleted."


def _project_rename(raw: str, profile: str) -> str:
    if not _admin(profile):
        return "Perfil não autorizado a renomear projetos. / Not authorized to rename projects."

    parts = raw.split(maxsplit=1)
    if len(parts) != 2:
        return "Uso: `/project rename <slug> <novo-nome>`."

    slug, new_name = parts[0].strip().lower(), parts[1].strip()
    if not _SLUG.fullmatch(slug):
        return "Slug inválido."

    data = _load_manifest()
    project = next(
        (p for p in data["projects"]
         if isinstance(p, dict) and str(p.get("slug", "")).lower() == slug),
        None,
    )
    if not project:
        return f"Projeto `{slug}` não existe. / Project not found."

    old_name = project.get("name", slug)
    project["name"] = new_name
    _write_manifest(data)

    return f"Projeto `{slug}` renomeado de `{old_name}` para `{new_name}`. / Renamed."


def _project_add_profile(raw: str, actor: str) -> str:
    if not _admin(actor):
        return "Perfil não autorizado a alterar projetos. / Not authorized."

    parts = raw.split()
    if len(parts) != 2:
        return "Uso: `/project add profile <slug> <perfil>`."

    slug, prof = parts[0].lower(), parts[1].lower()
    if not _SLUG.fullmatch(slug) or not _PROFILE_RE.fullmatch(prof):
        return "Slug ou perfil inválido. / Invalid slug or profile."

    data = _load_manifest()
    project = next(
        (p for p in data["projects"]
         if isinstance(p, dict) and str(p.get("slug", "")).lower() == slug),
        None,
    )
    if not project:
        return f"Projeto `{slug}` não existe. / Project not found."

    profiles = project.setdefault("profiles", [])
    if not isinstance(profiles, list):
        return f"Projeto `{slug}` tem `profiles` inválido."

    if prof in [str(p).lower() for p in profiles]:
        return f"Perfil `{prof}` já está autorizado em `{slug}`. / Already authorized."

    profiles.append(prof)
    _write_manifest(data)
    return f"Perfil `{prof}` autorizado no projeto `{slug}`. / Profile authorized."


def _project_add_route(raw: str, actor: str) -> str:
    if not _admin(actor):
        return "Perfil não autorizado a alterar projetos. / Not authorized."

    parts = raw.split()
    if len(parts) != 5:
        return (
            "Uso: `/project add route <slug> <plataforma> "
            "<chat_id> <thread_id|-> <perfil>`."
        )

    slug, platform, chat_id, thread_id, prof = parts
    slug, platform, prof = slug.lower(), platform.lower(), prof.lower()

    if not _SLUG.fullmatch(slug) or not _PROFILE_RE.fullmatch(prof):
        return "Slug ou perfil inválido. / Invalid slug or profile."
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", platform) or not chat_id:
        return "Plataforma ou chat_id inválido. / Invalid platform or chat_id."
    if any(c.isspace() for c in chat_id):
        return "chat_id inválido. / Invalid chat_id."

    thread_id = "" if thread_id == "-" else thread_id
    if thread_id and any(c.isspace() for c in thread_id):
        return "thread_id inválido. / Invalid thread_id."

    data = _load_manifest()
    project = next(
        (p for p in data["projects"]
         if isinstance(p, dict) and str(p.get("slug", "")).lower() == slug),
        None,
    )
    if not project:
        return f"Projeto `{slug}` não existe. / Project not found."

    authorized = [
        str(p).lower() for p in project.get("profiles", []) or []
    ]
    if prof not in authorized:
        return (
            f"Perfil `{prof}` não autorizado no projeto `{slug}`. "
            f"Use `/project add profile {slug} {prof}` primeiro. / Not authorized."
        )

    # Check for duplicate routes across all projects
    key = (platform, chat_id, thread_id, prof)
    for candidate in _projects():
        for route in candidate.get("routes", []) or []:
            if not isinstance(route, dict):
                continue
            other = (
                str(route.get("platform", "")).lower(),
                str(route.get("chat_id", "")),
                str(route.get("thread_id", "")),
                str(route.get("profile", "")).lower(),
            )
            if other == key:
                return (
                    f"Esta rota já existe no projeto "
                    f"`{candidate.get('slug')}`. / Route already exists."
                )

    routes = project.setdefault("routes", [])
    if not isinstance(routes, list):
        return f"Projeto `{slug}` tem `routes` inválido."

    routes.append({
        "platform": platform,
        "chat_id": chat_id,
        "thread_id": thread_id,
        "profile": prof,
    })
    _write_manifest(data)

    tid_display = thread_id or "-"
    return (
        f"Rota adicionada ao projeto `{slug}`: "
        f"`{platform}` / `{chat_id}` / `{tid_display}` → `{prof}`. "
        f"Reinicie o gateway para aplicar. / Route added."
    )


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _pre_llm_call(session_id: str = "", **kwargs: Any) -> dict[str, str] | None:
    # Routed gateway messages already receive a deterministic context in
    # pre_gateway_dispatch. Do not append the profile-global manual selection.
    if str(kwargs.get("platform") or "").lower() in _GATEWAY_PLATFORMS:
        return None
    profile = _active_profile()
    return {
        "context": _context(
            _selected(profile), profile, f"manual:{session_id or 'session'}"
        )
    }


def _pre_gateway_dispatch(event: Any, **_: Any) -> dict[str, str] | None:
    text = str(getattr(event, "text", "") or "").strip()
    profile = _profile(event)
    routed = _route(event)

    if text.startswith("/"):
        # Let Hermes' native command dispatcher handle slash commands.
        _CMD_PROFILE.set(profile)
        _CMD_ROUTE.set(routed)
        return None

    if routed:
        ctx = _context(routed[0], profile, "rota")
        return {"action": "rewrite", "text": ctx + "\n\nMensagem do usuário:\n" + text}

    ctx = _context(None, profile, "company")
    return {"action": "rewrite", "text": ctx + "\n\nMensagem do usuário:\n" + text}


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

def project_context(_: dict[str, Any], **kwargs: Any) -> str:
    try:
        profile = _active_profile()
        selected = _selected(profile)
        return json.dumps({
            "success": True,
            "profile": profile,
            "project": (selected or {}).get("slug", "company"),
            "context": _context(selected, profile, "tool"),
        })
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _command_profile() -> str:
    return _CMD_PROFILE.get() or _active_profile()


def _command_route() -> tuple[dict[str, Any], dict[str, Any]] | None:
    return _CMD_ROUTE.get()


def _cli_project(raw: str) -> str:
    profile = _command_profile()
    routed = _command_route()

    if not raw:
        project = routed[0] if routed else _selected(profile)
        source = "rota" if routed else "manual"
        return _context(project, profile, source)

    parts = raw.split(maxsplit=1)
    action = parts[0].lower()

    # In routed channels, only read actions are allowed
    if routed and action in {"init", "create", "add", "delete", "rename"}:
        return (
            "Este canal é roteado para projeto; "
            "inicialização, criação e alteração só podem ser feitas "
            "fora de canais de projeto. / Routed channel — read only."
        )

    # /project init
    if action == "init" and len(parts) == 1:
        return _project_init(profile)

    # /project create <slug> | <name>
    if action == "create" and len(parts) == 2:
        return _project_create(parts[1], profile)

    # /project delete <slug>
    if action == "delete" and len(parts) == 2:
        return _project_delete(parts[1], profile)

    # /project rename <slug> <new-name>
    if action == "rename" and len(parts) == 2:
        return _project_rename(parts[1], profile)

    # /project add profile|route ...
    if action == "add" and len(parts) == 2:
        kind, _, args = parts[1].partition(" ")
        if kind.lower() == "profile":
            return _project_add_profile(args, profile)
        if kind.lower() == "route":
            return _project_add_route(args, profile)
        return (
            "Uso: `/project add profile <slug> <perfil>` "
            "ou `/project add route <slug> <plataforma> "
            "<chat_id> <thread_id|-> <perfil>`."
        )

    # /project use <slug|company>
    if action == "use" and len(parts) == 2:
        if routed:
            return (
                f"Este canal é roteado para `{routed[0]['slug']}`; "
                f"a seleção manual está bloqueada. / Routed — manual selection blocked."
            )
        slug = parts[1].strip().lower()
        if slug == "company":
            _set_selection(profile, "company")
            return "Contexto selecionado: company. / Scope set to company."
        project = _project(slug)
        if not project or not _allowed(project, profile):
            return (
                f"Projeto `{slug}` não existe ou não está habilitado "
                f"para `{profile}`. / Not found or not authorized."
            )
        _set_selection(profile, slug)
        return _context(project, profile, "manual")

    # Unknown command
    return (
        "Uso:\n"
        "- `/project` — mostra contexto atual\n"
        "- `/projects` — lista projetos\n"
        "- `/project init` — inicializa Project OS\n"
        "- `/project create <slug> | <nome>` — cria projeto\n"
        "- `/project delete <slug>` — deleta projeto\n"
        "- `/project rename <slug> <novo-nome>` — renomeia\n"
        "- `/project add profile <slug> <perfil>` — autoriza perfil\n"
        "- `/project add route <slug> <plataforma> <chat_id> <thread_id|-> <perfil>` — cria rota\n"
        "- `/project use <slug|company>` — seleciona contexto"
    )


def _cli_projects(_: str) -> str:
    profile = _command_profile()
    names = [
        f"- `{p['slug']}` — {p.get('name', p['slug'])}"
        for p in _projects()
        if _allowed(p, profile)
    ]
    return (
        "Projetos disponíveis:\n"
        + ("\n".join(names) or "Nenhum.")
        + "\n\nUse `/project use <slug>`."
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx: Any) -> None:
    global _PLUGIN_CTX
    _PLUGIN_CTX = ctx

    ctx.register_hook("pre_gateway_dispatch", _pre_gateway_dispatch)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_command(
        "project", _cli_project, "Show or select active project context."
    )
    ctx.register_command(
        "projects", _cli_projects, "List available project contexts."
    )
    ctx.register_tool(
        name="project_context",
        toolset=_PLUGIN_KEY,
        schema={
            "name": "project_context",
            "description": (
                "Return the active project scope and canonical root for the current "
                "Hermes profile. Use before project-scoped work when the active "
                "context is uncertain."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
        handler=project_context,
        description="Read active project context.",
        emoji="🗂️",
    )
    ctx.register_skill(
        "project-context",
        Path(__file__).parent / "skills" / "project-context" / "SKILL.md",
    )
