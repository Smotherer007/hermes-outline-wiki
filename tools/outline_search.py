"""outline_search -- Full-text search across one or all workspaces."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .. import config as cfg
from ..client import search_documents
from ..formatters import ProfileSearchResult, format_multi_search_results, format_search_results
from ..models import ToolInputError
from ._base import (
    opt_bool,
    opt_int,
    opt_str,
    opt_str_list,
    req_str,
    result,
    schema,
    tool_handler,
)

VALID_STATUS = {"draft", "archived", "published"}
VALID_DATE = {"day", "week", "month", "year"}

SCHEMA = schema(
    "outline_search",
    "Full-text search across the Outline wiki. Returns matching documents with a snippet and their "
    "ids; read the full text with outline_read. Prefer two or three distinctive keywords over long "
    "sentences. With several workspaces configured, target one with 'profile' or set allProfiles to "
    "search all of them at once.",
    {
        "query": {
            "type": "string",
            "description": "Search keywords. Distinctive nouns work better than full questions.",
        },
        "limit": {"type": "number", "description": "How many results to return. Default 15.", "default": 15},
        "offset": {"type": "number", "description": "Pagination offset. Default 0.", "default": 0},
        "collectionId": {"type": "string", "description": "Restrict the search to one collection."},
        "documentId": {
            "type": "string",
            "description": "Restrict the search to one document and its children.",
        },
        "statusFilter": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(VALID_STATUS)},
            "description": "Restrict to document states: any of draft, archived, published. "
            "Defaults to published documents.",
        },
        "dateFilter": {
            "type": "string",
            "enum": ["day", "week", "month", "year"],
            "description": "Only documents updated within: day, week, month or year.",
        },
        "profile": {"type": "string", "description": "Outline profile to use. Defaults to the active one."},
        "allProfiles": {
            "type": "boolean",
            "description": "Search every configured workspace instead of just one, and report which "
            "workspace each hit came from. Use it when you do not know which wiki holds the answer. "
            "Default false.",
            "default": False,
        },
    },
    ["query"],
)


@tool_handler
def handle(args: dict) -> str:
    query = req_str(args, "query").strip()
    status_filter = opt_str_list(args, "statusFilter")
    if status_filter:
        invalid = [s for s in status_filter if s not in VALID_STATUS]
        if invalid:
            raise ToolInputError(
                f"Invalid statusFilter value(s): {', '.join(invalid)}. Use draft, archived or published."
            )
    date_filter = opt_str(args, "dateFilter")
    if date_filter and date_filter not in VALID_DATE:
        raise ToolInputError(f'Invalid dateFilter "{date_filter}". Use day, week, month or year.')

    profile = opt_str(args, "profile")
    collection_id = opt_str(args, "collectionId")
    document_id = opt_str(args, "documentId")
    criteria = dict(
        query=query,
        limit=opt_int(args, "limit"),
        offset=opt_int(args, "offset"),
        collection_id=collection_id,
        document_id=document_id,
        status_filter=status_filter,
        date_filter=date_filter,
    )

    if opt_bool(args, "allProfiles"):
        if profile:
            raise ToolInputError(
                "profile and allProfiles contradict each other: pick one workspace, or search all of them."
            )
        # Collection and document filters are ids that only exist in one
        # workspace, so a fan-out with them set would silently return nothing
        # for every other wiki.
        if collection_id or document_id:
            raise ToolInputError(
                "collectionId and documentId are specific to one workspace and cannot be combined with "
                "allProfiles. Search that workspace with the profile parameter instead."
            )
        profiles = cfg.get_profiles()
        if not profiles:
            raise ToolInputError("No Outline workspace configured. Use outline_setup first.")

        # One slow or broken workspace must not sink the whole search, so each
        # failure is reported alongside the results from the others.
        def search_one(name: str) -> ProfileSearchResult:
            config = profiles[name]
            try:
                hits, _ = search_documents(config, **criteria)
                return ProfileSearchResult(profile=name, description=config.description, hits=tuple(hits))
            except Exception as exc:
                return ProfileSearchResult(profile=name, description=config.description, error=str(exc))

        names = list(profiles)
        with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
            results = list(pool.map(search_one, names))

        return result(
            format_multi_search_results(results, query),
            query=query,
            searchedProfiles=names,
            count=sum(len(r.hits) for r in results),
            failedProfiles=[r.profile for r in results if r.error],
            documents=[
                {"id": hit.document.id, "title": hit.document.title, "profile": r.profile}
                for r in results
                for hit in r.hits
            ],
        )

    config = cfg.resolve_config(profile)
    hits, pagination = search_documents(config, **criteria)
    return result(
        format_search_results(hits, query, pagination),
        query=query,
        profile=profile,
        count=len(hits),
        documents=[{"id": h.document.id, "title": h.document.title} for h in hits],
        pagination=pagination.to_json() if pagination else None,
    )
