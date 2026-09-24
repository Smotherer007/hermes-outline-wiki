"""Outline API client.

The Outline API is RPC over HTTP: every method is a POST to
``<workspace>/api/<method>`` with a JSON body and a Bearer API key, and every
response is ``{ ok, data, pagination? }``. :func:`call_outline` is the single
place that owns auth, timeouts and error translation; everything above it is
a thin, typed wrapper that returns plain data and never mutates state.

Only the standard library is used, so the plugin installs into Hermes'
virtualenv without pulling in (or conflicting with) any package.
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    CollectionSummary,
    CommentEntry,
    DocumentDetail,
    DocumentSummary,
    NavigationNode,
    OutlineApiError,
    OutlineConfig,
    OutlineNotFoundError,
    OutlineResponse,
    Pagination,
    SearchHit,
    UnsafeExportPathError,
    UserRef,
    WorkspaceInfo,
)

DEFAULT_TIMEOUT_S = 30.0
PLUGIN_VERSION = "1.0.0"

_insecure_context: Optional[ssl.SSLContext] = None


class _JsonNull:
    """Sentinel for an explicit JSON null in a request body."""

    def __repr__(self) -> str:
        return "JSON_NULL"


JSON_NULL = _JsonNull()


def _ssl_context(config: OutlineConfig) -> Optional[ssl.SSLContext]:
    """Certificate validation is switched off per request, only for profiles
    that opt in -- unlike Node, Python does not force this to be process-wide."""
    global _insecure_context
    if not config.insecure_tls:
        return None
    if _insecure_context is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _insecure_context = ctx
    return _insecure_context


# Core request


def _describe_failure(method: str, status: int, payload: Any) -> OutlineApiError:
    body = payload if isinstance(payload, dict) else {}
    code = body.get("error") if isinstance(body.get("error"), str) else None
    detail = ""
    if isinstance(body.get("message"), str) and body["message"]:
        detail = body["message"]
    elif isinstance(body.get("error"), str):
        detail = body["error"]

    if status == 401:
        return OutlineApiError(
            method, status,
            "Outline rejected the API key (401). Create a new key under Settings -> API & Apps and re-run outline_setup.",
            code,
        )
    if status == 403:
        suffix = f": {detail}" if detail else ""
        return OutlineApiError(
            method, status,
            f"Outline denied access (403){suffix}. The API key's user may lack permission for this collection or document.",
            code,
        )
    if status == 429:
        return OutlineApiError(
            method, status, "Outline rate limit reached (429). Wait a moment and retry.", code
        )
    suffix = f": {detail}" if detail else ""
    return OutlineApiError(method, status, f"Outline API {method} failed ({status}){suffix}", code)


def _parse(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def call_outline(
    config: OutlineConfig,
    method: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> OutlineResponse:
    """Call one Outline API method. Raises :class:`OutlineApiError` for any non-ok response."""
    # None means "not given" and is dropped, like `undefined` in the pi
    # extension; JSON_NULL is sent as an explicit null.
    payload = {
        k: (None if v is JSON_NULL else v)
        for k, v in (body or {}).items()
        if v is not None
    }
    endpoint = f"{config.url}/api/{method}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {config.api_key}",
            "User-Agent": f"hermes-outline-wiki/{PLUGIN_VERSION}",
        },
    )

    status = 0
    raw = ""
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context(config)) as response:
            status = response.status
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        status = err.code
        try:
            raw = err.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        parsed = _parse(raw)
        if parsed is None and raw.strip().startswith("<"):
            raise OutlineApiError(
                method, status,
                f"Outline returned HTML instead of JSON ({status}). Is {config.url} really an Outline workspace?",
            ) from None
        raise _describe_failure(method, status, parsed) from None
    except (socket.timeout, TimeoutError):
        raise OutlineApiError(
            method, 0, f"Outline did not respond within {round(timeout)}s ({endpoint})."
        ) from None
    except urllib.error.URLError as err:
        reason = err.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise OutlineApiError(
                method, 0, f"Outline did not respond within {round(timeout)}s ({endpoint})."
            ) from None
        raise OutlineApiError(method, 0, f"Could not reach Outline at {config.url}: {reason}") from None
    except OSError as err:
        raise OutlineApiError(method, 0, f"Could not reach Outline at {config.url}: {err}") from None

    parsed = _parse(raw)
    if not isinstance(parsed, dict) or parsed.get("ok") is False:
        if parsed is None and raw.strip().startswith("<"):
            raise OutlineApiError(
                method, status,
                f"Outline returned HTML instead of JSON ({status}). Is {config.url} really an Outline workspace?",
            )
        raise _describe_failure(method, status, parsed)
    return OutlineResponse(data=parsed.get("data"), pagination=Pagination.from_json(parsed.get("pagination")))


# Mapping -- API payloads to domain data


def _str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def to_user_ref(raw: Any) -> Optional[UserRef]:
    if not isinstance(raw, dict):
        return None
    return UserRef(id=_str(raw.get("id")), name=_str(raw.get("name")), email=_str(raw.get("email")))


def _summary_fields(doc: Dict[str, Any]) -> Dict[str, Any]:
    title = doc.get("title")
    return dict(
        id=str(doc.get("id") or ""),
        title=title if isinstance(title, str) and title else "Untitled",
        url_id=doc.get("urlId"),
        url=doc.get("url"),
        icon=doc.get("icon"),
        collection_id=doc.get("collectionId"),
        parent_document_id=doc.get("parentDocumentId"),
        template=bool(doc.get("template")),
        full_width=bool(doc.get("fullWidth")),
        created_at=doc.get("createdAt"),
        updated_at=doc.get("updatedAt"),
        archived_at=doc.get("archivedAt"),
        deleted_at=doc.get("deletedAt"),
        published_at=doc.get("publishedAt"),
        created_by=to_user_ref(doc.get("createdBy")),
        updated_by=to_user_ref(doc.get("updatedBy")),
    )


def to_document_summary(raw: Any) -> DocumentSummary:
    return DocumentSummary(**_summary_fields(raw if isinstance(raw, dict) else {}))


def to_document_detail(raw: Any) -> DocumentDetail:
    doc = raw if isinstance(raw, dict) else {}
    text = doc.get("text")
    return DocumentDetail(**_summary_fields(doc), text=text if isinstance(text, str) else "")


def to_collection_summary(raw: Any) -> CollectionSummary:
    col = raw if isinstance(raw, dict) else {}
    name = col.get("name")
    return CollectionSummary(
        id=str(col.get("id") or ""),
        name=name if isinstance(name, str) else "Untitled",
        description=col.get("description"),
        icon=col.get("icon"),
        color=col.get("color"),
        permission=col.get("permission"),
        updated_at=col.get("updatedAt"),
    )


def to_navigation_node(raw: Any) -> NavigationNode:
    node = raw if isinstance(raw, dict) else {}
    title = node.get("title")
    children = node.get("children") if isinstance(node.get("children"), list) else []
    return NavigationNode(
        id=str(node.get("id") or ""),
        title=title if isinstance(title, str) and title else "Untitled",
        url=node.get("url"),
        children=tuple(to_navigation_node(child) for child in children),
    )


_BLOCK_TYPES = {
    "paragraph", "heading", "blockquote", "code_block", "code_fence", "list_item", "checkbox_item",
}


def flatten_rich_text(raw: Any) -> str:
    """Comments are stored as a ProseMirror document. Flatten it to plain text so
    the agent reads prose instead of a node tree."""
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, dict):
        return ""
    if raw.get("type") == "text" and isinstance(raw.get("text"), str):
        return raw["text"]
    children = raw.get("content") if isinstance(raw.get("content"), list) else []
    joined = "".join(part for part in (flatten_rich_text(c) for c in children) if part)
    return f"{joined}\n" if str(raw.get("type")) in _BLOCK_TYPES else joined


def to_comment(raw: Any) -> CommentEntry:
    comment = raw if isinstance(raw, dict) else {}
    text = comment.get("text")
    if not (isinstance(text, str) and text):
        text = flatten_rich_text(comment.get("data")).strip()
    return CommentEntry(
        id=str(comment.get("id") or ""),
        text=text,
        document_id=comment.get("documentId"),
        parent_comment_id=comment.get("parentCommentId"),
        created_at=comment.get("createdAt"),
        updated_at=comment.get("updatedAt"),
        resolved_at=comment.get("resolvedAt"),
        created_by=to_user_ref(comment.get("createdBy")),
    )


def _list(data: Any) -> list:
    return data if isinstance(data, list) else []


# Operations -- workspace


def get_workspace_info(config: OutlineConfig) -> WorkspaceInfo:
    res = call_outline(config, "auth.info", {}, timeout=15)
    data = res.data if isinstance(res.data, dict) else {}
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    team = data.get("team") if isinstance(data.get("team"), dict) else {}
    return WorkspaceInfo(
        user_name=user.get("name"), user_email=user.get("email"),
        team_name=team.get("name"), team_url=team.get("url"),
    )


# Operations -- collections


def list_collections(
    config: OutlineConfig, limit: Optional[int] = None, offset: Optional[int] = None
) -> Tuple[List[CollectionSummary], Optional[Pagination]]:
    res = call_outline(config, "collections.list", {
        "limit": limit if limit is not None else 50,
        "offset": offset if offset is not None else 0,
    })
    return [to_collection_summary(c) for c in _list(res.data)], res.pagination


def get_collection_structure(config: OutlineConfig, collection_id: str) -> List[NavigationNode]:
    res = call_outline(config, "collections.documents", {"id": collection_id})
    return [to_navigation_node(n) for n in _list(res.data)]


# Operations -- documents


def search_documents(
    config: OutlineConfig,
    query: str,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    collection_id: Optional[str] = None,
    document_id: Optional[str] = None,
    status_filter: Optional[List[str]] = None,
    date_filter: Optional[str] = None,
) -> Tuple[List[SearchHit], Optional[Pagination]]:
    res = call_outline(config, "documents.search", {
        "query": query,
        "limit": limit if limit is not None else 15,
        "offset": offset if offset is not None else 0,
        "collectionId": collection_id,
        "documentId": document_id,
        "statusFilter": status_filter,
        "dateFilter": date_filter,
    })
    hits = []
    for hit in _list(res.data):
        hit = hit if isinstance(hit, dict) else {}
        ranking = hit.get("ranking")
        hits.append(SearchHit(
            document=to_document_summary(hit.get("document")),
            context=hit.get("context") if isinstance(hit.get("context"), str) else "",
            ranking=ranking if isinstance(ranking, (int, float)) and not isinstance(ranking, bool) else None,
        ))
    return hits, res.pagination


def list_documents(
    config: OutlineConfig,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    collection_id: Optional[str] = None,
    parent_document_id: Optional[str] = None,
    user_id: Optional[str] = None,
    sort: Optional[str] = None,
    direction: Optional[str] = None,
    status_filter: Optional[List[str]] = None,
    drafts: bool = False,
) -> Tuple[List[DocumentSummary], Optional[Pagination]]:
    method = "documents.drafts" if drafts else "documents.list"
    res = call_outline(config, method, {
        "limit": limit if limit is not None else 25,
        "offset": offset if offset is not None else 0,
        "collectionId": collection_id,
        "parentDocumentId": None if drafts else parent_document_id,
        "userId": None if drafts else user_id,
        "sort": sort or "updatedAt",
        "direction": direction or "DESC",
        "statusFilter": None if drafts else status_filter,
    })
    return [to_document_summary(d) for d in _list(res.data)], res.pagination


def get_document(config: OutlineConfig, doc_id: str) -> DocumentDetail:
    try:
        res = call_outline(config, "documents.info", {"id": doc_id})
    except OutlineApiError as err:
        if err.status == 404:
            raise OutlineNotFoundError(f'Document "{doc_id}"') from None
        raise
    if not res.data:
        raise OutlineNotFoundError(f'Document "{doc_id}"')
    return to_document_detail(res.data)


def create_document(
    config: OutlineConfig,
    title: str,
    text: Optional[str] = None,
    collection_id: Optional[str] = None,
    parent_document_id: Optional[str] = None,
    template_id: Optional[str] = None,
    icon: Optional[str] = None,
    publish: bool = True,
) -> DocumentDetail:
    res = call_outline(config, "documents.create", {
        "title": title,
        "text": text,
        "collectionId": collection_id,
        "parentDocumentId": parent_document_id,
        "templateId": template_id,
        "icon": icon,
        "publish": publish,
    })
    return to_document_detail(res.data)


def update_document(
    config: OutlineConfig,
    doc_id: str,
    title: Optional[str] = None,
    text: Optional[str] = None,
    icon: Optional[str] = None,
    full_width: Optional[bool] = None,
    publish: Optional[bool] = None,
) -> DocumentDetail:
    res = call_outline(config, "documents.update", {
        "id": doc_id, "title": title, "text": text, "icon": icon,
        "fullWidth": full_width, "publish": publish,
    })
    return to_document_detail(res.data)


def move_document(
    config: OutlineConfig,
    doc_id: str,
    collection_id: Optional[str] = None,
    parent_document_id: Any = None,
    index: Optional[int] = None,
) -> int:
    """Move a document. Pass ``parent_document_id=JSON_NULL`` to detach it from
    its parent (Outline needs an explicit null for that)."""
    res = call_outline(config, "documents.move", {
        "id": doc_id,
        "collectionId": collection_id,
        "parentDocumentId": parent_document_id,
        "index": index,
    })
    data = res.data if isinstance(res.data, dict) else {}
    documents = data.get("documents")
    return len(documents) if isinstance(documents, list) else 0


def document_lifecycle(
    config: OutlineConfig, action: str, doc_id: str, permanent: bool = False
) -> Optional[DocumentSummary]:
    if action not in ("archive", "restore", "unpublish", "delete"):
        raise ValueError(f"Unknown lifecycle action {action!r}")
    body: Dict[str, Any] = {"id": doc_id}
    if action == "delete" and permanent:
        body["permanent"] = True
    res = call_outline(config, f"documents.{action}", body)
    return to_document_summary(res.data) if res.data else None


def export_document(config: OutlineConfig, doc_id: str) -> str:
    """Fetch a document as markdown via documents.export."""
    res = call_outline(config, "documents.export", {"id": doc_id})
    return res.data if isinstance(res.data, str) else ""


# Operations -- comments


def list_comments(
    config: OutlineConfig, document_id: str, limit: Optional[int] = None, offset: Optional[int] = None
) -> Tuple[List[CommentEntry], Optional[Pagination]]:
    res = call_outline(config, "comments.list", {
        "documentId": document_id,
        "limit": limit if limit is not None else 50,
        "offset": offset if offset is not None else 0,
    })
    return [to_comment(c) for c in _list(res.data)], res.pagination


def create_comment(
    config: OutlineConfig, document_id: str, text: str, parent_comment_id: Optional[str] = None
) -> CommentEntry:
    res = call_outline(config, "comments.create", {
        "documentId": document_id,
        "parentCommentId": parent_comment_id,
        "text": text,
        # Older Outline releases validate `data` (ProseMirror) rather than
        # `text`; sending both keeps one call working across versions.
        "data": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        },
    })
    return to_comment(res.data)


# Local file output


def slugify_title(title: str) -> str:
    """Slugify a document title into a safe file name stem."""
    normalized = unicodedata.normalize("NFKD", title)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")[:80]
    return slug or "document"


def write_markdown_file(directory: str, file_name: str, content: str) -> str:
    """Write markdown into ``directory``, refusing any path that escapes it.
    Returns the absolute path written."""
    target_dir = Path(os.path.abspath(os.path.expanduser(directory)))
    target = Path(os.path.abspath(target_dir / file_name))
    if target != target_dir and target_dir not in target.parents:
        raise UnsafeExportPathError(file_name)
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)
