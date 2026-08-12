#!/usr/bin/env python3
"""Install the plugin into the active Hermes home without touching Hermes core."""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
NAME = "hermes-multi-projects"

def main() -> int:
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser().resolve()
    target = home / "plugins" / NAME
    if target.exists():
        print(f"ERROR: {target} already exists; remove it only after backup or use git pull there.", file=sys.stderr)
        return 2
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".hermes-project-context.json", "projects.yaml"))
    print(f"Installed: {target}")
    print("Enable by adding 'hermes-multi-projects' to plugins.enabled in config.yaml via your configuration workflow, then restart the gateway.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
