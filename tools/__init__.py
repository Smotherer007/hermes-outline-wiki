"""One module per tool, each exposing ``SCHEMA`` and ``handle``."""

from __future__ import annotations

from . import (
    outline_archive,
    outline_collections,
    outline_comment,
    outline_comments,
    outline_create,
    outline_delete,
    outline_export,
    outline_list,
    outline_move,
    outline_profile,
    outline_read,
    outline_search,
    outline_setup,
    outline_status,
    outline_structure,
    outline_update,
)

TOOLSET = "outline"

#: Registration order = order in which the model sees the tools.
TOOL_MODULES = (
    outline_setup,
    outline_status,
    outline_profile,
    outline_collections,
    outline_structure,
    outline_search,
    outline_list,
    outline_read,
    outline_create,
    outline_update,
    outline_move,
    outline_archive,
    outline_delete,
    outline_comments,
    outline_comment,
    outline_export,
)

#: Tools that change content in Outline. The safety level applies to these.
WIKI_WRITE_TOOLS = frozenset({
    "outline_create",
    "outline_update",
    "outline_move",
    "outline_archive",
    "outline_delete",
    "outline_comment",
})
