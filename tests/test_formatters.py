from __future__ import annotations

from conftest import sub

f = sub("formatters")
m = sub("models")


def summary(**kw):
    base = dict(id="d1", title="Doc", published_at="2026-09-01T10:00:00Z")
    base.update(kw)
    return m.DocumentSummary(**base)


def test_mask_api_key():
    assert f.mask_api_key("") == "(none)"
    assert f.mask_api_key("short") == "****"
    assert f.mask_api_key("ol_api_abcdefghijkl1234") == "ol_api_...1234"


def test_short_date():
    assert f.short_date("2026-09-02T08:25:13.123Z") == "2026-09-02 08:25"
    assert f.short_date(None) == "-"
    assert f.short_date("garbage") == "garbage"


def test_status_markers():
    assert f.status_markers(summary()) == ""
    assert f.status_markers(summary(published_at=None)) == " [draft]"
    assert f.status_markers(summary(archived_at="x")) == " [archived]"
    assert f.status_markers(summary(deleted_at="x", template=True)) == " [trashed,template]"


def test_profile_status_marks_active_and_shows_descriptions():
    profiles = {
        "work": m.OutlineConfig(url="https://a", api_key="ol_api_aaaaaaaa1111", description="internal"),
        "client": m.OutlineConfig(url="https://b", api_key="ol_api_bbbbbbbb2222", insecure_tls=True),
    }
    text = f.format_profile_status(profiles, "work", env_profiles=["client"])
    assert "* work: https://a key ol_api_...1111" in text
    assert "    internal" in text
    assert "(TLS validation off) (from environment)" in text
    assert "allProfiles: true" in text
    assert "ol_api_aaaaaaaa1111" not in text


def test_profile_status_when_empty():
    assert "No Outline workspace configured" in f.format_profile_status({}, None)


def test_search_results_with_pagination_hint():
    hits = [m.SearchHit(document=summary(), context="  some\n context ")]
    text = f.format_search_results(hits, "q", m.Pagination(offset=0, limit=1))
    assert 'Search "q" -- 1 result(s)' in text
    assert "   some context" in text
    assert "Re-run with offset 1." in text


def test_search_results_empty():
    assert 'No documents match "q"' in f.format_search_results([], "q")


def test_document_truncation():
    detail = m.DocumentDetail(id="d1", title="T", text="x" * 50, published_at="2026-01-01T00:00:00Z")
    text = f.format_document(detail, max_chars=10)
    assert text.endswith("[truncated after 10 characters -- re-run outline_read with a larger maxChars to see the rest]")
    assert "x" * 11 not in text


def test_collection_structure_nests():
    tree = [m.NavigationNode(id="a", title="A", children=(m.NavigationNode(id="b", title="B"),))]
    assert f.format_collection_structure(tree, "Eng") == 'Document tree of "Eng":\n- A (id a)\n  - B (id b)'
    assert f.count_nodes(tree) == 2


def test_comments_are_threaded():
    comments = [
        m.CommentEntry(id="c1", text="root", created_by=m.UserRef(name="Ann")),
        m.CommentEntry(id="c2", text="reply", parent_comment_id="c1", resolved_at="x"),
    ]
    text = f.format_comments(comments, "d1")
    assert "- Ann at - (id c1)\n  root\n  - unknown at - [resolved] (id c2)\n    reply" in text
