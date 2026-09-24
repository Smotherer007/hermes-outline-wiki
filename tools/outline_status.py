"""outline_status -- Show configuration status and verify the connection."""

from __future__ import annotations

from .. import config as cfg
from ..client import get_workspace_info
from ..formatters import format_profile_status, format_workspace_info
from ._base import opt_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_status",
    "Show which Outline workspaces are configured and verify that the active API key still works.",
    {"profile": {"type": "string", "description": "Profile to verify. Defaults to the active one."}},
)


@tool_handler
def handle(args: dict) -> str:
    profiles = cfg.get_profiles()
    active = cfg.get_active_profile()
    env_profiles = [name for name in profiles if cfg.is_env_profile(name)]
    overview = format_profile_status(profiles, active, env_profiles)

    if not profiles:
        return result(overview, configured=False, profileCount=0, activeProfile=None)

    reachable = False
    try:
        info = get_workspace_info(cfg.resolve_config(opt_str(args, "profile")))
        connection = format_workspace_info(info)
        reachable = True
    except Exception as exc:
        connection = f"Connection test failed: {exc}"

    insecure = [name for name, config in profiles.items() if config.insecure_tls]
    warning = (
        f"\n\nWarning: TLS certificate validation is disabled for profile(s): {', '.join(insecure)}."
        if insecure
        else ""
    )
    return result(
        f"{overview}\n\n{connection}{warning}",
        configured=True,
        profileCount=len(profiles),
        activeProfile=active,
        profiles=list(profiles),
        reachable=reachable,
    )

