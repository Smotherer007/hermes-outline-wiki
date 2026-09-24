"""outline_profile -- List, switch or delete configured workspaces."""

from __future__ import annotations

from .. import config as cfg
from ..formatters import format_profile_status
from ..models import ToolInputError
from ._base import opt_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_profile",
    "List configured Outline workspace profiles, switch the active one, or delete a profile. "
    "Without arguments it lists all profiles.",
    {
        "action": {"type": "string", "description": "One of: list, use, delete. Defaults to list."},
        "name": {"type": "string", "description": "Profile name for 'use' and 'delete'."},
    },
)


@tool_handler
def handle(args: dict) -> str:
    action = (opt_str(args, "action") or "list").lower()
    name = opt_str(args, "name")

    if action == "list":
        profiles = cfg.get_profiles()
        env_profiles = [n for n in profiles if cfg.is_env_profile(n)]
        return result(
            format_profile_status(profiles, cfg.get_active_profile(), env_profiles),
            profiles=list(profiles),
            activeProfile=cfg.get_active_profile(),
        )

    if action not in ("use", "delete"):
        raise ToolInputError(f'Unknown action "{args.get("action")}". Use one of: list, use, delete.')
    if not name:
        raise ToolInputError(f'The "{action}" action requires a profile name.')

    if action == "use":
        cfg.set_active_profile(name)
        return result(f'Active Outline profile is now "{name}".', activeProfile=name)

    removed = cfg.delete_profile(name)
    active = cfg.get_active_profile()
    if removed:
        now = f'"{active}"' if active else "unset"
        text = f'Profile "{name}" deleted. Active profile is now {now}.'
    else:
        text = f'No profile named "{name}".'
    return result(text, deleted=removed, activeProfile=active)
