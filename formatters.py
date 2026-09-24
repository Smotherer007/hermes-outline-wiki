"""Output formatters.

Pure functions that transform domain data into display strings.
No emojis, no side effects. Wording matches pi-outline-wiki so the bundled
skills read the same on both agents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Sequence

from .models import (
    CollectionSummary,
    CommentEntry,
    DocumentDetail,
    DocumentSummary,
    NavigationNode,
    OutlineConfig,
    Pagination,
    SearchHit,
    WorkspaceInfo,
)


def mask_api_key(api_key: str) -> str:
    """Show only the prefix and the last four characters of an API key."""
    if not api_key:
        return "(none)"
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:7]}...{api_key[-4:]}"


def short_date(value: Optional[str]) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is not None:
        from datetime import timezone

        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def status_markers(doc: DocumentSummary) -> str:
    markers: List[str] = []
    if doc.deleted_at:
        markers.append("trashed")
    elif doc.archived_at:
        markers.append("archived")
    elif not doc.published_at:
        markers.append("draft")
    if doc.template:
        markers.append("template")
    return f" [{','.join(markers)}]" if markers else ""


def pagination_note(pagination: Optional[Pagination], shown: int = 0) -> str:
    if pagination is None:
        return ""
    offset = pagination.offset or 0
    limit = pagination.limit if pagination.limit is not None else shown
    if shown < limit:
        return ""
    return f"\n\nMore results may exist. Re-run with offset {offset + limit}."


# Profiles


def format_profile_status(
    profiles: Mapping[str, OutlineConfig],
    active: Optional[str],
    env_profiles: Sequence[str] = (),
) -> str:
    names = list(profiles)
    if not names:
        return (
            "No Outline workspace configured. Use outline_setup with your workspace URL and an "
            "API key from Settings -> API & Apps, or set OUTLINE_URL and OUTLINE_API_KEY."
        )

    lines: List[str] = []
    for name in names:
        config = profiles[name]
        marker = "*" if name == active else " "
        insecure = " (TLS validation off)" if config.insecure_tls else ""
        source = " (from environment)" if name in env_profiles else ""
        lines.append(f"{marker} {name}: {config.url} key {mask_api_key(config.api_key)}{insecure}{source}")
        # The description is what tells the agent which wiki holds what, so it
        # gets its own line rather than being truncated onto the end of the URL.
        if config.description:
            lines.append(f"    {config.description}")

    footer = (
        [
            "",
            "Target one workspace with the profile parameter, or set allProfiles: true on "
            "outline_search to search all of them at once.",
        ]
        if len(names) > 1
        else []
    )
    return "\n".join([f"Outline workspaces ({len(names)}), * marks the active one:", *lines, *footer])


@dataclass(frozen=True)
class ProfileSearchResult:
    """Search results gathered from one of several workspaces in one call."""

    profile: str
    hits: Sequence[SearchHit] = field(default_factory=tuple)
    description: Optional[str] = None
    error: Optional[str] = None


def format_multi_search_results(results: Sequence[ProfileSearchResult], query: str) -> str:
    with_hits = [r for r in results if r.hits]
    failed = [r for r in results if r.error]
    total = sum(len(r.hits) for r in with_hits)

    sections: List[str] = []
    if total == 0:
        sections.append(
            f'No documents match "{query}" in any of the {len(results)} configured workspace(s).'
        )
    else:
        sections.append(f'Search "{query}" across {len(results)} workspace(s) -- {total} result(s).')
        sections.append(
            "Ids are only valid within their own workspace: pass that workspace as the profile "
            "parameter to outline_read."
        )

    for result in with_hits:
        label = f"{result.profile} ({result.description})" if result.description else result.profile
        lines = []
        for index, hit in enumerate(result.hits, start=1):
            context = _one_line(hit.context)
            entry = [
                f"  {index}. {hit.document.title}{status_markers(hit.document)}",
                f"     id {hit.document.id} | profile {result.profile} | updated {short_date(hit.document.updated_at)}",
            ]
            if context:
                entry.append(f"     {context[:300]}")
            lines.append("\n".join(entry))
        sections.append(f"\n[{label}] {len(result.hits)} result(s):\n" + "\n".join(lines))

    empty = [r for r in results if not r.error and not r.hits]
    if empty and total > 0:
        sections.append(f"\nNo matches in: {', '.join(r.profile for r in empty)}.")

    if failed:
        sections.append(f"\n{len(failed)} workspace(s) could not be searched:")
        sections.extend(f"- {r.profile}: {r.error}" for r in failed)

    return "\n".join(sections)


def format_workspace_info(info: WorkspaceInfo) -> str:
    email = f" <{info.user_email}>" if info.user_email else ""
    return "\n".join([
        f"Workspace: {info.team_name or '(unknown)'}",
        f"URL: {info.team_url or '(unknown)'}",
        f"Authenticated as: {info.user_name or '(unknown)'}{email}",
    ])


# Collections


def format_collection_list(collections: Sequence[CollectionSummary]) -> str:
    if not collections:
        return "No collections found. The API key's user may not be a member of any collection."
    lines = []
    for collection in collections:
        description = (
            f" -- {_one_line(collection.description)[:100]}" if collection.description else ""
        )
        lines.append(f"- {collection.name} (id {collection.id}){description}")
    return "\n".join([f"Collections ({len(collections)}):", *lines])


def format_collection_structure(
    nodes: Sequence[NavigationNode], collection_name: Optional[str] = None
) -> str:
    if not nodes:
        return f"Collection {collection_name or ''} has no documents.".replace("  ", " ").strip()

    lines: List[str] = []

    def walk(items: Sequence[NavigationNode], indent: str) -> None:
        for node in items:
            lines.append(f"{indent}- {node.title} (id {node.id})")
            if node.children:
                walk(node.children, indent + "  ")

    walk(nodes, "")
    header = f'Document tree of "{collection_name}":' if collection_name else "Document tree:"
    return "\n".join([header, *lines])


def count_nodes(nodes: Sequence[NavigationNode]) -> int:
    return sum(1 + count_nodes(node.children) for node in nodes)


def flatten_nodes(nodes: Sequence[NavigationNode]) -> List[NavigationNode]:
    out: List[NavigationNode] = []
    for node in nodes:
        out.append(node)
        out.extend(flatten_nodes(node.children))
    return out


# Documents


def format_document_list(
    documents: Sequence[DocumentSummary], heading: str, pagination: Optional[Pagination] = None
) -> str:
    if not documents:
        return f"{heading}: nothing found."
    lines = []
    for doc in documents:
        author = f" by {doc.updated_by.name}" if doc.updated_by and doc.updated_by.name else ""
        lines.append(
            f"- {doc.title}{status_markers(doc)}\n  id {doc.id} | updated {short_date(doc.updated_at)}{author}"
        )
    return f"{heading} ({len(documents)}):\n" + "\n".join(lines) + pagination_note(pagination, len(documents))


def format_search_results(
    hits: Sequence[SearchHit], query: str, pagination: Optional[Pagination] = None
) -> str:
    if not hits:
        return (
            f'No documents match "{query}". Try fewer or more general keywords, or drop the '
            "collection filter."
        )
    lines = []
    for index, hit in enumerate(hits, start=1):
        context = _one_line(hit.context)
        entry = [
            f"{index}. {hit.document.title}{status_markers(hit.document)}",
            f"   id {hit.document.id} | updated {short_date(hit.document.updated_at)}",
        ]
        if context:
            entry.append(f"   {context[:300]}")
        lines.append("\n".join(entry))
    return (
        f'Search "{query}" -- {len(hits)} result(s). Read one with outline_read.\n'
        + "\n".join(lines)
        + pagination_note(pagination, len(hits))
    )


def format_document(doc: DocumentDetail, max_chars: int = 0) -> str:
    body = doc.text or "(this document has no content yet)"
    truncated = False
    if max_chars > 0 and len(body) > max_chars:
        body = body[:max_chars]
        truncated = True

    updated_by = f" by {doc.updated_by.name}" if doc.updated_by and doc.updated_by.name else ""
    header = [
        f"Title: {doc.title}{status_markers(doc)}",
        f"Id: {doc.id}",
        f"Collection: {doc.collection_id}" if doc.collection_id else "",
        f"Parent document: {doc.parent_document_id}" if doc.parent_document_id else "",
        f"URL: {doc.url}" if doc.url else "",
        f"Updated: {short_date(doc.updated_at)}{updated_by}",
    ]
    footer = (
        f"\n\n[truncated after {max_chars} characters -- re-run outline_read with a larger "
        "maxChars to see the rest]"
        if truncated
        else ""
    )
    return "\n".join(line for line in header if line) + f"\n\n---\n\n{body}{footer}"


def format_document_saved(doc: DocumentSummary, action: str) -> str:
    state = "published" if doc.published_at else "draft"
    lines = [f"Document {action} ({state}): {doc.title}", f"Id: {doc.id}"]
    if doc.url:
        lines.append(f"URL: {doc.url}")
    return "\n".join(lines)


# Comments


def format_comments(comments: Sequence[CommentEntry], document_id: str) -> str:
    if not comments:
        return f"No comments on document {document_id}."

    by_parent: Dict[str, List[CommentEntry]] = {}
    roots: List[CommentEntry] = []
    for comment in comments:
        if comment.parent_comment_id:
            by_parent.setdefault(comment.parent_comment_id, []).append(comment)
        else:
            roots.append(comment)

    lines: List[str] = []

    def render(entry: CommentEntry, indent: str) -> None:
        author = entry.created_by.name if entry.created_by and entry.created_by.name else "unknown"
        resolved = " [resolved]" if entry.resolved_at else ""
        lines.append(f"{indent}- {author} at {short_date(entry.created_at)}{resolved} (id {entry.id})")
        for line in (entry.text or "(empty)").split("\n"):
            lines.append(f"{indent}  {line}")
        for child in by_parent.get(entry.id, []):
            render(child, indent + "  ")

    for root in roots:
        render(root, "")

    return "\n".join([f"Comments on document {document_id} ({len(comments)}):", *lines])
