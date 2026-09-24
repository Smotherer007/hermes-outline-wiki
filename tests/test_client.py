from __future__ import annotations

import os

import pytest

from conftest import sub

client = sub("client")
models = sub("models")


def cfg(outline, **extra):
    return models.OutlineConfig(url=outline.url, api_key="ol_api_secret", **extra)


class TestCallOutline:
    def test_posts_to_the_rpc_endpoint_with_a_bearer_token(self, outline):
        outline.ok("auth.info", {"user": {"name": "Neo"}})
        client.call_outline(cfg(outline), "auth.info", {})
        assert outline.methods() == ["auth.info"]
        headers = {k.lower(): v for k, v in outline.headers[0].items()}
        assert headers["authorization"] == "Bearer ol_api_secret"
        assert headers["content-type"] == "application/json"
        assert headers["user-agent"].startswith("hermes-outline-wiki/")

    def test_drops_none_values_instead_of_sending_nulls(self, outline):
        outline.ok("documents.search", [])
        client.call_outline(cfg(outline), "documents.search", {"query": "x", "collectionId": None})
        assert outline.body("documents.search") == {"query": "x"}

    def test_keeps_explicit_nulls_which_documents_move_needs(self, outline):
        outline.ok("documents.move", {"documents": []})
        client.call_outline(cfg(outline), "documents.move", {"id": "d1", "parentDocumentId": client.JSON_NULL})
        assert outline.body("documents.move") == {"id": "d1", "parentDocumentId": None}

    def test_explains_a_401_in_terms_of_the_api_key(self, outline):
        outline.on("auth.info", (401, {"ok": False, "error": "authentication_required"}))
        with pytest.raises(models.OutlineApiError) as err:
            client.call_outline(cfg(outline), "auth.info")
        assert err.value.status == 401
        assert "API key" in str(err.value)
        assert err.value.code == "authentication_required"

    def test_explains_a_403_as_a_permission_problem(self, outline):
        outline.on("documents.info", (403, {"ok": False, "message": "no access"}))
        with pytest.raises(models.OutlineApiError, match=r"denied access \(403\): no access"):
            client.call_outline(cfg(outline), "documents.info")

    def test_explains_a_429_as_rate_limiting(self, outline):
        outline.on("documents.list", (429, {"ok": False}))
        with pytest.raises(models.OutlineApiError, match="rate limit"):
            client.call_outline(cfg(outline), "documents.list")

    def test_recognises_an_html_error_page_as_a_wrong_base_url(self, outline):
        outline.on("auth.info", (404, "<html>nope</html>"))
        with pytest.raises(models.OutlineApiError, match="HTML instead of JSON"):
            client.call_outline(cfg(outline), "auth.info")

    def test_treats_ok_false_as_a_failure_even_on_http_200(self, outline):
        outline.on("auth.info", (200, {"ok": False, "error": "weird"}))
        with pytest.raises(models.OutlineApiError, match="weird"):
            client.call_outline(cfg(outline), "auth.info")

    def test_reports_an_unreachable_host_with_the_workspace_url(self):
        config = models.OutlineConfig(url="http://127.0.0.1:9", api_key="k")
        with pytest.raises(models.OutlineApiError, match=r"Could not reach Outline at http://127.0.0.1:9"):
            client.call_outline(config, "auth.info", timeout=2)

    def test_returns_data_and_pagination(self, outline):
        outline.ok("documents.list", [1, 2], pagination={"offset": 0, "limit": 2})
        res = client.call_outline(cfg(outline), "documents.list")
        assert res.data == [1, 2]
        assert res.pagination.limit == 2


class TestOperations:
    def test_search_documents_maps_hits_to_documents_plus_context(self, outline):
        outline.ok("documents.search", [
            {"ranking": 0.9, "context": "the **failover** runbook", "document": {"id": "d1", "title": "Failover"}},
        ])
        hits, _ = client.search_documents(cfg(outline), query="failover", status_filter=["published"])
        assert hits[0].document.title == "Failover"
        assert hits[0].context == "the **failover** runbook"
        assert hits[0].ranking == 0.9
        body = outline.body("documents.search")
        assert body["limit"] == 15 and body["offset"] == 0 and body["statusFilter"] == ["published"]

    def test_list_documents_switches_to_documents_drafts(self, outline):
        outline.ok("documents.drafts", [])
        client.list_documents(cfg(outline), drafts=True, parent_document_id="p1")
        assert outline.methods() == ["documents.drafts"]
        assert "parentDocumentId" not in outline.body("documents.drafts")

    def test_get_document_turns_a_404_into_not_found(self, outline):
        outline.on("documents.info", (404, {"ok": False, "error": "not_found"}))
        with pytest.raises(models.OutlineNotFoundError, match='Document "nope"'):
            client.get_document(cfg(outline), "nope")

    def test_update_document_forwards_publish(self, outline):
        outline.ok("documents.update", {"id": "d1", "title": "T"})
        client.update_document(cfg(outline), "d1", publish=True)
        assert outline.body("documents.update") == {"id": "d1", "publish": True}

    def test_document_lifecycle_only_sends_permanent_for_delete(self, outline):
        outline.ok("documents.archive", {"id": "d1", "title": "T"})
        outline.ok("documents.delete", {})
        client.document_lifecycle(cfg(outline), "archive", "d1", permanent=True)
        client.document_lifecycle(cfg(outline), "delete", "d1", permanent=True)
        assert outline.body("documents.archive") == {"id": "d1"}
        assert outline.body("documents.delete") == {"id": "d1", "permanent": True}

    def test_create_comment_sends_both_text_and_rich_text_data(self, outline):
        outline.ok("comments.create", {"id": "c1"})
        client.create_comment(cfg(outline), "d1", "hello")
        body = outline.body("comments.create")
        assert body["text"] == "hello"
        assert body["data"]["content"][0]["content"][0]["text"] == "hello"

    def test_export_document_returns_the_markdown_string(self, outline):
        outline.ok("documents.export", "# Title\n\nBody")
        assert client.export_document(cfg(outline), "d1") == "# Title\n\nBody"

    def test_insecure_tls_is_per_profile(self):
        assert client._ssl_context(models.OutlineConfig(url="https://x", api_key="k")) is None
        ctx = client._ssl_context(models.OutlineConfig(url="https://x", api_key="k", insecure_tls=True))
        assert ctx is not None and ctx.check_hostname is False


class TestMapping:
    def test_falls_back_to_untitled_for_an_empty_title(self):
        assert client.to_document_summary({"id": "d1", "title": ""}).title == "Untitled"

    def test_keeps_the_markdown_body(self):
        assert client.to_document_detail({"id": "d1", "text": "# hi"}).text == "# hi"

    def test_defaults_a_missing_body_to_an_empty_string(self):
        assert client.to_document_detail({"id": "d1"}).text == ""

    def test_maps_navigation_nodes_recursively(self):
        node = client.to_navigation_node({"id": "a", "title": "A", "children": [{"id": "b", "title": "B"}]})
        assert node.children[0].title == "B"
        assert node.children[0].children == ()


class TestFlattenRichText:
    def test_returns_a_plain_string_unchanged(self):
        assert client.flatten_rich_text("plain") == "plain"

    def test_returns_empty_for_none(self):
        assert client.flatten_rich_text(None) == ""

    def test_separates_block_nodes_by_newline(self):
        rich = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "one"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "two"}]},
        ]}
        assert client.flatten_rich_text(rich) == "one\ntwo\n"

    def test_prefers_a_server_provided_text_field(self):
        assert client.to_comment({"id": "c", "text": "server", "data": {"type": "text", "text": "x"}}).text == "server"

    def test_falls_back_to_the_rich_text_body(self):
        rich = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hi"}]}]}
        assert client.to_comment({"id": "c", "data": rich}).text == "hi"


class TestSlugify:
    @pytest.mark.parametrize("title, slug", [
        ("Deploy Runbook", "deploy-runbook"),
        ("Übergabe für Kunden", "ubergabe-fur-kunden"),
        ("  What?!  Now...  ", "what-now"),
        ("???", "document"),
    ])
    def test_slugs(self, title, slug):
        assert client.slugify_title(title) == slug

    def test_caps_the_length(self):
        assert len(client.slugify_title("a" * 200)) == 80


class TestWriteMarkdownFile:
    def test_writes_the_file_and_returns_its_absolute_path(self, tmp_path):
        path = client.write_markdown_file(str(tmp_path), "a.md", "x")
        assert os.path.isabs(path) and open(path).read() == "x"

    def test_creates_the_directory_when_missing(self, tmp_path):
        path = client.write_markdown_file(str(tmp_path / "new" / "dir"), "a.md", "x")
        assert os.path.exists(path)

    def test_refuses_a_file_name_that_escapes_the_target_directory(self, tmp_path):
        with pytest.raises(models.UnsafeExportPathError):
            client.write_markdown_file(str(tmp_path / "out"), "../escape.md", "x")
