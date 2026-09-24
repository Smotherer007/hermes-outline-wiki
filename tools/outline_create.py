"""outline_create -- Create a new wiki document."""

from __future__ import annotations

from .. import config as cfg
from ..client import create_document
from ..formatters import format_document_saved
from ..models import ToolInputError
from ._base import PROFILE_PROPERTY, opt_bool, opt_str, req_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_create",
    "Create a new document in the Outline wiki from markdown. Give either a collectionId (top level "
    "of that collection) or a parentDocumentId (nested under an existing page). Search first -- "
    "updating an existing page is usually better than adding a near-duplicate.",
    {
        "title": {"type": "string", "description": "Document title. Keep it specific and searchable."},
        "text": {
            "type": "string",
            "description": "Markdown body. Do not repeat the title as a top-level heading; Outline "
            "renders the title separately.",
        },
        "collectionId": {
            "type": "string",
            "description": "Collection to create the document in. Required unless parentDocumentId is given.",
        },
        "parentDocumentId": {
            "type": "string",
            "description": "Create the document as a child of this document.",
        },
        "templateId": {"type": "string", "description": "Create the document from this template."},
        "icon": {"type": "string", "description": "Emoji or icon name shown next to the title."},
        "publish": {
            "type": "boolean",
            "description": "Publish immediately so others can see it. Default true. Set false to keep it "
            "as a personal draft.",
            "default": True,
        },
        "profile": PROFILE_PROPERTY,
    },
    ["title"],
)


@tool_handler
def handle(args: dict) -> str:
    title = req_str(args, "title").strip()
    publish = opt_bool(args, "publish")
    publish = True if publish is None else publish
    collection_id = opt_str(args, "collectionId")
    parent_id = opt_str(args, "parentDocumentId")
    if publish and not collection_id and not parent_id:
        raise ToolInputError(
            "A published document needs a collectionId or a parentDocumentId. List collections with "
            "outline_collections, or pass publish: false to create a draft."
        )

    config = cfg.resolve_config(opt_str(args, "profile"))
    doc = create_document(
        config,
        title=title,
        text=opt_str(args, "text") or "",
        collection_id=collection_id,
        parent_document_id=parent_id,
        template_id=opt_str(args, "templateId"),
        icon=opt_str(args, "icon"),
        publish=publish,
    )
    return result(
        format_document_saved(doc, "created"),
        id=doc.id,
        title=doc.title,
        url=doc.url,
        collectionId=doc.collection_id,
        published=bool(doc.published_at),
    )
