"""Test fixtures.

The plugin is imported the way Hermes imports a directory plugin: as a
package whose ``__init__.py`` lives in the repository root, under a
namespaced module name. That also proves the relative imports work outside
the source tree.

``outline`` is a real HTTP server on localhost that speaks Outline's RPC
shape, so every test goes through the actual urllib client.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple, Union

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "hermes_plugins_test.outline_wiki"


def _load_plugin():
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    parent = "hermes_plugins_test"
    if parent not in sys.modules:
        namespace = importlib.util.module_from_spec(importlib.machinery.ModuleSpec(parent, None, is_package=True))
        namespace.__path__ = []  # type: ignore[attr-defined]
        sys.modules[parent] = namespace
    spec = importlib.util.spec_from_file_location(
        PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


plugin = _load_plugin()


def sub(name: str):
    return importlib.import_module(f"{PACKAGE}.{name}")


Reply = Union[Tuple[int, Any], Callable[[dict], Tuple[int, Any]]]


class FakeOutline:
    """Records every call and answers from a per-method table."""

    def __init__(self) -> None:
        self.routes: Dict[str, Reply] = {}
        self.calls: List[dict] = []
        self.headers: List[dict] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def on(self, method: str, reply: Reply) -> None:
        self.routes[method] = reply

    def ok(self, method: str, data: Any, pagination: Any = None) -> None:
        body = {"ok": True, "data": data}
        if pagination is not None:
            body["pagination"] = pagination
        self.routes[method] = (200, body)

    def methods(self) -> List[str]:
        return [call["method"] for call in self.calls]

    def body(self, method: str) -> dict:
        return next(call["body"] for call in self.calls if call["method"] == method)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8")
                method = self.path.split("/api/", 1)[-1]
                body = json.loads(raw) if raw else {}
                fake.calls.append({"method": method, "body": body})
                fake.headers.append(dict(self.headers))
                reply = fake.routes.get(method, (404, {"ok": False, "error": "not_found", "message": "Not found"}))
                status, payload = reply(body) if callable(reply) else reply
                data = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload).encode("utf-8")
                self.send_response(status)
                content_type = "text/html" if isinstance(payload, str) else "application/json"
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler


@pytest.fixture
def outline():
    fake = FakeOutline()
    yield fake
    fake.close()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Every test gets its own profile file and no environment profile."""
    monkeypatch.setenv("OUTLINE_CONFIG", str(tmp_path / "outline-config.json"))
    for var in ("OUTLINE_URL", "OUTLINE_API_KEY", "OUTLINE_DESCRIPTION", "OUTLINE_PROFILE_NAME"):
        monkeypatch.delenv(var, raising=False)
    config = sub("config")
    config._reset_for_testing()
    yield tmp_path / "outline-config.json"
    config._reset_for_testing()


@pytest.fixture
def configured(outline):
    """One workspace 'work' pointing at the fake server."""
    config = sub("config")
    models = sub("models")
    config.save_profile("work", models.OutlineConfig(url=outline.url, api_key="ol_api_testkey1234"))
    return outline


def call(tool: str, args: dict | None = None) -> dict:
    """Invoke a tool handler the way Hermes does and decode its JSON result."""
    module = sub(f"tools.{tool}")
    raw = module.handle(args or {}, task_id="t1", session_id="s1")
    assert isinstance(raw, str), "handlers must return a JSON string"
    return json.loads(raw)


def doc(id: str = "d1", title: str = "Doc", text: str = "", **extra: Any) -> dict:
    return {"id": id, "title": title, "text": text, "publishedAt": "2026-09-01T10:00:00Z", **extra}
