"""outline_read -- Read one document's markdown body.

Long wiki pages can blow a context window, so the body is truncated by
default and the caller decides how much to pull in.
"""

from __future__ import annotations

from .. import config as cfg
from ..client import get_document, list_documents, slugify_title, write_markdown_file
from ..formatters import format_document, format_document_list
from ._base import PROFILE_PROPERTY, opt_bool, opt_int, opt_str, req_str, result, schema, tool_handler

DEFAULT_MAX_CHARS = 20_000

SCHEMA = schema(
    "outline_read",
    "Read a document's full markdown body by id (the id or urlId from outline_search, outline_list or "
    "outline_structure). Optionally list its child documents or save it to a local markdown file.",
    {
        "id": {"type": "string", "description": "Document id (uuid) or urlId from an Outline URL."},
        "maxChars": {
            "type": "number",
            "description": "Truncate the body after this many characters. Default 20000. Use 0 for no limit.",
            "default": DEFAULT_MAX_CHARS,
        },
        "includeChildren": {
            "type": "boolean",
            "description": "Also list the direct child documents. Default false.",
            "default": False,
        },
        "saveDir": {
            "type": "string",
            "description": "Directory to save the document as a .md file in. Absolute paths are safest.",
        },
        "profile": PROFILE_PROPERTY,
    },
    ["id"],
)


@tool_handler
def handle(args: dict) -> str:
    config = cfg.resolve_config(opt_str(args, "profile"))
    doc = get_document(config, req_str(args, "id"))
    max_chars = opt_int(args, "maxChars")
    if max_chars is None:
        max_chars = DEFAULT_MAX_CHARS

    sections = [format_document(doc, max_chars=max_chars)]

    saved_path = None
    save_dir = opt_str(args, "saveDir")
    if save_dir:
        saved_path = write_markdown_file(
            save_dir, f"{slugify_title(doc.title)}.md", f"# {doc.title}\n\n{doc.text}\n"
        )
        sections.append(f"\nSaved full document to {saved_path}")

    child_count = 0
    if opt_bool(args, "includeChildren"):
        children, _ = list_documents(config, parent_document_id=doc.id, limit=50)
        child_count = len(children)
        sections.append("\n" + format_document_list(children, "Child documents"))

    return result(
        "\n".join(sections),
        id=doc.id,
        title=doc.title,
        collectionId=doc.collection_id,
        length=len(doc.text),
        truncated=max_chars > 0 and len(doc.text) > max_chars,
        childCount=child_count,
        savedPath=saved_path,
    )
