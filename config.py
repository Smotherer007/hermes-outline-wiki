"""Configuration persistence and state.

Stores named Outline workspace profiles in ``$HERMES_HOME/outline-config.json``
(override with ``OUTLINE_CONFIG``). Because ``HERMES_HOME`` is per Hermes
profile, every Hermes profile gets its own set of wikis.

File format -- identical to pi-outline-wiki, so the same file works for both::

    { "profiles": { "name": {"url": ..., "apiKey": ...}, ... }, "activeProfile": "name" }

A flat ``{ url, apiKey }`` object is migrated to a ``default`` profile.

Environment fallback: ``OUTLINE_URL`` + ``OUTLINE_API_KEY`` (optionally
``OUTLINE_DESCRIPTION``, ``OUTLINE_PROFILE_NAME``) define one more profile
that lives only in memory. That suits containers, where secrets arrive as
environment variables and the agent should not hold them in a file it can edit.
A file profile with the same name wins.

Hermes runs tools on several threads and the gateway and CLI can be separate
processes, so all access goes through a lock and the file is re-read when its
modification time changes.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

from .models import OutlineConfig, OutlineNotConfiguredError

_lock = threading.RLock()

# Mutable state
_profiles: Dict[str, OutlineConfig] = {}
_active: Optional[str] = None
_loaded_mtime: Optional[int] = None
_loaded_path: Optional[Path] = None


# Path resolution


def _hermes_home() -> Path:
    try:  # the documented resolver honours profile overrides; fall back outside Hermes
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:
        home = os.environ.get("HERMES_HOME", "").strip()
        return Path(home).expanduser() if home else Path.home() / ".hermes"


def config_path() -> Path:
    override = os.environ.get("OUTLINE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    return _hermes_home() / "outline-config.json"


# URL normalisation


def normalize_base_url(raw: str) -> str:
    """Accept what people actually paste: a bare host, a trailing slash, the
    ``/api`` base, or the ``/mcp`` endpoint from Outline's MCP docs. Returns the
    workspace root without a trailing slash."""
    url = str(raw if raw is not None else "").strip()
    if not url:
        raise ValueError("Workspace URL must not be empty.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = f"https://{url}"
    url = url.rstrip("/")
    url = re.sub(r"/(api|mcp)$", "", url, flags=re.IGNORECASE)
    url = url.rstrip("/")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or " " in url:
        raise ValueError(f'"{raw}" is not a valid workspace URL.')
    return url


# Environment profile


def _env_profile() -> Optional[tuple]:
    url = os.environ.get("OUTLINE_URL", "").strip()
    key = os.environ.get("OUTLINE_API_KEY", "").strip()
    if not url or not key:
        return None
    name = os.environ.get("OUTLINE_PROFILE_NAME", "").strip() or "default"
    try:
        normalized = normalize_base_url(url)
    except ValueError:
        return None
    description = os.environ.get("OUTLINE_DESCRIPTION", "").strip() or None
    return name, OutlineConfig(url=normalized, api_key=key, description=description)


# Persistence


def _persist() -> None:
    """Write the profile store.

    The file holds plaintext API keys, so it must never be group- or
    world-readable. We write to a private temp file and rename it into place:
    that fixes the mode of an existing file and is atomic, so a crash
    mid-write cannot truncate the config. Environment profiles are never
    written.
    """
    global _loaded_mtime, _loaded_path
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    env = _env_profile()
    file_profiles = {
        name: cfg.to_json()
        for name, cfg in _profiles.items()
        if not (env and name == env[0] and cfg == env[1])
    }
    data = {"profiles": file_profiles, "activeProfile": _active}
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    _loaded_path = path
    try:
        _loaded_mtime = path.stat().st_mtime_ns
    except OSError:
        _loaded_mtime = None


def load_config() -> None:
    """(Re)load profiles from disk and the environment."""
    global _profiles, _active, _loaded_mtime, _loaded_path
    with _lock:
        path = config_path()
        profiles: Dict[str, OutlineConfig] = {}
        active: Optional[str] = None
        migrate = False
        mtime: Optional[int] = None

        try:
            if path.exists():
                mtime = path.stat().st_mtime_ns
                raw = json.loads(path.read_text(encoding="utf-8"))
                # Tighten permissions on files written by older versions or by hand.
                try:
                    if (path.stat().st_mode & 0o777) != 0o600:
                        os.chmod(path, 0o600)
                except OSError:
                    pass

                if isinstance(raw, dict) and raw.get("apiKey") and "profiles" not in raw:
                    profiles = {"default": OutlineConfig.from_json(raw)}
                    active = "default"
                    migrate = True
                elif isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
                    profiles = {
                        str(name): OutlineConfig.from_json(value)
                        for name, value in raw["profiles"].items()
                        if isinstance(value, dict)
                    }
                    requested = raw.get("activeProfile")
                    active = requested if requested in profiles else None
        except Exception:
            profiles, active = {}, None

        env = _env_profile()
        if env and env[0] not in profiles:
            profiles[env[0]] = env[1]
        if active is None and profiles:
            active = next(iter(profiles))

        _profiles, _active = profiles, active
        _loaded_path, _loaded_mtime = path, mtime
        if migrate:
            _persist()


def _refresh_if_changed() -> None:
    """Pick up edits made by another process (e.g. outline_setup in the CLI while the gateway runs)."""
    path = config_path()
    try:
        mtime = path.stat().st_mtime_ns if path.exists() else None
    except OSError:
        mtime = None
    if path != _loaded_path or mtime != _loaded_mtime:
        load_config()


# Access


def get_config() -> Optional[OutlineConfig]:
    with _lock:
        _refresh_if_changed()
        if not _active:
            return None
        return _profiles.get(_active)


def get_config_or_raise() -> OutlineConfig:
    config = get_config()
    if config is None:
        raise OutlineNotConfiguredError()
    return config


def get_profile(name: str) -> Optional[OutlineConfig]:
    with _lock:
        _refresh_if_changed()
        return _profiles.get(name)


def resolve_config(profile_name: Optional[str] = None) -> OutlineConfig:
    """Return the named profile (or raise), or the active one."""
    if profile_name:
        with _lock:
            _refresh_if_changed()
            config = _profiles.get(profile_name)
            if config is None:
                available = ", ".join(_profiles) or "none"
                raise ValueError(f'Profile "{profile_name}" not found. Available: {available}')
            return config
    return get_config_or_raise()


def get_profiles() -> Dict[str, OutlineConfig]:
    with _lock:
        _refresh_if_changed()
        return dict(_profiles)


def get_active_profile() -> Optional[str]:
    with _lock:
        _refresh_if_changed()
        return _active


def is_env_profile(name: str) -> bool:
    env = _env_profile()
    with _lock:
        return bool(env and name == env[0] and _profiles.get(name) == env[1])


# Mutations


def save_profile(name: str, config: OutlineConfig) -> None:
    global _active
    with _lock:
        _refresh_if_changed()
        normalized = OutlineConfig(
            url=normalize_base_url(config.url),
            api_key=config.api_key,
            description=config.description,
            insecure_tls=config.insecure_tls,
        )
        _profiles[name] = normalized
        if not _active or len(_profiles) == 1:
            _active = name
        _persist()


def set_active_profile(name: str) -> None:
    global _active
    with _lock:
        _refresh_if_changed()
        if name not in _profiles:
            available = ", ".join(_profiles) or "none"
            raise ValueError(f'Profile "{name}" does not exist. Available: {available}')
        _active = name
        _persist()


def delete_profile(name: str) -> bool:
    global _active
    with _lock:
        _refresh_if_changed()
        if name not in _profiles:
            return False
        if is_env_profile(name):
            raise ValueError(
                f'Profile "{name}" comes from the OUTLINE_URL / OUTLINE_API_KEY environment '
                "variables. Remove it there instead."
            )
        del _profiles[name]
        if _active == name:
            _active = next(iter(_profiles), None)
        _persist()
        return True


def _reset_for_testing() -> None:
    global _profiles, _active, _loaded_mtime, _loaded_path
    with _lock:
        _profiles, _active = {}, None
        _loaded_mtime, _loaded_path = None, None
