from __future__ import annotations

import json
import os
import stat

import pytest

from conftest import sub

config = sub("config")
models = sub("models")


def profile(url="https://wiki.example.com", key="ol_api_x", **extra):
    return models.OutlineConfig(url=url, api_key=key, **extra)


class TestNormalizeBaseUrl:
    @pytest.mark.parametrize("raw, expected", [
        ("acme.getoutline.com", "https://acme.getoutline.com"),
        ("https://wiki.example.com/", "https://wiki.example.com"),
        ("https://wiki.example.com/api", "https://wiki.example.com"),
        ("https://wiki.example.com/mcp/", "https://wiki.example.com"),
        ("http://localhost:3000", "http://localhost:3000"),
    ])
    def test_accepts_what_people_paste(self, raw, expected):
        assert config.normalize_base_url(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", "https://", "not a url"])
    def test_rejects_garbage(self, raw):
        with pytest.raises(ValueError):
            config.normalize_base_url(raw)


class TestPersistence:
    def test_first_profile_becomes_active(self, isolated_config):
        config.save_profile("work", profile())
        assert config.get_active_profile() == "work"

    def test_later_profiles_do_not_steal_the_active_slot(self):
        config.save_profile("work", profile())
        config.save_profile("client", profile(url="https://client.example.com"))
        assert config.get_active_profile() == "work"

    def test_writes_the_pi_file_format_with_0600(self, isolated_config):
        config.save_profile("work", profile(description="internal", insecure_tls=True))
        data = json.loads(isolated_config.read_text())
        assert data == {
            "profiles": {"work": {
                "url": "https://wiki.example.com", "apiKey": "ol_api_x",
                "description": "internal", "insecureTls": True,
            }},
            "activeProfile": "work",
        }
        assert stat.S_IMODE(os.stat(isolated_config).st_mode) == 0o600

    def test_reads_a_file_written_by_pi(self, isolated_config):
        isolated_config.write_text(json.dumps({
            "profiles": {"a": {"url": "https://a.example.com", "apiKey": "k1"},
                         "b": {"url": "https://b.example.com", "apiKey": "k2", "description": "B wiki"}},
            "activeProfile": "b",
        }))
        config.load_config()
        assert config.get_active_profile() == "b"
        assert config.get_profile("b").description == "B wiki"

    def test_migrates_a_flat_legacy_file(self, isolated_config):
        isolated_config.write_text(json.dumps({"url": "https://a.example.com", "apiKey": "k"}))
        config.load_config()
        assert config.get_active_profile() == "default"
        assert "profiles" in json.loads(isolated_config.read_text())

    def test_tightens_loose_permissions(self, isolated_config):
        isolated_config.write_text(json.dumps({"profiles": {}, "activeProfile": None}))
        os.chmod(isolated_config, 0o644)
        config.load_config()
        assert stat.S_IMODE(os.stat(isolated_config).st_mode) == 0o600

    def test_picks_up_changes_from_another_process(self, isolated_config):
        config.save_profile("work", profile())
        data = json.loads(isolated_config.read_text())
        data["profiles"]["other"] = {"url": "https://o.example.com", "apiKey": "k"}
        data["activeProfile"] = "other"
        isolated_config.write_text(json.dumps(data))
        os.utime(isolated_config, ns=(1, 1))  # guarantee a different mtime
        assert config.get_active_profile() == "other"

    def test_survives_a_corrupt_file(self, isolated_config):
        isolated_config.write_text("{not json")
        config.load_config()
        assert config.get_profiles() == {}


class TestProfiles:
    def test_resolve_named_or_active(self):
        config.save_profile("work", profile())
        assert config.resolve_config().url == "https://wiki.example.com"
        assert config.resolve_config("work").api_key == "ol_api_x"

    def test_resolve_unknown_lists_available(self):
        config.save_profile("work", profile())
        with pytest.raises(ValueError, match="Available: work"):
            config.resolve_config("nope")

    def test_not_configured(self):
        with pytest.raises(models.OutlineNotConfiguredError):
            config.resolve_config()

    def test_delete_moves_the_active_slot(self):
        config.save_profile("a", profile())
        config.save_profile("b", profile())
        assert config.delete_profile("a") is True
        assert config.get_active_profile() == "b"
        assert config.delete_profile("a") is False


class TestEnvironmentProfile:
    def test_env_vars_define_a_profile(self, monkeypatch, isolated_config):
        monkeypatch.setenv("OUTLINE_URL", "wiki.example.com/api")
        monkeypatch.setenv("OUTLINE_API_KEY", "ol_api_env")
        monkeypatch.setenv("OUTLINE_DESCRIPTION", "company wiki")
        config.load_config()
        assert config.get_active_profile() == "default"
        assert config.get_config().url == "https://wiki.example.com"
        assert config.is_env_profile("default")

    def test_env_profile_is_never_written_to_disk(self, monkeypatch, isolated_config):
        monkeypatch.setenv("OUTLINE_URL", "https://env.example.com")
        monkeypatch.setenv("OUTLINE_API_KEY", "ol_api_env")
        config.load_config()
        config.save_profile("work", profile())
        assert "ol_api_env" not in isolated_config.read_text()

    def test_env_profile_cannot_be_deleted(self, monkeypatch):
        monkeypatch.setenv("OUTLINE_URL", "https://env.example.com")
        monkeypatch.setenv("OUTLINE_API_KEY", "ol_api_env")
        config.load_config()
        with pytest.raises(ValueError, match="environment"):
            config.delete_profile("default")

    def test_a_file_profile_with_the_same_name_wins(self, monkeypatch, isolated_config):
        isolated_config.write_text(json.dumps({
            "profiles": {"default": {"url": "https://file.example.com", "apiKey": "k"}},
            "activeProfile": "default",
        }))
        monkeypatch.setenv("OUTLINE_URL", "https://env.example.com")
        monkeypatch.setenv("OUTLINE_API_KEY", "ol_api_env")
        config.load_config()
        assert config.get_config().url == "https://file.example.com"
