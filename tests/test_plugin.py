"""Registration, safety hook, slash commands, manifest and skills."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import ROOT, plugin, sub

safety = sub("safety")
commands = sub("commands")
tools = sub("tools")
config = sub("config")
models = sub("models")


class FakeCtx:
    def __init__(self, settings=None, inject_result=True):
        self.tools, self.skills, self.hooks, self.commands, self.sections = {}, {}, {}, {}, {}
        self.skill_descriptions = {}
        self.settings = settings or {}
        self.injected = []
        self.inject_result = inject_result

    def register_tool(self, name, toolset, schema, handler, **kw):
        self.tools[name] = (toolset, schema, handler)

    def register_skill(self, name, path, description=""):
        assert Path(path).exists()
        self.skills[name] = path
        self.skill_descriptions[name] = description

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands[name] = handler

    def register_system_prompt_section(self, id, content, **kw):
        self.sections[id] = content

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def inject_message(self, content, role="user", *, session_key=None):
        self.injected.append((content, session_key))
        return self.inject_result


@pytest.fixture
def ctx():
    c = FakeCtx()
    plugin.register(c)
    return c


def manifest():
    return yaml.safe_load((ROOT / "plugin.yaml").read_text())


class TestRegistration:
    def test_registers_every_tool_the_manifest_declares(self, ctx):
        assert sorted(ctx.tools) == sorted(manifest()["provides_tools"])
        assert {toolset for toolset, _, _ in ctx.tools.values()} == {"outline"}

    def test_schema_names_match_registration(self, ctx):
        for name, (_, schema, _) in ctx.tools.items():
            assert schema["name"] == name
            assert schema["parameters"]["type"] == "object"
            for required in schema["parameters"]["required"]:
                assert required in schema["parameters"]["properties"]

    def test_registers_hooks_skills_commands_and_prompt_section(self, ctx):
        assert list(ctx.hooks) == manifest()["provides_hooks"]
        assert sorted(ctx.skills) == ["outline-doc-writing", "outline-knowledge-capture", "outline-wiki"]
        assert sorted(ctx.commands) == ["wiki", "wiki-capture"]
        assert "outline-wiki.overview" in ctx.sections

    def test_prompt_section_lists_workspaces_without_secrets(self, ctx):
        config.save_profile("firma", models.OutlineConfig(url="https://w", api_key="ol_api_SECRET", description="internal"))
        text = ctx.sections["outline-wiki.overview"]({})
        assert "outline-wiki:outline-knowledge-capture" in text
        assert "- firma (active) -- internal" in text
        assert "SECRET" not in text

    def test_works_without_the_optional_prompt_section_api(self):
        class OlderHermesCtx(FakeCtx):
            register_system_prompt_section = None

        c = OlderHermesCtx()
        plugin.register(c)
        assert c.tools and not c.sections


class TestSafety:
    def hook(self, level):
        return safety.make_pre_tool_call_hook(lambda: level)

    def test_open_lets_everything_through(self):
        assert self.hook("open")(tool_name="outline_delete", args={"id": "d"}) is None

    def test_readonly_blocks_writes_but_not_reads(self):
        hook = self.hook("readonly")
        assert hook(tool_name="outline_create", args={})["action"] == "block"
        assert hook(tool_name="outline_search", args={}) is None
        assert hook(tool_name="outline_export", args={}) is None

    def test_confirm_escalates_to_the_approval_gate(self):
        directive = self.hook("confirm")(tool_name="outline_delete", args={"id": "d1", "permanent": True, "profile": "kunde"})
        assert directive["action"] == "approve"
        assert directive["message"] == "PERMANENTLY delete Outline document d1 in workspace kunde"

    def test_every_wiki_write_tool_is_covered(self):
        writes = {"outline_create", "outline_update", "outline_move", "outline_archive", "outline_delete", "outline_comment"}
        assert tools.WIKI_WRITE_TOOLS == writes

    def test_unknown_level_fails_closed_to_confirm(self):
        assert self.hook("yolo")(tool_name="outline_update", args={"id": "d"})["action"] == "approve"

    def test_level_is_read_at_call_time(self):
        c = FakeCtx(settings={"safety_level": "readonly"})
        plugin.register(c)
        assert c.hooks["pre_tool_call"](tool_name="outline_create", args={})["action"] == "block"
        c.settings["safety_level"] = "open"
        assert c.hooks["pre_tool_call"](tool_name="outline_create", args={}) is None


class TestCommands:
    def test_wiki_needs_configuration(self, ctx):
        assert "not configured" in ctx.commands["wiki"]("postgres")

    def test_wiki_needs_a_query(self, ctx):
        config.save_profile("w", models.OutlineConfig(url="https://w", api_key="k"))
        assert ctx.commands["wiki"]("  ").startswith("Usage:")

    def test_wiki_injects_the_research_prompt(self, ctx, monkeypatch):
        config.save_profile("w", models.OutlineConfig(url="https://w", api_key="k"))
        monkeypatch.setenv("HERMES_SESSION_KEY", "sess-1")
        assert "Searching the wiki" in ctx.commands["wiki"]("postgres failover")
        prompt, key = ctx.injected[0]
        assert 'Search our Outline wiki for "postgres failover".' in prompt
        assert key == "sess-1"

    def test_falls_back_to_returning_the_prompt(self, monkeypatch):
        c = FakeCtx(inject_result=False)
        plugin.register(c)
        config.save_profile("w", models.OutlineConfig(url="https://w", api_key="k"))
        out = c.commands["wiki-capture"]("the pooling decision")
        assert "allow_gateway_injection" in out
        assert "Focus on: the pooling decision." in out


class TestManifestAndSkills:
    def test_manifest_basics(self):
        data = manifest()
        assert data["name"] == "outline-wiki"
        assert data["config_schema"]["safety_level"]["choices"] == list(safety.VALID_LEVELS)

    @pytest.mark.parametrize("skill", ["outline-wiki", "outline-doc-writing", "outline-knowledge-capture"])
    def test_skill_frontmatter_is_valid_yaml(self, skill):
        # Parsed for real: an unquoted value containing ": " is a nested
        # mapping to YAML, which is exactly how a broken skill shipped once.
        content = (ROOT / "skills" / skill / "SKILL.md").read_text()
        assert content.startswith("---\n")
        end = content.index("\n---", 4)
        front = yaml.safe_load(content[4:end])
        assert front["name"] == skill
        assert isinstance(front["description"], str) and 0 < len(front["description"]) <= 1024
        assert front["metadata"]["hermes"]["requires_toolsets"] == ["outline"]

    def test_skills_only_reference_tools_that_exist(self):
        names = set(manifest()["provides_tools"])
        for path in (ROOT / "skills").glob("*/SKILL.md"):
            content = path.read_text()
            end = content.index("\n---", 4)
            allowed = yaml.safe_load(content[4:end]).get("allowed-tools", "")
            for tool in (t.strip() for t in allowed.split(",")):
                assert tool in names, f"{path.parent.name} allows unknown tool {tool}"


def test_skills_are_registered_with_their_full_description(ctx):
    # the frontmatter carries the trigger phrases skills_list should show
    assert ctx.skill_descriptions["outline-wiki"].startswith("Research the team's Outline wiki")
    assert "write this up" in ctx.skill_descriptions["outline-knowledge-capture"]
