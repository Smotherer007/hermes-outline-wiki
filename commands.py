"""Slash commands ``/wiki`` and ``/wiki-capture``.

pi's commands queue a prompt for the agent. The Hermes equivalent is
``ctx.inject_message``: in the CLI it always works; in the gateway (Teams,
Telegram, ...) Hermes only allows it when the operator sets
``plugins.entries.outline-wiki.allow_gateway_injection: true``. Without that,
the command answers with the prompt so the user can send it as a message.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from . import config as cfg

NOT_CONFIGURED = (
    "Outline not configured. Use the outline_setup tool with your workspace URL and an API key, "
    "or set OUTLINE_URL and OUTLINE_API_KEY."
)


def wiki_prompt(query: str) -> str:
    return " ".join([
        f'Search our Outline wiki for "{query}".',
        "If outline_profile shows more than one workspace, pick the one whose description fits, or "
        "search them all with outline_search allProfiles: true.",
        "Then read the most relevant document(s) with outline_read, passing the same profile the hit "
        "came from, and summarise what the wiki says.",
        "Cite each document by title and id (and workspace, if several are in play). Say so plainly if "
        "the wiki has nothing on it.",
    ])


def capture_prompt(hint: str) -> str:
    parts = [
        "Capture the durable knowledge from this session in our Outline wiki.",
        f"Focus on: {hint}." if hint else "",
        "Load the skill outline-wiki:outline-knowledge-capture first.",
        "If outline_profile shows more than one workspace, decide which one this belongs in first and "
        "pass profile explicitly on every call; ask me if it is not obvious.",
        "Then use outline_search to check whether a page on this already exists.",
        "If it does, extend it with outline_update (mode append) instead of creating a duplicate.",
        "If it does not, use outline_collections to pick the right collection and create the page with "
        "outline_create.",
        "Write what a colleague would need in six months: the decision, why, and what was ruled out -- "
        "not a transcript.",
        "Show me the workspace, page title and URL when you are done.",
    ]
    return " ".join(part for part in parts if part)


def _session_key() -> str:
    try:  # bound by the gateway around plugin command dispatch
        from gateway.session_context import get_session_env  # type: ignore

        return get_session_env("HERMES_SESSION_KEY", "")
    except Exception:
        return os.environ.get("HERMES_SESSION_KEY", "")


def _deliver(ctx: Any, prompt: str, started: str) -> str:
    try:
        key = _session_key() or None
        if ctx.inject_message(prompt, session_key=key):
            return started
    except Exception:
        pass
    return (
        "I could not start this automatically here (the gateway needs "
        "plugins.entries.outline-wiki.allow_gateway_injection: true). Send this as a message instead:\n\n"
        + prompt
    )


def make_wiki_command(ctx: Any) -> Callable[[str], str]:
    def wiki(raw_args: str = "") -> str:
        if cfg.get_config() is None:
            return NOT_CONFIGURED
        query = (raw_args or "").strip()
        if not query:
            return "Usage: /wiki <what you are looking for>"
        return _deliver(ctx, wiki_prompt(query), f'Searching the wiki for "{query}"...')

    return wiki


def make_capture_command(ctx: Any) -> Callable[[str], str]:
    def wiki_capture(raw_args: str = "") -> str:
        if cfg.get_config() is None:
            return NOT_CONFIGURED
        return _deliver(
            ctx, capture_prompt((raw_args or "").strip()), "Asking the agent to write this up in the wiki..."
        )

    return wiki_capture
