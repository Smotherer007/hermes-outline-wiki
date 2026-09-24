"""outline_update -- Change an existing document.

``replace`` overwrites the body, so append/prepend exist to add to a page
(changelog, decision log, FAQ) without having to read and re-send it.
"""

from __future__ import annotations

import re

from .. import config as cfg
from ..client import get_document, update_document
from ..formatters import format_document_saved
from ..models import ToolInputError
from ._base import PROFILE_PROPERTY, opt_bool, opt_str, req_str, result, schema, tool_handler

VALID_MODES = {"replace", "append", "prepend"}

SCHEMA = schema(
    "outline_update",
    "Update an existing document: replace the body, append or prepend a section, rename it, or "
    "publish a draft. Read the document first when replacing, so nothing is lost.",
    {
        "id": {"type": "string", "description": "Document id or urlId."},
        "text": {"type": "string", "description": "Markdown to write, append or prepend."},
        "mode": {
            "type": "string",
            "enum": ["replace", "append", "prepend"],
            "description": "How to apply text: replace (default, overwrites the whole body), append (add "
            "at the end), prepend (add at the top).",
            "default": "replace",
        },
        "title": {"type": "string", "description": "New title."},
        "icon": {"type": "string", "description": "New emoji or icon."},
        "publish": {"type": "boolean", "description": "Publish a draft document so others can see it."},
        "profile": PROFILE_PROPERTY,
    },
    ["id"],
)


@tool_handler
def handle(args: dict) -> str:
    doc_id = req_str(args, "id")
    mode = (opt_str(args, "mode") or "replace").lower()
    if mode not in VALID_MODES:
        raise ToolInputError(f'Invalid mode "{args.get("mode")}". Use replace, append or prepend.')

    text = opt_str(args, "text")
    title = opt_str(args, "title")
    icon = opt_str(args, "icon")
    publish = opt_bool(args, "publish")
    if text is None and title is None and icon is None and publish is None:
        raise ToolInputError("Nothing to update: pass at least one of text, title, icon or publish.")

    config = cfg.resolve_config(opt_str(args, "profile"))

    if text is not None and mode != "replace":
        existing = get_document(config, doc_id).text or ""
        if mode == "append":
            head = re.sub(r"\s*$", "", existing)
            text = f"{head}\n\n{text}\n"
        else:
            tail = re.sub(r"^\s*", "", existing)
            text = f"{text}\n\n{tail}"

    doc = update_document(config, doc_id, title=title, text=text, icon=icon, publish=publish)
    return result(
        f"{format_document_saved(doc, 'updated')}\nMode: {mode}",
        id=doc.id,
        title=doc.title,
        url=doc.url,
        mode=mode,
        length=len(doc.text),
    )
