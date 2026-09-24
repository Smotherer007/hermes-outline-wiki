"""outline_comment -- Post a comment or a reply on a document."""

from __future__ import annotations

from .. import config as cfg
from ..client import create_comment
from ._base import PROFILE_PROPERTY, opt_str, req_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_comment",
    "Post a comment on a document, or reply to an existing comment thread. Use this to leave a "
    "question or a note for the humans who own the page instead of editing it silently.",
    {
        "documentId": {"type": "string", "description": "Document id to comment on."},
        "text": {"type": "string", "description": "Comment text."},
        "parentCommentId": {"type": "string", "description": "Reply inside this comment thread."},
        "profile": PROFILE_PROPERTY,
    },
    ["documentId", "text"],
)


@tool_handler
def handle(args: dict) -> str:
    document_id = req_str(args, "documentId")
    text = req_str(args, "text").strip()
    parent_id = opt_str(args, "parentCommentId")
    config = cfg.resolve_config(opt_str(args, "profile"))
    comment = create_comment(config, document_id, text, parent_comment_id=parent_id)
    kind = "Reply" if parent_id else "Comment"
    return result(
        f"{kind} posted on document {document_id}.\nComment id: {comment.id}",
        id=comment.id,
        documentId=document_id,
        parentCommentId=parent_id,
    )
