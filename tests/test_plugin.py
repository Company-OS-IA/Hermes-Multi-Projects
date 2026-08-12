import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PLUGIN = Path(__file__).parents[1] / "__init__.py"


def load_plugin():
    spec = importlib.util.spec_from_file_location("multi_projects", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event(text, profile="pedro", platform="telegram", chat_id="-1001", thread_id="7"):
    return SimpleNamespace(text=text, source=SimpleNamespace(profile=profile, platform=platform, chat_id=chat_id, thread_id=thread_id))


class MultiProjectsTests(unittest.TestCase):
    def test_gateway_route_injects_only_its_project_context(self):
        plugin = load_plugin()
        manifest = {"projects": [{"slug":"pixel-x", "name":"Pixel X", "profiles":["pedro"], "routes":[{"platform":"telegram","chat_id":"-1001","thread_id":"7","profile":"pedro"}]}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = root / "projects/pixel-x"; project.mkdir(parents=True)
            for name in ("PROJECT.md", "CONTEXT.md", "AGENTS.md"): (project / name).write_text("ok")
            with patch.object(plugin, "_cfg", return_value={"workspace_root":str(root)}), patch.object(plugin, "_load_manifest", return_value=manifest):
                result = plugin._pre_gateway_dispatch(event("analisar campanha"))
        self.assertIn("Slug: pixel-x", result["text"])
        self.assertIn("Mensagem do usuário:\nanalisar campanha", result["text"])

    def test_project_init_creates_empty_manifest(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(plugin, "_cfg", return_value={"workspace_root":str(root)}):
                result = plugin._project_init("default")
                manifest = plugin._load_manifest()
            self.assertIn("inicializada", result)
            self.assertEqual(manifest, {"version": 1, "projects": []})

    def test_main_can_create_and_register_project(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(plugin, "_cfg", return_value={"workspace_root":str(root), "admin_profiles":["default"]}):
                plugin._project_init("default")
                result = plugin._project_create("pixel-x | Pixel X", "default")
                manifest = plugin._load_manifest()
                exists = (root / "projects/pixel-x/PROJECT.md").is_file()
            self.assertIn("pixel-x", result)
            self.assertEqual(manifest["projects"][0]["slug"], "pixel-x")
            self.assertTrue(exists)

    def test_main_can_create_from_human_name(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(plugin, "_cfg", return_value={"workspace_root":str(root), "admin_profiles":["default"]}):
                plugin._project_init("default")
                result = plugin._project_create("Arquitetando Viagens", "default")
                manifest = plugin._load_manifest()
            self.assertIn("arquitetando-viagens", result)
            self.assertEqual(manifest["projects"][0]["slug"], "arquitetando-viagens")

    def test_string_admin_profile_is_supported(self):
        plugin = load_plugin()
        with patch.object(plugin, "_cfg", return_value={"admin_profiles":"default"}):
            self.assertTrue(plugin._admin("default"))

    def test_non_admin_cannot_create_project(self):
        plugin = load_plugin()
        with patch.object(plugin, "_cfg", return_value={"admin_profiles":["default"]}):
            self.assertIn("não autorizado", plugin._project_create("pixel-x", "pedro"))

    def test_route_rejects_profile_not_authorized_by_project(self):
        plugin = load_plugin()
        manifest = {"projects": [{"slug":"pixel-x", "profiles":["david"], "routes":[{"platform":"telegram","chat_id":"-1001","thread_id":"7","profile":"pedro"}]}]}
        with patch.object(plugin, "_load_manifest", return_value=manifest):
            self.assertIsNone(plugin._route(event("hello", profile="pedro")))

    def test_routed_channel_cannot_switch_project(self):
        plugin = load_plugin()
        manifest = {"projects": [{"slug":"pixel-x", "profiles":["pedro"], "routes":[{"platform":"telegram","chat_id":"-1001","thread_id":"7","profile":"pedro"}]}]}
        with patch.object(plugin, "_load_manifest", return_value=manifest):
            result = plugin._pre_gateway_dispatch(event("/project use other"))
        self.assertIn("seleção manual está bloqueada", result["text"])

    def test_manual_selection_persists_per_profile_and_pre_llm_injects_it(self):
        plugin = load_plugin()
        manifest = {"projects": [{"slug":"pixel-x", "name":"Pixel X", "profiles":["pedro"]}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = root / "projects/pixel-x"; project.mkdir(parents=True)
            for name in ("PROJECT.md", "CONTEXT.md", "AGENTS.md"): (project / name).write_text("ok")
            with patch.object(plugin, "_cfg", return_value={"workspace_root":str(root)}), patch.object(plugin, "_load_manifest", return_value=manifest):
                result = plugin._pre_gateway_dispatch(event("/project use pixel-x", platform=""))
                with patch.object(plugin, "_active_profile", return_value="pedro"):
                    injected = plugin._pre_llm_call(session_id="x")
        self.assertIn("Slug: pixel-x", result["text"])
        self.assertIn("Slug: pixel-x", injected["context"])

    def test_invalid_manifest_slug_cannot_escape_projects_root(self):
        plugin = load_plugin()
        manifest = {"projects": [{"slug":"../../outside", "name":"Outside", "profiles":["pedro"]}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(plugin, "_cfg", return_value={"workspace_root":str(root)}), patch.object(plugin, "_load_manifest", return_value=manifest):
                context = plugin._context(manifest["projects"][0], "pedro", "manual")
        self.assertIn("CONTEXTO BLOQUEADO", context)

    def test_gateway_pre_llm_does_not_append_manual_context(self):
        plugin = load_plugin()
        self.assertIsNone(plugin._pre_llm_call(session_id="x", platform="telegram"))

    def test_unknown_gateway_is_closed_when_enabled(self):
        plugin = load_plugin()
        with patch.object(plugin, "_cfg", return_value={"fail_closed_gateway":True}), patch.object(plugin, "_load_manifest", return_value={"projects":[]}):
            result = plugin._pre_gateway_dispatch(event("hello", chat_id="-999"))
        self.assertIn("não está provisionado", result["text"])


if __name__ == "__main__": unittest.main()
