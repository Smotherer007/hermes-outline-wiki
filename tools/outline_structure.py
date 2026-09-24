"""outline_structure -- Show the nested document tree of a collection.

Cheaper and more useful than listing documents flat: it reveals how the wiki
is organised, which is what you need before filing a new document.
"""

from __future__ import annotations

from .. import config as cfg
from ..client import get_collection_structure, list_collections
from ..formatters import count_nodes, format_collection_structure
from ._base import PROFILE_PROPERTY, opt_str, req_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_structure",
    "Show the nested document tree of one collection (titles and ids, parents and children). Use it "
    "to understand how a wiki section is organised before creating or moving documents.",
    {
        "collectionId": {"type": "string", "description": "Collection id. Get it from outline_collections."},
        "profile": PROFILE_PROPERTY,
    },
    ["collectionId"],
)


@tool_handler
def handle(args: dict) -> str:
    collection_id = req_str(args, "collectionId")
    config = cfg.resolve_config(opt_str(args, "profile"))
    nodes = get_collection_structure(config, collection_id)

    # The tree endpoint returns no collection name, so resolve it for output.
    collection_name = None
    try:
        collections, _ = list_collections(config, limit=100)
        collection_name = next((c.name for c in collections if c.id == collection_id), None)
    except Exception:
        pass  # naming is cosmetic -- never fail the call over it

    return result(
        format_collection_structure(nodes, collection_name),
        collectionId=collection_id,
        collectionName=collection_name,
        topLevelCount=len(nodes),
        totalCount=count_nodes(nodes),
    )
