"""Hermes Multi-Projects — portable project-context plugin."""
from __future__ import annotations

import contextvars
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

_PLUGIN_KEY = "hermes-multi-projects"
_COMMAND = re.compile(r"^/(project|projects)(?:@[A-Za-z0-9_]+)?(?:\s+(.*))?$", re.DOTALL)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_COMMAND_PROFILE: contextvars.ContextVar[str] = contextvars.ContextVar("multi_projects_command_profile", default="default")
_COMMAND_ROUTE: contextvars.ContextVar[tuple[dict[str, Any], dict[str, Any]] | None] = contextvars.ContextVar("multi_projects_command_route", default=None)


def _cfg() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config
        root = load_config() or {}
        return dict((((root.get("plugins") or {}).get("entries") or {}).get(_PLUGIN_KEY) or {}))
    except Exception:
        return {}


def _manifest_path() -> Path:
    cfg = _cfg()
    root = Path(str(cfg.get("workspace_root") or ".")).expanduser().resolve()
    return Path(str(cfg.get("manifest") or root / "projects.yaml")).expanduser().resolve()


def _load_manifest() -> dict[str, Any]:
    path = _manifest_path()
    if not path.is_file():
        return {"projects": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not isinstance(data.get("projects", []), list):
        raise ValueError(f"Manifesto inválido: {path}")
    return data


def _write_manifest(data: dict[str, Any]) -> None:
    path = _manifest_path(); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    temp.replace(path)


def _admin(profile: str) -> bool:
    raw = _cfg().get("admin_profiles", ["default"])
    values = [raw] if isinstance(raw, str) else raw
    allowed = [str(p).lower() for p in values if str(p).strip()]
    return profile.lower() in allowed


def _project_root(slug: str) -> Path:
    if not _SLUG.fullmatch(slug):
        raise ValueError("slug deve usar lowercase, números e hífens.")
    root = Path(str(_cfg().get("workspace_root") or ".")).expanduser().resolve()
    return root / "projects" / slug


def _project_init(profile: str) -> str:
    if not _admin(profile): return "Perfil não autorizado a inicializar o Project OS."
    path = _manifest_path()
    if path.exists():
        return f"Project OS já está inicializado: `{path}`."
    _write_manifest({"version": 1, "projects": []})
    return f"Project OS inicializada em `{path.parent}`. Use `/project create <slug> | <nome>` para criar o primeiro projeto."


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", normalized)).strip("-")[:63]


def _project_create(raw: str, profile: str) -> str:
    if not _admin(profile): return "Perfil não autorizado a criar projetos."
    if not _manifest_path().is_file(): return "Project OS não inicializada. Use `/project init` primeiro."
    parts = [p.strip() for p in raw.split("|", 1)]
    candidate = parts[0]
    explicit_slug = _SLUG.fullmatch(candidate.lower()) is not None
    slug = candidate.lower() if explicit_slug else _slugify(candidate)
    if not _SLUG.fullmatch(slug): return "Uso: `/project create <slug> | <nome>` ou `/project create <nome>`."
    name = parts[1] if len(parts) == 2 and parts[1] else (slug.replace("-", " ").title() if explicit_slug else candidate)
    data = _load_manifest()
    if _project(slug) is not None: return f"Projeto `{slug}` já está cadastrado."
    dest = _project_root(slug)
    if dest.exists(): return f"Diretório do projeto já existe: `{dest}`."
    templates = Path(__file__).resolve().parent / "templates"
    try:
        for item in ("knowledge", "operations/decisions", "operations/pending", "operations/risks", "operations/reports", "artifacts", "checkpoints/project", "checkpoints/agents", "graph"):
            (dest / item).mkdir(parents=True, exist_ok=True)
        for filename in ("PROJECT.md", "CONTEXT.md", "AGENTS.md"):
            text = (templates / filename).read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", name).replace("{{PROJECT_SLUG}}", slug)
            (dest / filename).write_text(text, encoding="utf-8")
        data["projects"].append({"slug": slug, "name": name, "enabled": True, "profiles": [], "routes": []})
        _write_manifest(data)
    except Exception as exc:
        if dest.exists():
            import shutil; shutil.rmtree(dest)
        return f"Falha ao criar projeto: {exc}"
    return f"Projeto `{slug}` criado e cadastrado. Próximo passo: use `/project add profile {slug} <perfil>` e `/project add route {slug} <plataforma> <chat_id> <thread_id|-> <perfil>`."


def _project_add_profile(raw: str, actor: str) -> str:
    if not _admin(actor): return "Perfil não autorizado a alterar projetos."
    parts = raw.split()
    if len(parts) != 2: return "Uso: `/project add profile <slug> <perfil>`."
    slug, profile = parts[0].lower(), parts[1].lower()
    if not _SLUG.fullmatch(slug) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", profile): return "Slug ou perfil inválido."
    data = _load_manifest(); project = next((p for p in data["projects"] if isinstance(p, dict) and str(p.get("slug", "")).lower() == slug), None)
    if not project: return f"Projeto `{slug}` não existe."
    profiles = project.setdefault("profiles", [])
    if not isinstance(profiles, list): return f"Projeto `{slug}` tem `profiles` inválido."
    if profile in [str(p).lower() for p in profiles]: return f"Perfil `{profile}` já está autorizado em `{slug}`."
    profiles.append(profile); _write_manifest(data)
    return f"Perfil `{profile}` autorizado no projeto `{slug}`."


def _project_add_route(raw: str, actor: str) -> str:
    if not _admin(actor): return "Perfil não autorizado a alterar projetos."
    parts = raw.split()
    if len(parts) != 5: return "Uso: `/project add route <slug> <plataforma> <chat_id> <thread_id|-> <perfil>`."
    slug, platform, chat_id, thread_id, profile = parts
    slug, platform, profile = slug.lower(), platform.lower(), profile.lower()
    if not _SLUG.fullmatch(slug) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", profile): return "Slug ou perfil inválido."
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", platform) or not chat_id or any(c.isspace() for c in chat_id): return "Plataforma ou chat_id inválido."
    thread_id = "" if thread_id == "-" else thread_id
    if thread_id and any(c.isspace() for c in thread_id): return "thread_id inválido."
    data = _load_manifest(); project = next((p for p in data["projects"] if isinstance(p, dict) and str(p.get("slug", "")).lower() == slug), None)
    if not project: return f"Projeto `{slug}` não existe."
    if profile not in [str(p).lower() for p in project.get("profiles", []) or []]: return f"Perfil `{profile}` não autorizado no projeto `{slug}`. Use `/project add profile {slug} {profile}` primeiro."
    key = (platform, chat_id, thread_id, profile)
    for candidate in _projects():
        for route in candidate.get("routes", []) or []:
            if not isinstance(route, dict): continue
            other = (str(route.get("platform", "")).lower(), str(route.get("chat_id", "")), str(route.get("thread_id", "")), str(route.get("profile", "")).lower())
            if other == key:
                return f"Esta rota já existe no projeto `{candidate.get('slug')}`."
    routes = project.setdefault("routes", [])
    if not isinstance(routes, list): return f"Projeto `{slug}` tem `routes` inválido."
    routes.append({"platform": platform, "chat_id": chat_id, "thread_id": thread_id, "profile": profile})
    _write_manifest(data)
    return f"Rota adicionada ao projeto `{slug}`: `{platform}` / `{chat_id}` / `{thread_id or '- '}` → `{profile}`. Reinicie o gateway para aplicar."


def _projects() -> list[dict[str, Any]]:
    return [p for p in _load_manifest().get("projects", []) if isinstance(p, dict) and p.get("enabled", True) and _SLUG.fullmatch(str(p.get("slug", "")))]


def _project(slug: str) -> dict[str, Any] | None:
    key = slug.strip().lower()
    return next((p for p in _projects() if str(p.get("slug", "")).lower() == key), None)


def _profile(event: Any = None) -> str:
    source = getattr(event, "source", None)
    return str(getattr(source, "profile", "") or "default").lower()


def _platform_value(value: Any) -> str:
    """Normalize Hermes Platform enums and plain string platform names."""
    raw = getattr(value, "value", value)
    return str(raw or "").lower()


def _route(event: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
    source = getattr(event, "source", None)
    platform = _platform_value(getattr(source, "platform", ""))
    chat_id = str(getattr(source, "chat_id", "") or "")
    thread_id = str(getattr(source, "thread_id", "") or "")
    profile = _profile(event)
    for project in _projects():
        for route in project.get("routes", []) or []:
            if not isinstance(route, dict):
                continue
            if (str(route.get("platform", "")).lower() == platform and str(route.get("chat_id", "")) == chat_id and str(route.get("thread_id", "")) == thread_id and str(route.get("profile", "")).lower() == profile and _allowed(project, profile)):
                return project, route
    return None


def _state_path() -> Path:
    cfg = _cfg(); root = Path(str(cfg.get("workspace_root") or ".")).expanduser().resolve()
    return root / ".hermes-project-context.json"


def _state() -> dict[str, str]:
    path = _state_path()
    if not path.is_file(): return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _set_selection(profile: str, slug: str) -> None:
    path = _state_path(); path.parent.mkdir(parents=True, exist_ok=True)
    state = _state(); state[profile] = slug
    temp = path.with_suffix(".tmp"); temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"); temp.replace(path)


def _selected(profile: str) -> dict[str, Any] | None:
    slug = _state().get(profile, "company")
    return None if slug == "company" else _project(slug)


def _allowed(project: dict[str, Any], profile: str) -> bool:
    profiles = [str(p).lower() for p in project.get("profiles", []) or []]
    return not profiles or profile in profiles


def _context(project: dict[str, Any] | None, profile: str, source: str) -> str:
    if project is None:
        return """## Contexto operacional ativo\nEscopo: company\nRegra: não leia ou grave dados específicos de projeto sem selecionar um projeto com `/project use <slug>`."""
    slug = str(project.get("slug", ""))
    if not _SLUG.fullmatch(slug):
        return "## CONTEXTO BLOQUEADO\nManifesto contém slug de projeto inválido."
    cfg = _cfg(); root = Path(str(cfg.get("workspace_root") or ".")).expanduser().resolve()
    path = root / "projects" / slug
    required = [path / name for name in ("PROJECT.md", "CONTEXT.md", "AGENTS.md")]
    missing = [p.name for p in required if not p.is_file()]
    if missing:
        return f"## CONTEXTO BLOQUEADO\nProjeto: {project['slug']}\nO projeto está mal provisionado; faltam: {', '.join(missing)}. Não leia/escreva artefatos deste projeto até corrigir."
    return f"""## Contexto operacional ativo
Projeto: {project.get('name', project['slug'])}
Slug: {project['slug']}
Perfil: {profile}
Origem: {source}
Raiz canônica: {path}

Antes de trabalho material, leia: PROJECT.md, CONTEXT.md e AGENTS.md na raiz do projeto. Use somente este namespace para conhecimento, decisões, artefatos e checkpoints. Não leia, cite ou grave dados de outro projeto. Dados externos/temporais exigem revalidação."""


def _active_profile() -> str:
    return str(os.environ.get("HERMES_PROFILE") or Path(os.environ.get("HERMES_HOME", "")).name if "/profiles/" in os.environ.get("HERMES_HOME", "") else "default").lower()


_GATEWAY_PLATFORMS = {"telegram", "discord", "slack", "whatsapp", "signal", "teams", "google_chat", "email", "matrix", "imessage"}


def _pre_llm_call(session_id: str = "", **kwargs: Any) -> dict[str, str] | None:
    # Routed gateway messages already receive a deterministic context in
    # pre_gateway_dispatch. Do not append the profile-global manual selection.
    if str(kwargs.get("platform") or "").lower() in _GATEWAY_PLATFORMS:
        return None
    profile = _active_profile()
    return {"context": _context(_selected(profile), profile, f"manual:{session_id or 'session'}")}


def _pre_gateway_dispatch(event: Any, **_: Any) -> dict[str, str] | None:
    text = str(getattr(event, "text", "") or "").strip()
    # Every slash command must reach Hermes' native command dispatcher. It owns
    # direct gateway replies; rewriting here only feeds a synthetic prompt to
    # the LLM and does not reliably send a response to Telegram.
    profile = _profile(event)
    routed = _route(event)
    if text.startswith("/"):
        # Gateway dispatch calls the registered handler synchronously after this
        # hook. Preserve this event's identity so the response is both sent
        # natively and authorized against the profile/route that invoked it.
        _COMMAND_PROFILE.set(profile)
        _COMMAND_ROUTE.set(routed)
        return None
    if routed:
        return {"action":"rewrite", "text":_context(routed[0], profile, "rota") + "\n\nMensagem do usuário:\n" + text}
    return {"action":"rewrite", "text":_context(None, profile, "company") + "\n\nMensagem do usuário:\n" + text}


def project_context(_: dict[str, Any], **kwargs: Any) -> str:
    profile = str(kwargs.get("profile") or "default").lower()
    return json.dumps({"success": True, "profile": profile, "project": (_selected(profile) or {}).get("slug", "company"), "context": _context(_selected(profile), profile, "tool")})


def _command_profile() -> str:
    return _COMMAND_PROFILE.get() or _active_profile()


def _command_route() -> tuple[dict[str, Any], dict[str, Any]] | None:
    return _COMMAND_ROUTE.get()


def _cli_project(raw: str) -> str:
    profile, routed = _command_profile(), _command_route()
    if not raw:
        return _context(routed[0] if routed else _selected(profile), profile, "rota" if routed else "manual")
    parts = raw.split(maxsplit=1); action = parts[0].lower()
    if routed and action in {"init", "create", "add"}:
        return "Este canal é roteado para projeto; inicialização, criação e alteração só podem ser feitas fora de canais de projeto."
    if action == "init" and len(parts) == 1: return _project_init(profile)
    if action == "create" and len(parts) == 2: return _project_create(parts[1], profile)
    if action == "add" and len(parts) == 2:
        kind, _, args = parts[1].partition(" ")
        if kind.lower() == "profile": return _project_add_profile(args, profile)
        if kind.lower() == "route": return _project_add_route(args, profile)
        return "Uso: `/project add profile <slug> <perfil>` ou `/project add route <slug> <plataforma> <chat_id> <thread_id|-> <perfil>`."
    if action != "use" or len(parts) != 2:
        return "Uso: `/project`, `/projects`, `/project init`, `/project create <slug> | <nome>`, `/project add profile ...`, `/project add route ...` ou `/project use <slug|company>`."
    if routed: return f"Este canal é roteado para `{routed[0]['slug']}`; a seleção manual está bloqueada."
    slug = parts[1].strip().lower()
    if slug == "company":
        _set_selection(profile, "company"); return "Contexto selecionado: company."
    project = _project(slug)
    if not project or not _allowed(project, profile): return f"Projeto `{slug}` não existe ou não está habilitado para `{profile}`."
    _set_selection(profile, slug); return _context(project, profile, "manual")


def _cli_projects(_: str) -> str:
    profile = _command_profile()
    names = [f"- `{p['slug']}` — {p.get('name', p['slug'])}" for p in _projects() if _allowed(p, profile)]
    return "Projetos disponíveis:\n" + ("\n".join(names) or "Nenhum.") + "\n\nUse `/project use <slug>`."

def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", _pre_gateway_dispatch)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_command("project", _cli_project, "Show or select active project context.")
    ctx.register_command("projects", _cli_projects, "List available project contexts.")
    ctx.register_tool(name="project_context", toolset="file", schema={"name":"project_context","description":"Return active company or project context for this profile.","parameters":{"type":"object","properties":{}}}, handler=project_context, description="Read active project context.", emoji="🗂️")
