"""outline_setup -- Configure an Outline workspace.

Stores a named profile. The first profile becomes active automatically. Use
outline_status to see all profiles and outline_profile to switch between them.
"""

from __future__ import annotations

from .. import config as cfg
from ..client import get_workspace_info
from ..formatters import format_workspace_info
from ..models import OutlineConfig
from ._base import opt_bool, opt_str, req_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_setup",
    "Configure an Outline workspace (URL + API key). Call this first before using any other outline "
    "tool. The API key is created in Outline under Settings -> API & Apps and starts with 'ol_api_'. "
    "Credentials are stored in $HERMES_HOME/outline-config.json (readable only by you). Works with "
    "both cloud (yourteam.getoutline.com) and self-hosted installations.",
    {
        "name": {
            "type": "string",
            "description": "Profile name, e.g. 'work', 'company-wiki'. Use a short, memorable name.",
        },
        "url": {
            "type": "string",
            "description": "Workspace URL, e.g. https://acme.getoutline.com or https://wiki.example.com. "
            "A trailing /api or /mcp is stripped automatically.",
        },
        "apiKey": {
            "type": "string",
            "description": "Outline API key from Settings -> API & Apps (starts with ol_api_).",
        },
        "description": {
            "type": "string",
            "description": "One line on what this wiki contains, e.g. 'internal engineering wiki' or "
            "'ACME client project docs'. Strongly recommended when several workspaces are configured: "
            "it is how the agent decides which wiki to search.",
        },
        "insecureTls": {
            "type": "boolean",
            "description": "Skip TLS certificate validation. Only for self-hosted instances with a "
            "self-signed certificate; applies to this profile's requests only.",
        },
    },
    ["name", "url", "apiKey"],
)


@tool_handler
def handle(args: dict) -> str:
    name = req_str(args, "name").strip()
    description = opt_str(args, "description")
    config = OutlineConfig(
        url=cfg.normalize_base_url(req_str(args, "url")),
        api_key=req_str(args, "apiKey").strip(),
        description=description.strip() if description and description.strip() else None,
        insecure_tls=bool(opt_bool(args, "insecureTls")),
    )
    cfg.save_profile(name, config)

    # Verify immediately: a typo in the URL or key is much cheaper to find
    # here than inside the first real document call.
    verified = False
    try:
        info = get_workspace_info(cfg.resolve_config(name))
        verification = format_workspace_info(info)
        verified = True
    except Exception as exc:
        verification = f"Saved, but the connection test failed: {exc}"

    active = cfg.get_active_profile()
    state = "saved and set as active" if active == name else f'saved (active profile stays "{active}")'
    return result(
        f'Outline profile "{name}" {state} ({config.url}).\n\n{verification}',
        profileName=name,
        url=config.url,
        verified=verified,
    )
