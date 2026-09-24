"""outline_move -- Re-file a document within the wiki."""

from __future__ import annotations

from .. import config as cfg
from ..client import JSON_NULL, get_document, move_document
from ..models import ToolInputError
from ._base import PROFILE_PROPERTY, opt_bool, opt_int, opt_str, req_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_move",
    "Move a document into another collection or under another parent document. Child documents move "
    "with it. Pass toTopLevel to lift a nested document to the root of its collection.",
    {
        "id": {"type": "string", "description": "Document id to move."},
        "collectionId": {"type": "string", "description": "Target collection id."},
        "parentDocumentId": {
            "type": "string",
            "description": "Target parent document id (nests the document under it).",
        },
        "toTopLevel": {
            "type": "boolean",
            "description": "Detach from the current parent and place at the collection root.",
            "default": False,
        },
        "index": {"type": "number", "description": "Position among its new siblings (0 = first)."},
        "profile": PROFILE_PROPERTY,
    },
    ["id"],
)


@tool_handler
def handle(args: dict) -> str:
    doc_id = req_str(args, "id")
    collection_id = opt_str(args, "collectionId")
    parent_id = opt_str(args, "parentDocumentId")
    to_top = bool(opt_bool(args, "toTopLevel"))
    if not collection_id and not parent_id and not to_top:
        raise ToolInputError("Specify a target: collectionId, parentDocumentId, or toTopLevel: true.")
    if parent_id and to_top:
        raise ToolInputError("parentDocumentId and toTopLevel contradict each other.")

    config = cfg.resolve_config(opt_str(args, "profile"))

    # documents.move needs a collection when the parent is cleared, so fall
    # back to the document's current one.
    if not collection_id and to_top:
        collection_id = get_document(config, doc_id).collection_id

    count = move_document(
        config,
        doc_id,
        collection_id=collection_id,
        parent_document_id=JSON_NULL if to_top else parent_id,
        index=opt_int(args, "index"),
    )

    if to_top:
        target = f"the root of collection {collection_id}"
    elif parent_id:
        target = f"under document {parent_id}"
    else:
        target = f"collection {collection_id}"

    return result(
        f"Moved document {doc_id} to {target}. {count} document(s) affected.",
        id=doc_id,
        collectionId=collection_id,
        parentDocumentId=None if to_top else parent_id,
        documentCount=count,
    )
