"""outline_comments -- Read the discussion on a document."""

from __future__ import annotations

from .. import config as cfg
from ..client import list_comments
from ..formatters import format_comments
from ._base import PROFILE_PROPERTY, opt_int, opt_str, req_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_comments",
    "Read the comment threads on a document, nested by reply. Useful for open questions and review "
    "feedback that never made it into the page body.",
    {
        "documentId": {"type": "string", "description": "Document id."},
        "limit": {"type": "number", "description": "How many comments to return. Default 50.", "default": 50},
        "offset": {"type": "number", "description": "Pagination offset. Default 0.", "default": 0},
        "profile": PROFILE_PROPERTY,
    },
    ["documentId"],
)


@tool_handler
def handle(args: dict) -> str:
    document_id = req_str(args, "documentId")
    config = cfg.resolve_config(opt_str(args, "profile"))
    comments, pagination = list_comments(
        config, document_id, limit=opt_int(args, "limit"), offset=opt_int(args, "offset")
    )
    return result(
        format_comments(comments, document_id),
        documentId=document_id,
        count=len(comments),
        unresolved=sum(1 for c in comments if not c.resolved_at),
        pagination=pagination.to_json() if pagination else None,
    )
