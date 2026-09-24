"""Data types for the Hermes Outline Wiki plugin.

All domain data is represented as plain frozen dataclasses. No behaviour,
no inheritance -- just data (errors excepted).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Configuration


@dataclass(frozen=True)
class OutlineConfig:
    """One Outline workspace."""

    #: Workspace base URL without trailing slash and without ``/api``.
    url: str
    #: Personal API key, starts with ``ol_api_``.
    api_key: str
    #: What this wiki is for, in one line. Lets the agent pick the right one.
    description: Optional[str] = None
    #: Skip TLS certificate validation (self-signed certificates only).
    insecure_tls: bool = False

    def to_json(self) -> dict:
        """Serialise in the same shape pi-outline-wiki writes, so one file serves both."""
        data: dict = {"url": self.url, "apiKey": self.api_key}
        if self.description:
            data["description"] = self.description
        if self.insecure_tls:
            data["insecureTls"] = True
        return data

    @staticmethod
    def from_json(raw: dict) -> "OutlineConfig":
        return OutlineConfig(
            url=str(raw.get("url", "")),
            api_key=str(raw.get("apiKey", raw.get("api_key", ""))),
            description=raw.get("description") or None,
            insecure_tls=bool(raw.get("insecureTls", raw.get("insecure_tls", False))),
        )


# Domain


@dataclass(frozen=True)
class UserRef:
    id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None


@dataclass(frozen=True)
class CollectionSummary:
    id: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    permission: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class DocumentSummary:
    id: str
    title: str
    url_id: Optional[str] = None
    url: Optional[str] = None
    icon: Optional[str] = None
    collection_id: Optional[str] = None
    parent_document_id: Optional[str] = None
    template: bool = False
    full_width: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    archived_at: Optional[str] = None
    deleted_at: Optional[str] = None
    published_at: Optional[str] = None
    created_by: Optional[UserRef] = None
    updated_by: Optional[UserRef] = None


@dataclass(frozen=True)
class DocumentDetail(DocumentSummary):
    #: Markdown body.
    text: str = ""


@dataclass(frozen=True)
class SearchHit:
    document: DocumentSummary
    #: Snippet around the match, may contain markdown highlight markers.
    context: str = ""
    ranking: Optional[float] = None


@dataclass(frozen=True)
class NavigationNode:
    id: str
    title: str
    url: Optional[str] = None
    children: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class CommentEntry:
    id: str
    #: Plain text flattened from the stored rich-text document.
    text: str
    document_id: Optional[str] = None
    parent_comment_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    resolved_at: Optional[str] = None
    created_by: Optional[UserRef] = None


@dataclass(frozen=True)
class WorkspaceInfo:
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    team_name: Optional[str] = None
    team_url: Optional[str] = None


@dataclass(frozen=True)
class Pagination:
    offset: Optional[int] = None
    limit: Optional[int] = None
    total: Optional[int] = None
    next_path: Optional[str] = None

    @staticmethod
    def from_json(raw) -> Optional["Pagination"]:
        if not isinstance(raw, dict):
            return None
        return Pagination(
            offset=raw.get("offset"),
            limit=raw.get("limit"),
            total=raw.get("total"),
            next_path=raw.get("nextPath"),
        )

    def to_json(self) -> dict:
        return {k: v for k, v in {
            "offset": self.offset, "limit": self.limit,
            "total": self.total, "nextPath": self.next_path,
        }.items() if v is not None}


@dataclass(frozen=True)
class OutlineResponse:
    """Envelope every Outline API method returns."""

    data: object
    pagination: Optional[Pagination] = None


# Errors


class OutlineNotConfiguredError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Outline is not configured. Use the outline_setup tool first (workspace URL + API key)."
        )


class OutlineApiError(Exception):
    def __init__(self, method: str, status: int, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.method = method
        self.status = status
        self.code = code


class OutlineNotFoundError(Exception):
    def __init__(self, what: str) -> None:
        super().__init__(f"{what} not found. Check the id, or search for it with outline_search.")


class UnsafeExportPathError(Exception):
    def __init__(self, target: str) -> None:
        super().__init__(f"Refusing to write outside the target directory: {target}")


class ToolInputError(ValueError):
    """Invalid arguments from the model. Reported back as a tool error."""
