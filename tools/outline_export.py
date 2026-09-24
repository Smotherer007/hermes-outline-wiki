"""outline_export -- Save wiki documents to local markdown files.

The point is to get wiki knowledge into the repository the agent is working
in (docs/, ADRs, onboarding notes) without copying text through the model.
"""

from __future__ import annotations

from .. import config as cfg
from ..client import (
    export_document,
    get_collection_structure,
    get_document,
    slugify_title,
    write_markdown_file,
)
from ..formatters import flatten_nodes
from ..models import ToolInputError
from ._base import PROFILE_PROPERTY, opt_bool, opt_int, opt_str, req_str, result, schema, tool_handler

SCHEMA = schema(
    "outline_export",
    "Export one document (optionally with its children) or a whole collection to local markdown "
    "files. Use it to pull wiki content into a repository instead of reading every page through the "
    "model.",
    {
        "targetDir": {
            "type": "string",
            "description": "Directory to write the .md files into. Absolute paths are safest.",
        },
        "documentId": {
            "type": "string",
            "description": "Document to export. Mutually exclusive with collectionId.",
        },
        "collectionId": {"type": "string", "description": "Export every document of this collection."},
        "includeChildren": {
            "type": "boolean",
            "description": "With documentId: also export nested child documents. Default false.",
            "default": False,
        },
        "limit": {
            "type": "number",
            "description": "Maximum number of documents to write. Default 50.",
            "default": 50,
        },
        "profile": PROFILE_PROPERTY,
    },
    ["targetDir"],
)


@tool_handler
def handle(args: dict) -> str:
    target_dir = req_str(args, "targetDir")
    document_id = opt_str(args, "documentId")
    collection_id = opt_str(args, "collectionId")
    if not document_id and not collection_id:
        raise ToolInputError("Pass either documentId or collectionId.")
    if document_id and collection_id:
        raise ToolInputError("Pass documentId or collectionId, not both.")

    config = cfg.resolve_config(opt_str(args, "profile"))
    limit = opt_int(args, "limit")
    if limit is None:
        limit = 50
    targets = []

    if collection_id:
        tree = get_collection_structure(config, collection_id)
        targets = [(node.id, node.title) for node in flatten_nodes(tree)]
    else:
        doc = get_document(config, document_id)
        targets.append((doc.id, doc.title))
        if opt_bool(args, "includeChildren") and doc.collection_id:
            tree = get_collection_structure(config, doc.collection_id)
            node = next((n for n in flatten_nodes(tree) if n.id == doc.id), None)
            if node is not None:
                targets.extend((child.id, child.title) for child in flatten_nodes(node.children))

    capped = targets[:limit]
    written = []
    failed = []
    used_names = set()

    for target_id, title in capped:
        try:
            markdown = export_document(config, target_id)
            stem = slugify_title(title)
            # Wikis are full of pages called "Overview"; keep every file.
            if stem in used_names:
                stem = f"{stem}-{target_id[:8]}"
            used_names.add(stem)
            written.append(write_markdown_file(target_dir, f"{stem}.md", markdown))
        except Exception as exc:
            failed.append({"id": target_id, "error": str(exc)})

    lines = [f"Exported {len(written)} document(s) to {target_dir}:", *[f"- {f}" for f in written]]
    if len(targets) > len(capped):
        lines.append(f"\n{len(targets) - len(capped)} more document(s) not exported (limit {limit}).")
    if failed:
        lines.append(f"\n{len(failed)} document(s) failed:")
        lines.extend(f"- {f['id']}: {f['error']}" for f in failed)

    return result(
        "\n".join(lines),
        targetDir=target_dir,
        written=written,
        writtenCount=len(written),
        failedCount=len(failed),
        skipped=len(targets) - len(capped),
    )
