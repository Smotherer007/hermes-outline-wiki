"""outline_delete -- Move a document to the trash, or erase it."""

from __future__ import annotations

from .. import config as cfg
from ..client import document_lifecycle, get_document
from ._base import PROFILE_PROPERTY, opt_bool, opt_str, req_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_delete",
    "Move a document to the Outline trash, where it can be restored with outline_archive action "
    "'restore'. With permanent: true it is erased and cannot be recovered -- only do that when "
    "explicitly asked. Prefer archiving over deleting.",
    {
        "id": {"type": "string", "description": "Document id."},
        "permanent": {
            "type": "boolean",
            "description": "Erase the document instead of moving it to the trash. Irreversible. Default false.",
            "default": False,
        },
        "profile": PROFILE_PROPERTY,
    },
    ["id"],
)


@tool_handler
def handle(args: dict) -> str:
    doc_id = req_str(args, "id")
    permanent = bool(opt_bool(args, "permanent"))
    config = cfg.resolve_config(opt_str(args, "profile"))

    # Resolve the title before deletion so the confirmation names the page
    # rather than a bare uuid.
    title = doc_id
    try:
        title = get_document(config, doc_id).title
    except Exception:
        pass  # the delete call below reports a real failure

    document_lifecycle(config, "delete", doc_id, permanent=permanent)

    if permanent:
        text = f'Permanently deleted "{title}" ({doc_id}). This cannot be undone.'
    else:
        text = f'Moved "{title}" ({doc_id}) to the trash. Restore it with outline_archive action "restore".'
    return result(text, id=doc_id, title=title, permanent=permanent)
