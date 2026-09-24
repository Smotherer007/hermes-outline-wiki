"""outline_archive -- Archive, restore or unpublish a document.

Archiving is the reversible way to retire a wiki page: it disappears from the
collection but stays searchable in the archive.
"""

from __future__ import annotations

from .. import config as cfg
from ..client import document_lifecycle
from ..models import ToolInputError
from ._base import PROFILE_PROPERTY, opt_str, req_str, result, schema, tool_handler

ACTIONS = {"archive": "archive", "restore": "restore", "unarchive": "restore", "unpublish": "unpublish"}
DONE = {"archive": "archived", "restore": "restored", "unpublish": "unpublished (now a draft)"}

SCHEMA = schema(
    "outline_archive",
    "Archive a document (reversible, keeps it out of the collection), restore an archived or trashed "
    "document, or unpublish a document back into a draft. Use outline_delete only when the page "
    "should really go away.",
    {
        "id": {"type": "string", "description": "Document id."},
        "action": {
            "type": "string",
            "enum": ["archive", "restore", "unpublish"],
            "description": "One of: archive (default), restore, unpublish.",
            "default": "archive",
        },
        "profile": PROFILE_PROPERTY,
    },
    ["id"],
)


@tool_handler
def handle(args: dict) -> str:
    doc_id = req_str(args, "id")
    requested = (opt_str(args, "action") or "archive").lower()
    action = ACTIONS.get(requested)
    if action is None:
        raise ToolInputError(f'Unknown action "{args.get("action")}". Use archive, restore or unpublish.')

    config = cfg.resolve_config(opt_str(args, "profile"))
    doc = document_lifecycle(config, action, doc_id)
    title = doc.title if doc else doc_id
    final_id = doc.id if doc else doc_id
    return result(
        f"Document {title} {DONE[action]}.\nId: {final_id}",
        id=final_id,
        action=action,
        title=doc.title if doc else None,
    )
