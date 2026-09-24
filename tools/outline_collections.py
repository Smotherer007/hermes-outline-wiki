"""outline_collections -- List the collections of the workspace.

Collections are the top level of an Outline wiki; every published document
lives in exactly one. Most write tools need a collectionId, so this is
usually the first read call in a session.
"""

from __future__ import annotations

from .. import config as cfg
from ..client import list_collections
from ..formatters import format_collection_list
from ._base import PROFILE_PROPERTY, opt_int, opt_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_collections",
    "List the collections (top-level sections) of the Outline workspace with their ids. Use this to "
    "find the collectionId needed by outline_create, outline_search filters and outline_structure.",
    {
        "limit": {"type": "number", "description": "How many collections to return. Default 50.", "default": 50},
        "offset": {"type": "number", "description": "Pagination offset. Default 0.", "default": 0},
        "profile": PROFILE_PROPERTY,
    },
)


@tool_handler
def handle(args: dict) -> str:
    config = cfg.resolve_config(opt_str(args, "profile"))
    collections, pagination = list_collections(
        config, limit=opt_int(args, "limit"), offset=opt_int(args, "offset")
    )
    return result(
        format_collection_list(collections),
        count=len(collections),
        collections=[{"id": c.id, "name": c.name} for c in collections],
        pagination=pagination.to_json() if pagination else None,
    )
