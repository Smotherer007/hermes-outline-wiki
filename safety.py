"""Safety level for write tools, enforced through Hermes' ``pre_tool_call`` hook.

``plugins.entries.outline-wiki.settings.safety_level`` in ``config.yaml``
(or the settings form in the Desktop app):

* ``open`` (default) -- write tools run directly, as in pi-outline-wiki.
* ``confirm`` -- every write goes through Hermes' human-approval gate. In the
  gateway that is the normal approval prompt in the chat; denial or timeout
  blocks the call.
* ``readonly`` -- write tools are blocked outright.

Reads and the local-only tools (setup, profile, export) are never affected.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .tools import WIKI_WRITE_TOOLS

VALID_LEVELS = ("open", "confirm", "readonly")


def normalize_level(value: Any) -> str:
    level = str(value or "open").strip().lower()
    # Unknown values fail closed to the stricter behaviour that still lets people work.
    return level if level in VALID_LEVELS else "confirm"


def make_pre_tool_call_hook(get_level: Callable[[], Any]) -> Callable[..., Optional[dict]]:
    def pre_tool_call(tool_name: str = "", args: Optional[dict] = None, **_kwargs: Any) -> Optional[dict]:
        if tool_name not in WIKI_WRITE_TOOLS:
            return None
        level = normalize_level(get_level())
        if level == "open":
            return None
        if level == "readonly":
            return {
                "action": "block",
                "message": f"{tool_name} is blocked: the Outline plugin is set to readonly "
                "(plugins.entries.outline-wiki.settings.safety_level).",
            }
        return {
            "action": "approve",
            "message": _describe(tool_name, args or {}),
            "rule_key": f"outline-wiki:{tool_name}",
        }

    return pre_tool_call


def _describe(tool_name: str, args: dict) -> str:
    """One line for the approval prompt, so the human sees what would change."""
    profile = f" in workspace {args['profile']}" if args.get("profile") else ""
    if tool_name == "outline_create":
        return f'Create Outline page "{args.get("title", "?")}"{profile}'
    if tool_name == "outline_update":
        mode = args.get("mode") or "replace"
        return f"Update Outline document {args.get('id', '?')} (mode {mode}){profile}"
    if tool_name == "outline_move":
        return f"Move Outline document {args.get('id', '?')}{profile}"
    if tool_name == "outline_archive":
        return f"{str(args.get('action') or 'archive').capitalize()} Outline document {args.get('id', '?')}{profile}"
    if tool_name == "outline_delete":
        kind = "PERMANENTLY delete" if args.get("permanent") in (True, "true", "True") else "Trash"
        return f"{kind} Outline document {args.get('id', '?')}{profile}"
    if tool_name == "outline_comment":
        return f"Comment on Outline document {args.get('documentId', '?')}{profile}"
    return f"Run {tool_name}{profile}"
