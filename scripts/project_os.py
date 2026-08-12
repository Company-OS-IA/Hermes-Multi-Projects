#!/usr/bin/env python3
"""Provision and validate Hermes Multi-Projects workspaces."""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
REQUIRED = ("PROJECT.md", "CONTEXT.md", "AGENTS.md")
DIRS = ("knowledge", "operations/decisions", "operations/pending", "operations/risks", "operations/reports", "artifacts", "checkpoints/project", "checkpoints/agents", "graph")

def project_path(workspace: Path, slug: str) -> Path:
    if not SLUG.fullmatch(slug): raise ValueError("slug deve usar lowercase, números e hífens.")
    return workspace.resolve() / "projects" / slug

def init(args):
    dest = project_path(Path(args.workspace), args.slug)
    if dest.exists(): raise ValueError(f"Projeto já existe: {dest}")
    for item in DIRS: (dest / item).mkdir(parents=True, exist_ok=True)
    values = {"{{PROJECT_NAME}}": args.name, "{{PROJECT_SLUG}}": args.slug}
    for name in REQUIRED:
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        for old, new in values.items(): text = text.replace(old, new)
        (dest / name).write_text(text, encoding="utf-8")
    print(dest)

def validate(args):
    workspace = Path(args.workspace).resolve(); manifest = Path(args.manifest or workspace / "projects.yaml").resolve()
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    errors=[]; slugs=set(); routes=set()
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        print("INVALID\n- manifesto deve conter `projects` como lista"); return 1
    for project in data["projects"]:
        if not isinstance(project, dict): errors.append("cada projeto deve ser um mapa"); continue
        slug=str(project.get("slug", "")); path=project_path(workspace, slug) if SLUG.fullmatch(slug) else None
        if not path: errors.append(f"slug inválido: {slug!r}"); continue
        if slug in slugs: errors.append(f"slug duplicado: {slug}")
        slugs.add(slug)
        profiles=project.get("profiles", [])
        if not isinstance(profiles, list) or not all(isinstance(p, str) and p for p in profiles): errors.append(f"{slug}: profiles deve ser lista de nomes")
        missing=[x for x in REQUIRED if not (path/x).is_file()]
        if missing: errors.append(f"{slug}: faltam {', '.join(missing)}")
        for route in project.get("routes", []) or []:
            if not isinstance(route, dict): errors.append(f"{slug}: route deve ser mapa"); continue
            missing_keys=[key for key in ("platform", "chat_id", "thread_id", "profile") if not str(route.get(key, ""))]
            if missing_keys: errors.append(f"{slug}: route sem {', '.join(missing_keys)}"); continue
            profile=str(route["profile"])
            if profiles and profile not in profiles: errors.append(f"{slug}: route profile `{profile}` não está em profiles")
            key=(str(route["platform"]).lower(),str(route["chat_id"]),str(route["thread_id"]),profile.lower())
            if key in routes: errors.append(f"{slug}: route duplicada para {key}")
            routes.add(key)
    if errors:
        print("INVALID\n" + "\n".join("- " + x for x in errors)); return 1
    print("VALID"); return 0

def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="cmd", required=True)
    p=sub.add_parser("init"); p.add_argument("--workspace", required=True); p.add_argument("--slug", required=True); p.add_argument("--name", required=True); p.set_defaults(fn=init)
    p=sub.add_parser("validate"); p.add_argument("--workspace", required=True); p.add_argument("--manifest"); p.set_defaults(fn=validate)
    args=parser.parse_args()
    try:
        result=args.fn(args); return result or 0
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())
