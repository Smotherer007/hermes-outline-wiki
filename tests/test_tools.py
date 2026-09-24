from __future__ import annotations

import os

import pytest

from conftest import call, doc, sub

config = sub("config")
models = sub("models")


class TestResultContract:
    def test_errors_come_back_as_json_never_raised(self, configured):
        out = call("outline_search", {"query": ""})
        assert out == {"error": "query must not be empty."}

    def test_not_configured(self):
        out = call("outline_list")
        assert "outline_setup" in out["error"]

    def test_numbers_and_booleans_as_strings_are_accepted(self, configured):
        configured.ok("documents.list", [])
        call("outline_list", {"limit": "5", "drafts": "false"})
        assert configured.body("documents.list")["limit"] == 5


class TestSearch:
    def test_rejects_an_unknown_status_filter(self, configured):
        assert "Invalid statusFilter" in call("outline_search", {"query": "x", "statusFilter": ["gone"]})["error"]

    def test_rejects_an_unknown_date_filter(self, configured):
        assert "Invalid dateFilter" in call("outline_search", {"query": "x", "dateFilter": "decade"})["error"]

    def test_passes_filters_through_and_reports_the_hits(self, configured):
        configured.ok("documents.search", [{"context": "ctx", "document": doc("d1", "Failover")}])
        out = call("outline_search", {
            "query": " failover ", "collectionId": "c1", "statusFilter": ["published", "archived"],
            "dateFilter": "month",
        })
        body = configured.body("documents.search")
        assert body["query"] == "failover" and body["collectionId"] == "c1"
        assert body["statusFilter"] == ["published", "archived"] and body["dateFilter"] == "month"
        assert out["count"] == 1 and out["documents"] == [{"id": "d1", "title": "Failover"}]
        assert "1. Failover" in out["result"]


class TestSearchAcrossWorkspaces:
    @pytest.fixture
    def two(self, outline):
        from conftest import FakeOutline

        other = FakeOutline()
        config.save_profile("firma", models.OutlineConfig(url=outline.url, api_key="k1", description="internal"))
        config.save_profile("kunde-a", models.OutlineConfig(url=other.url, api_key="k2", description="ACME docs"))
        yield outline, other
        other.close()

    def test_rejects_combining_profile_with_all_profiles(self, two):
        assert "contradict" in call("outline_search", {"query": "x", "allProfiles": True, "profile": "firma"})["error"]

    def test_rejects_workspace_specific_id_filters(self, two):
        out = call("outline_search", {"query": "x", "allProfiles": True, "collectionId": "c1"})
        assert "specific to one workspace" in out["error"]

    def test_searches_every_workspace_and_labels_hits(self, two):
        first, second = two
        first.ok("documents.search", [{"context": "", "document": doc("a1", "Ours")}])
        second.ok("documents.search", [{"context": "", "document": doc("b1", "Theirs")}])
        out = call("outline_search", {"query": "x", "allProfiles": True})
        assert out["searchedProfiles"] == ["firma", "kunde-a"]
        assert {"id": "b1", "title": "Theirs", "profile": "kunde-a"} in out["documents"]
        assert "[kunde-a (ACME docs)] 1 result(s)" in out["result"]

    def test_reports_a_failing_workspace_without_losing_the_rest(self, two):
        first, second = two
        first.ok("documents.search", [{"context": "", "document": doc("a1", "Ours")}])
        second.on("documents.search", (401, {"ok": False}))
        out = call("outline_search", {"query": "x", "allProfiles": True})
        assert out["failedProfiles"] == ["kunde-a"]
        assert out["count"] == 1
        assert "could not be searched" in out["result"]

    def test_says_so_when_nothing_matches_anywhere(self, two):
        for fake in two:
            fake.ok("documents.search", [])
        out = call("outline_search", {"query": "x", "allProfiles": True})
        assert "in any of the 2 configured workspace(s)" in out["result"]


class TestList:
    def test_rejects_an_unknown_sort_field(self, configured):
        assert "Invalid sort" in call("outline_list", {"sort": "size"})["error"]

    def test_rejects_a_bad_direction(self, configured):
        assert "Invalid direction" in call("outline_list", {"direction": "up"})["error"]

    def test_labels_drafts_in_the_heading(self, configured):
        configured.ok("documents.drafts", [doc(publishedAt=None)])
        assert call("outline_list", {"drafts": True})["result"].startswith("Drafts (1):")


class TestCreate:
    def test_rejects_an_empty_title(self, configured):
        assert call("outline_create", {"title": "  "})["error"] == "title must not be empty."

    def test_refuses_to_publish_without_a_destination(self, configured):
        assert "needs a collectionId" in call("outline_create", {"title": "T"})["error"]
        assert configured.calls == []

    def test_allows_an_unpublished_draft_without_a_destination(self, configured):
        configured.ok("documents.create", doc(publishedAt=None))
        out = call("outline_create", {"title": "T", "publish": False})
        assert configured.body("documents.create") == {"title": "T", "text": "", "publish": False}
        assert out["published"] is False


class TestUpdate:
    def test_rejects_an_unknown_mode(self, configured):
        assert "Invalid mode" in call("outline_update", {"id": "d1", "text": "x", "mode": "merge"})["error"]

    def test_refuses_a_no_op_update(self, configured):
        assert "Nothing to update" in call("outline_update", {"id": "d1"})["error"]

    def test_replaces_the_body_without_reading_it_first(self, configured):
        configured.ok("documents.update", doc(text="new"))
        call("outline_update", {"id": "d1", "text": "new"})
        assert configured.methods() == ["documents.update"]

    def test_appends_after_the_existing_body(self, configured):
        configured.ok("documents.info", doc(text="old\n\n  "))
        configured.ok("documents.update", doc())
        call("outline_update", {"id": "d1", "text": "added", "mode": "append"})
        assert configured.body("documents.update")["text"] == "old\n\nadded\n"

    def test_prepends_before_the_existing_body(self, configured):
        configured.ok("documents.info", doc(text="\n old"))
        configured.ok("documents.update", doc())
        call("outline_update", {"id": "d1", "text": "notice", "mode": "prepend"})
        assert configured.body("documents.update")["text"] == "notice\n\nold"

    def test_publishes_a_draft_without_touching_the_body(self, configured):
        configured.ok("documents.update", doc())
        call("outline_update", {"id": "d1", "publish": True})
        assert configured.body("documents.update") == {"id": "d1", "publish": True}


class TestMove:
    def test_requires_a_target(self, configured):
        assert "Specify a target" in call("outline_move", {"id": "d1"})["error"]

    def test_rejects_contradictory_targets(self, configured):
        assert "contradict" in call("outline_move", {"id": "d1", "parentDocumentId": "p", "toTopLevel": True})["error"]

    def test_clears_the_parent_and_keeps_the_current_collection(self, configured):
        configured.ok("documents.info", doc(collectionId="c9"))
        configured.ok("documents.move", {"documents": [{}, {}]})
        out = call("outline_move", {"id": "d1", "toTopLevel": True})
        assert configured.body("documents.move") == {"id": "d1", "collectionId": "c9", "parentDocumentId": None}
        assert out["documentCount"] == 2
        assert "root of collection c9" in out["result"]

    def test_nests_under_a_parent_without_an_extra_lookup(self, configured):
        configured.ok("documents.move", {"documents": [{}]})
        call("outline_move", {"id": "d1", "parentDocumentId": "p1"})
        assert configured.methods() == ["documents.move"]


class TestArchiveAndDelete:
    def test_rejects_an_unknown_action(self, configured):
        assert "Unknown action" in call("outline_archive", {"id": "d1", "action": "burn"})["error"]

    def test_accepts_unarchive_as_an_alias_for_restore(self, configured):
        configured.ok("documents.restore", doc(title="Back"))
        out = call("outline_archive", {"id": "d1", "action": "unarchive"})
        assert out["action"] == "restore" and "Back restored" in out["result"]

    def test_archives_by_default(self, configured):
        configured.ok("documents.archive", doc())
        call("outline_archive", {"id": "d1"})
        assert configured.methods() == ["documents.archive"]

    def test_trashes_by_default_and_explains_how_to_restore(self, configured):
        configured.ok("documents.info", doc(title="Old page"))
        configured.ok("documents.delete", {})
        out = call("outline_delete", {"id": "d1"})
        assert configured.body("documents.delete") == {"id": "d1"}
        assert 'Moved "Old page" (d1) to the trash' in out["result"]

    def test_warns_that_permanent_deletion_cannot_be_undone(self, configured):
        configured.ok("documents.info", doc(title="Old page"))
        configured.ok("documents.delete", {})
        out = call("outline_delete", {"id": "d1", "permanent": True})
        assert configured.body("documents.delete")["permanent"] is True
        assert "cannot be undone" in out["result"]


class TestComments:
    def test_rejects_empty_text(self, configured):
        assert call("outline_comment", {"documentId": "d1", "text": " "})["error"] == "text must not be empty."

    def test_labels_a_threaded_reply(self, configured):
        configured.ok("comments.create", {"id": "c2"})
        out = call("outline_comment", {"documentId": "d1", "text": "yes", "parentCommentId": "c1"})
        assert out["result"].startswith("Reply posted on document d1.")

    def test_counts_unresolved_threads(self, configured):
        configured.ok("comments.list", [{"id": "c1", "text": "a"}, {"id": "c2", "text": "b", "resolvedAt": "x"}])
        out = call("outline_comments", {"documentId": "d1"})
        assert out["count"] == 2 and out["unresolved"] == 1


class TestReadAndExport:
    def test_read_truncates_but_saves_the_full_body(self, configured, tmp_path):
        configured.ok("documents.info", doc(title="Long Page", text="x" * 100))
        out = call("outline_read", {"id": "d1", "maxChars": 10, "saveDir": str(tmp_path)})
        assert out["truncated"] is True
        assert open(out["savedPath"]).read() == "# Long Page\n\n" + "x" * 100 + "\n"

    def test_read_lists_children(self, configured):
        configured.ok("documents.info", doc())
        configured.ok("documents.list", [doc("k1", "Kid")])
        out = call("outline_read", {"id": "d1", "includeChildren": True})
        assert out["childCount"] == 1
        assert configured.body("documents.list")["parentDocumentId"] == "d1"

    def test_export_requires_exactly_one_source(self, configured, tmp_path):
        assert "either" in call("outline_export", {"targetDir": str(tmp_path)})["error"]
        assert "not both" in call("outline_export", {"targetDir": str(tmp_path), "documentId": "a", "collectionId": "b"})["error"]

    def test_export_writes_one_file_per_document_and_keeps_duplicates(self, configured, tmp_path):
        configured.ok("collections.documents", [
            {"id": "aaaaaaaa1", "title": "Overview", "children": [{"id": "bbbbbbbb2", "title": "Overview"}]},
            {"id": "c3", "title": "Runbook"},
        ])
        configured.on("documents.export", lambda body: (200, {"ok": True, "data": f"# {body['id']}"}))
        target = tmp_path / "out"
        out = call("outline_export", {"targetDir": str(target), "collectionId": "c1", "limit": 2})
        assert sorted(os.listdir(target)) == ["overview-bbbbbbbb.md", "overview.md"]
        assert out["writtenCount"] == 2 and out["skipped"] == 1
        assert "1 more document(s) not exported (limit 2)" in out["result"]


class TestProfileSetupStatus:
    def test_setup_normalizes_saves_and_verifies(self, outline):
        outline.ok("auth.info", {"user": {"name": "Neo", "email": "neo@example.com"}, "team": {"name": "ACME"}})
        out = call("outline_setup", {"name": "work", "url": outline.url + "/api/", "apiKey": " ol_api_k ",
                                     "description": " internal wiki "})
        assert out["verified"] is True and out["url"] == outline.url
        assert "Authenticated as: Neo <neo@example.com>" in out["result"]
        saved = config.get_profile("work")
        assert saved.api_key == "ol_api_k" and saved.description == "internal wiki"

    def test_setup_still_saves_when_the_connection_test_fails(self, outline):
        outline.on("auth.info", (401, {"ok": False}))
        out = call("outline_setup", {"name": "work", "url": outline.url, "apiKey": "bad"})
        assert out["verified"] is False and "connection test failed" in out["result"]
        assert config.get_profile("work") is not None

    def test_status_reports_profiles_and_connection(self, configured):
        configured.ok("auth.info", {"team": {"name": "ACME"}})
        out = call("outline_status")
        assert out["reachable"] is True and "Workspace: ACME" in out["result"]

    def test_status_does_not_fail_when_unreachable(self, configured):
        configured.on("auth.info", (500, {"ok": False}))
        out = call("outline_status")
        assert out["reachable"] is False and "Connection test failed" in out["result"]

    def test_profile_actions(self, configured):
        assert "work" in call("outline_profile")["result"]
        assert "requires a profile name" in call("outline_profile", {"action": "use"})["error"]
        assert "Unknown action" in call("outline_profile", {"action": "rename", "name": "x"})["error"]
        assert call("outline_profile", {"action": "delete", "name": "ghost"})["deleted"] is False

    def test_collections_and_structure(self, configured):
        configured.ok("collections.list", [{"id": "c1", "name": "Engineering"}])
        configured.ok("collections.documents", [{"id": "a", "title": "A", "children": [{"id": "b", "title": "B"}]}])
        assert call("outline_collections")["collections"] == [{"id": "c1", "name": "Engineering"}]
        out = call("outline_structure", {"collectionId": "c1"})
        assert out["collectionName"] == "Engineering" and out["totalCount"] == 2

    def test_structure_renders_even_when_the_name_lookup_fails(self, configured):
        configured.ok("collections.documents", [{"id": "a", "title": "A"}])
        configured.on("collections.list", (500, {"ok": False}))
        out = call("outline_structure", {"collectionId": "c1"})
        assert out["result"] == "Document tree:\n- A (id a)"
