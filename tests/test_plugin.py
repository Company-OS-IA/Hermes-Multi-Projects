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


def event(text, profile="operator", platform="telegram", chat_id="-1001", thread_id="7"):
    source = SimpleNamespace(
        profile=profile,
        platform=platform,
        chat_id=chat_id,
        thread_id=thread_id,
    )
    return SimpleNamespace(text=text, source=source)


class MemoryState:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class FakeContext:
    def __init__(self, profile_name="default", settings=None):
        self.profile_name = profile_name
        self.settings = settings or {}
        self.state = MemoryState()
        self.hooks = {}
        self.commands = {}
        self.tools = {}
        self.skills = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, handler):
        self.hooks[name] = handler

    def register_command(self, name, handler, description=""):
        self.commands[name] = (handler, description)

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs

    def register_skill(self, name, path):
        self.skills[name] = Path(path)


class MultiProjectsTests(unittest.TestCase):
    def test_gateway_route_injects_only_its_project_context(self):
        plugin = load_plugin()
        manifest = {
            "projects": [{
                "slug": "project-alpha",
                "name": "Project Alpha",
                "profiles": ["operator"],
                "routes": [{
                    "platform": "telegram",
                    "chat_id": "-1001",
                    "thread_id": "7",
                    "profile": "operator",
                }],
            }]
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "projects/project-alpha"
            project.mkdir(parents=True)
            for name in ("PROJECT.md", "CONTEXT.md"):
                (project / name).write_text("ok", encoding="utf-8")
            with patch.object(plugin, "_cfg", return_value={"workspace_root": str(root)}), patch.object(
                plugin, "_load_manifest", return_value=manifest
            ):
                result = plugin._pre_gateway_dispatch(event("review campaign"))
        self.assertIn("Slug: project-alpha", result["text"])
        self.assertIn("Mensagem do usuário:\nreview campaign", result["text"])

    def test_gateway_route_normalizes_platform_enum(self):
        plugin = load_plugin()

        class PlatformLike:
            value = "telegram"

        manifest = {
            "projects": [{
                "slug": "project-alpha",
                "profiles": ["operator"],
                "routes": [{
                    "platform": "telegram",
                    "chat_id": "-1001",
                    "thread_id": "7",
                    "profile": "operator",
                }],
            }]
        }
        with patch.object(plugin, "_load_manifest", return_value=manifest):
            routed = plugin._route(event("hello", platform=PlatformLike()))
        self.assertEqual("project-alpha", routed[0]["slug"])

    def test_empty_profile_allowlist_denies_access(self):
        plugin = load_plugin()
        self.assertFalse(plugin._allowed({"profiles": []}, "operator"))

    def test_empty_profile_allowlist_blocks_manual_selection(self):
        plugin = load_plugin()
        ctx = FakeContext(profile_name="operator")
        plugin.register(ctx)
        with patch.object(
            plugin,
            "_load_manifest",
            return_value={"projects": [{"slug": "project-alpha", "profiles": []}]},
        ):
            result = plugin._cli_project("use project-alpha")
        self.assertIn("não está habilitado", result)
        self.assertIsNone(ctx.state.get("selection:operator"))

    def test_project_init_creates_empty_manifest(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(plugin, "_cfg", return_value={"workspace_root": str(root)}):
                result = plugin._project_init("default")
                manifest = plugin._load_manifest()
            self.assertIn("inicializada", result)
            self.assertEqual({"version": 1, "projects": []}, manifest)

    def test_admin_can_create_and_register_project(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = {"workspace_root": str(root), "admin_profiles": ["default"]}
            with patch.object(plugin, "_cfg", return_value=settings):
                plugin._project_init("default")
                result = plugin._project_create("Project Alpha", "default")
                manifest = plugin._load_manifest()
            self.assertIn("project-alpha", result)
            self.assertEqual("project-alpha", manifest["projects"][0]["slug"])
            self.assertEqual([], manifest["projects"][0]["profiles"])
            self.assertTrue((root / "projects/project-alpha/PROJECT.md").is_file())

    def test_admin_can_add_profile_and_route(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = {"workspace_root": str(root), "admin_profiles": ["default"]}
            with patch.object(plugin, "_cfg", return_value=settings):
                plugin._project_init("default")
                plugin._project_create("project-alpha", "default")
                plugin._project_add_profile("project-alpha operator", "default")
                result = plugin._project_add_route(
                    "project-alpha telegram -1001 7 operator", "default"
                )
                manifest = plugin._load_manifest()
            self.assertIn("Rota adicionada", result)
            self.assertEqual("operator", manifest["projects"][0]["profiles"][0])
            self.assertEqual("-1001", manifest["projects"][0]["routes"][0]["chat_id"])

    def test_route_requires_explicit_profile_authorization(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = {"workspace_root": str(root), "admin_profiles": ["default"]}
            with patch.object(plugin, "_cfg", return_value=settings):
                plugin._project_init("default")
                plugin._project_create("project-alpha", "default")
                result = plugin._project_add_route(
                    "project-alpha telegram -1001 7 operator", "default"
                )
            self.assertIn("não autorizado", result)

    def test_non_admin_cannot_create_project(self):
        plugin = load_plugin()
        with patch.object(plugin, "_cfg", return_value={"admin_profiles": ["default"]}):
            self.assertIn("não autorizado", plugin._project_create("project-alpha", "operator"))

    def test_routed_channel_cannot_switch_project(self):
        plugin = load_plugin()
        manifest = {
            "projects": [{
                "slug": "project-alpha",
                "profiles": ["operator"],
                "routes": [{
                    "platform": "telegram",
                    "chat_id": "-1001",
                    "thread_id": "7",
                    "profile": "operator",
                }],
            }]
        }
        with patch.object(plugin, "_load_manifest", return_value=manifest):
            plugin._pre_gateway_dispatch(event("/project use project-beta"))
            result = plugin._cli_project("use project-beta")
        self.assertIn("seleção manual está bloqueada", result)

    def test_active_profile_comes_from_plugin_context(self):
        plugin = load_plugin()
        ctx = FakeContext(profile_name="operator")
        plugin.register(ctx)
        self.assertEqual("operator", plugin._active_profile())
        self.assertEqual("operator", plugin._command_profile())
        self.assertEqual("operator", json.loads(plugin.project_context({}))["profile"])

    def test_manual_selection_uses_hermes_state(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ctx = FakeContext(
                profile_name="operator",
                settings={"workspace_root": str(root), "admin_profiles": ["default"]},
            )
            plugin.register(ctx)
            manifest = {"projects": [{"slug": "project-alpha", "profiles": ["operator"]}]}
            project = root / "projects/project-alpha"
            project.mkdir(parents=True)
            for name in ("PROJECT.md", "CONTEXT.md"):
                (project / name).write_text("ok", encoding="utf-8")
            with patch.object(plugin, "_load_manifest", return_value=manifest):
                result = plugin._cli_project("use project-alpha")
                tool_result = json.loads(plugin.project_context({}))
            self.assertIn("Slug: project-alpha", result)
            self.assertEqual("project-alpha", ctx.state.get("selection:operator"))
            self.assertEqual("project-alpha", tool_result["project"])

    def test_legacy_selection_is_migrated_to_hermes_state(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".hermes-project-context.json").write_text(
                json.dumps({"operator": "project-alpha"}), encoding="utf-8"
            )
            ctx = FakeContext(profile_name="operator", settings={"workspace_root": str(root)})
            plugin.register(ctx)
            with patch.object(
                plugin,
                "_load_manifest",
                return_value={"projects": [{"slug": "project-alpha", "profiles": ["operator"]}]},
            ):
                selected = plugin._selected("operator")
            self.assertEqual("project-alpha", selected["slug"])
            self.assertEqual("project-alpha", ctx.state.get("selection:operator"))

    def test_project_context_returns_json_error(self):
        plugin = load_plugin()
        with patch.object(plugin, "_selected", side_effect=ValueError("bad manifest")):
            result = json.loads(plugin.project_context({}))
        self.assertFalse(result["success"])
        self.assertEqual("bad manifest", result["error"])

    def test_invalid_manifest_slug_cannot_escape_projects_root(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(plugin, "_cfg", return_value={"workspace_root": temp}):
                context = plugin._context(
                    {"slug": "../../outside", "profiles": ["operator"]},
                    "operator",
                    "manual",
                )
        self.assertIn("CONTEXTO BLOQUEADO", context)

    def test_project_symlink_cannot_escape_projects_root(self):
        plugin = load_plugin()
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            (root / "projects").mkdir()
            (root / "projects/project-alpha").symlink_to(Path(outside), target_is_directory=True)
            with patch.object(plugin, "_cfg", return_value={"workspace_root": str(root)}):
                with self.assertRaisesRegex(ValueError, "escapes"):
                    plugin._project_root("project-alpha")

    def test_unrouted_gateway_uses_company_context(self):
        plugin = load_plugin()
        with patch.object(plugin, "_load_manifest", return_value={"projects": []}):
            result = plugin._pre_gateway_dispatch(event("hello", chat_id="-999"))
        self.assertIn("Escopo: company", result["text"])

    def test_native_gateway_command_passes_through(self):
        plugin = load_plugin()
        with patch.object(plugin, "_load_manifest", return_value={"projects": []}):
            self.assertIsNone(plugin._pre_gateway_dispatch(event("/restart", chat_id="-999")))

    def test_delete_requires_explicit_confirmation(self):
        plugin = load_plugin()
        with patch.object(plugin, "_cfg", return_value={"admin_profiles": ["default"]}):
            self.assertIn("--confirm", plugin._project_delete("project-alpha", "default"))

    def test_registration_matches_manifest_surfaces(self):
        plugin = load_plugin()
        ctx = FakeContext()
        plugin.register(ctx)
        self.assertEqual({"pre_gateway_dispatch", "pre_llm_call"}, set(ctx.hooks))
        self.assertEqual({"project", "projects"}, set(ctx.commands))
        self.assertEqual({"project_context"}, set(ctx.tools))
        self.assertEqual({"project-context"}, set(ctx.skills))
        self.assertTrue(ctx.skills["project-context"].is_file())
        self.assertEqual("hermes-multi-projects", ctx.tools["project_context"]["toolset"])


if __name__ == "__main__":
    unittest.main()
