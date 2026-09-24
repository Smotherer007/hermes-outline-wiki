"""Hermes Outline Wiki plugin.

Gives Hermes read and write access to an Outline wiki
(https://www.getoutline.com) through Outline's REST API. Port of the pi
extension pi-outline-wiki: same tools, same parameters, same config file
format, same skills.

Tools:
  outline_setup        Configure workspace URL and API key
  outline_status       Show configuration and verify the connection
  outline_profile      List, switch or delete workspace profiles
  outline_collections  List collections with their ids
  outline_structure    Show the nested document tree of a collection
  outline_search       Full-text search, one or all workspaces
  outline_list         Browse documents, children or drafts
  outline_read         Read a document's markdown body
  outline_create       Create a new document
  outline_update       Replace, append to or prepend to a document
  outline_move         Re-file a document into another collection or parent
  outline_archive      Archive, restore or unpublish a document
  outline_delete       Trash or permanently delete a document
  outline_comments     Read comment threads on a document
  outline_comment      Post a comment or reply
  outline_export       Save documents to local markdown files

Layout:
  models.py      plain frozen dataclasses, no behaviour
  client.py      all HTTP (stdlib only), mapping API payloads to models
  formatters.py  pure functions: models -> display strings
  config.py      profile store, persisted with 0600 permissions
  tools/         one module per tool (SCHEMA + handle)
  safety.py      safety level for write tools (pre_tool_call hook)
  commands.py    /wiki and /wiki-capture
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from . import config as cfg
from .commands import make_capture_command, make_wiki_command
from .safety import make_pre_tool_call_hook
from .tools import TOOL_MODULES, TOOLSET

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).resolve().parent

SKILLS = {
    "outline-wiki": "Research the Outline wiki before answering questions about internal systems, "
    "conventions, decisions, runbooks or onboarding.",
    "outline-doc-writing": "Write and edit Outline pages so they are findable, correct and safe to change.",
    "outline-knowledge-capture": "Turn what was worked out in a session into a durable Outline page.",
}


def _prompt_section(_session: Mapping[str, Any]) -> str:
    """Short, frozen-per-session pointer to the skills and the configured wikis.

    Plugin skills are not listed in Hermes' skill index, so without this the
    model would never learn that they exist. No keys, no URLs beyond the host.
    """
    lines = [
        "Outline wiki tools (outline_*) are available. Before using them for more than a quick lookup, "
        "load the matching skill with skill_view:",
    ]
    lines += [f"- outline-wiki:{name} -- {text}" for name, text in SKILLS.items()]
    try:
        profiles = cfg.get_profiles()
        active = cfg.get_active_profile()
    except Exception:
        profiles, active = {}, None
    if profiles:
        lines.append("Configured Outline workspaces (profile parameter):")
        for name, config in profiles.items():
            marker = " (active)" if name == active else ""
            description = f" -- {config.description}" if config.description else ""
            lines.append(f"- {name}{marker}{description}")
    else:
        lines.append("No Outline workspace is configured yet; outline_setup adds one.")
    return "\n".join(lines)


def _frontmatter_description(path: Path) -> str:
    """The single-line ``description:`` of a SKILL.md, without needing a YAML parser."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not content.startswith("---\n"):
        return ""
    end = content.find("\n---", 4)
    for line in content[4:end].splitlines():
        if line.startswith("description:"):
            return line[len("description:"):].strip().strip("\"'")
    return ""


def register(ctx) -> None:
    """Called once by the Hermes plugin loader."""
    cfg.load_config()

    for module in TOOL_MODULES:
        ctx.register_tool(
            name=module.SCHEMA["name"],
            toolset=TOOLSET,
            schema=module.SCHEMA,
            handler=module.handle,
            description=module.SCHEMA["description"],
        )

    for name, short in SKILLS.items():
        skill_md = _PLUGIN_DIR / "skills" / name / "SKILL.md"
        if skill_md.exists():
            # skills_list shows this text; the full frontmatter description
            # carries the trigger phrases, so prefer it over the short one.
            ctx.register_skill(name, skill_md, description=_frontmatter_description(skill_md) or short)

    def safety_level() -> Any:
        try:
            return ctx.get_config("safety_level", default="open")
        except Exception:
            return "open"

    ctx.register_hook("pre_tool_call", make_pre_tool_call_hook(safety_level))

    ctx.register_command(
        "wiki",
        handler=make_wiki_command(ctx),
        description="Search the Outline wiki and summarise what it says",
        args_hint="<what you are looking for>",
    )
    ctx.register_command(
        "wiki-capture",
        handler=make_capture_command(ctx),
        description="Write what we worked out in this session into the Outline wiki",
        args_hint="[focus]",
    )

    register_section = getattr(ctx, "register_system_prompt_section", None)
    if callable(register_section):
        try:
            register_section("outline-wiki.overview", _prompt_section)
        except Exception:  # older Hermes: the skills are still reachable via skills_list
            logger.debug("outline-wiki: could not register the system prompt section", exc_info=True)
