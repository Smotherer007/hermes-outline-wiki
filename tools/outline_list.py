"""outline_list -- Browse documents without searching.

Useful for "what changed recently", "what is in this collection" and
"what are my unpublished drafts".
"""

from __future__ import annotations

from .. import config as cfg
from ..client import list_documents
from ..formatters import format_document_list
from ..models import ToolInputError
from ._base import PROFILE_PROPERTY, opt_bool, opt_int, opt_str, result, schema, tool_handler

VALID_SORT = {"updatedAt", "createdAt", "title", "index"}

SCHEMA = schema(
    "outline_list",
    "List documents without a search query -- most recently updated first by default. Filter by "
    "collection, by parent document, or list your own drafts. Use outline_search when you know what "
    "you are looking for.",
    {
        "collectionId": {"type": "string", "description": "Only documents in this collection."},
        "parentDocumentId": {"type": "string", "description": "Only direct children of this document."},
        "drafts": {
            "type": "boolean",
            "description": "List unpublished drafts of the authenticated user instead.",
            "default": False,
        },
        "limit": {"type": "number", "description": "How many documents to return. Default 25.", "default": 25},
        "offset": {"type": "number", "description": "Pagination offset. Default 0.", "default": 0},
        "sort": {
            "type": "string",
            "enum": ["updatedAt", "createdAt", "title", "index"],
            "description": "Sort field: updatedAt (default), createdAt, title or index.",
        },
        "direction": {
            "type": "string",
            "enum": ["ASC", "DESC"],
            "description": "ASC or DESC. Default DESC.",
            "default": "DESC",
        },
        "profile": PROFILE_PROPERTY,
    },
)


@tool_handler
def handle(args: dict) -> str:
    sort = opt_str(args, "sort")
    if sort and sort not in VALID_SORT:
        raise ToolInputError(f'Invalid sort "{sort}". Use updatedAt, createdAt, title or index.')
    direction = (opt_str(args, "direction") or "DESC").upper()
    if direction not in ("ASC", "DESC"):
        raise ToolInputError(f'Invalid direction "{args.get("direction")}". Use ASC or DESC.')

    drafts = bool(opt_bool(args, "drafts"))
    collection_id = opt_str(args, "collectionId")
    parent_id = opt_str(args, "parentDocumentId")
    config = cfg.resolve_config(opt_str(args, "profile"))
    documents, pagination = list_documents(
        config,
        collection_id=collection_id,
        parent_document_id=parent_id,
        drafts=drafts,
        limit=opt_int(args, "limit"),
        offset=opt_int(args, "offset"),
        sort=sort,
        direction=direction,
    )

    if drafts:
        heading = "Drafts"
    elif parent_id:
        heading = f"Children of {parent_id}"
    elif collection_id:
        heading = f"Documents in collection {collection_id}"
    else:
        heading = "Recently updated documents"

    return result(
        format_document_list(documents, heading, pagination),
        count=len(documents),
        documents=[{"id": d.id, "title": d.title} for d in documents],
        pagination=pagination.to_json() if pagination else None,
    )
