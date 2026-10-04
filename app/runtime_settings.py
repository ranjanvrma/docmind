"""Settings that can be changed at runtime from the UI.

Values saved through ``PATCH /api/settings`` are written to
``<DATA_DIR>/settings.json`` and override the environment (.env). They are
validated with the same rules as startup configuration and applied without
a restart. "Reset to defaults" deletes the file, returning to the environment
values.

Deliberately *not* editable here:
  * embedding_model - changing it requires rebuilding the whole index;
  * api_token, cors_allow_origins - security boundaries stay in the server's
    environment, so a UI session can never widen its own access;
  * data_dir, web_dist_dir, log_level - deployment concerns.

The LLM API key is write-only: it can be set or removed but is never returned.
A key from the environment is only ever sent to the environment's provider and
base URL; pointing the app at another endpoint from the UI requires entering a
key for it too, so a token holder cannot redirect the server's key elsewhere.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import json
import logging
import socket
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from app.config import Settings
from app.utils import atomic_write_json

logger = logging.getLogger(__name__)

OVERRIDES_FILE = "settings.json"

# name -> python type used for coercion
EDITABLE: dict[str, type] = {
    "llm_provider": str,
    "llm_model": str,
    "llm_base_url": str,
    "llm_effort": str,
    "llm_max_tokens": int,
    "llm_temperature": float,
    "llm_timeout_seconds": float,
    "llm_api_key": str,  # write-only
    "max_context_chars": int,
    "top_k": int,
    "min_relevance": float,
    "chunk_size": int,
    "chunk_overlap": int,
    "min_chars_per_page": int,
    "max_upload_mb": int,
    "max_request_mb": int,
    "max_pages": int,
    "classifier_labels": list,
}
SECRET = {"llm_api_key"}
LLM_FIELDS = {k for k in EDITABLE if k.startswith("llm_")}
ENDPOINT_FIELDS = ("llm_provider", "llm_base_url")
INDEXING_FIELDS = {"chunk_size", "chunk_overlap", "min_chars_per_page"}


def overrides_path(settings: Settings) -> Path:
    return settings.data_dir / OVERRIDES_FILE


def _coerce(name: str, value: Any) -> Any:
    expected = EDITABLE[name]
    if expected is list:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{name} must be a list of strings")
        cleaned = [v.strip() for v in value if v.strip()]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError(f"{name} contains duplicates")
        return cleaned
    if expected is str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        value = value.strip()
        return value.lower() if name in {"llm_provider", "llm_effort"} else value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if expected is int and float(value) != int(value):
        raise ValueError(f"{name} must be a whole number")
    return expected(value)


def check_public_endpoint(url: str) -> None:
    """Reject LLM base URLs that would make the server call private addresses.

    Applied in production to base URLs set through the API (the operator's own
    LLM_BASE_URL is trusted). Without it, anyone holding the access token could
    point the server at internal services or cloud metadata endpoints (SSRF).
    DNS is checked when the setting is saved; DNS rebinding afterwards is not
    covered (see docs/SECURITY.md).
    """
    if not url:
        return
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("In production, an LLM base URL set from the UI must be an https:// URL")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"LLM base URL host '{parts.hostname}' could not be resolved") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global:
            raise ValueError("LLM base URL must point to a public host, not a private, loopback or link-local address")


def apply_changes(settings: Settings, changes: dict[str, Any]) -> tuple[Settings, dict[str, Any]]:
    """Validate ``changes`` against ``settings``; return (new settings, coerced changes).

    Raises ValueError with a user-facing message on any invalid value.
    """
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise ValueError(f"These settings cannot be changed here: {', '.join(sorted(unknown))}")
    coerced = {name: _coerce(name, value) for name, value in changes.items()}
    updated = dataclasses.replace(settings, **coerced)
    updated.validate()
    if settings.app_env == "production" and coerced.get("llm_base_url"):
        check_public_endpoint(coerced["llm_base_url"])
    return updated, coerced


def env_key_withheld(settings: Settings, overrides: dict[str, Any], env_settings: Settings) -> bool:
    """True if the environment's key must not be used because the endpoint was changed."""
    return (
        "llm_api_key" not in overrides
        and bool(env_settings.llm_api_key)
        and any(getattr(settings, f) != getattr(env_settings, f) for f in ENDPOINT_FIELDS)
    )


def resolve(env_settings: Settings, overrides: dict[str, Any]) -> Settings:
    """Environment settings plus validated overrides, with the key bound to its endpoint."""
    settings, _ = apply_changes(env_settings, overrides)
    if env_key_withheld(settings, overrides, env_settings):
        return dataclasses.replace(settings, llm_api_key="")
    return settings


def load_overrides(settings: Settings) -> tuple[Settings, dict[str, Any]]:
    """Apply saved overrides on top of environment settings.

    A missing file means no overrides. An unreadable or invalid file is
    ignored with an error in the log (the app still starts on .env values).
    """
    path = overrides_path(settings)
    if not path.exists():
        return settings, {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            raise ValueError("expected a JSON object")
        _, coerced = apply_changes(settings, saved)
        updated = resolve(settings, coerced)
    except (OSError, ValueError) as exc:
        logger.error("Ignoring %s: %s. Using environment settings.", path, exc)
        return settings, {}
    logger.info("Applied %d saved setting override(s) from %s", len(coerced), path)
    return updated, coerced


def save_overrides(settings: Settings, overrides: dict[str, Any]) -> None:
    atomic_write_json(overrides_path(settings), overrides)


def public_view(settings: Settings, overrides: dict[str, Any], env_settings: Settings) -> dict[str, Any]:
    """Every editable value except secrets, plus where each value comes from."""
    values = {name: getattr(settings, name) for name in EDITABLE if name not in SECRET}
    return {
        "values": values,
        "overridden": sorted(k for k in overrides if k not in SECRET),
        "llm_api_key": {
            "configured": bool(settings.llm_api_key),
            "source": "settings" if "llm_api_key" in overrides else ("environment" if env_settings.llm_api_key else None),
            # The environment key exists but is not sent to a provider/base URL changed here.
            "withheld": env_key_withheld(settings, overrides, env_settings),
        },
        "read_only": {
            "embedding_model": settings.embedding_model,
            "auth_required": bool(settings.api_token),
            "cors_origins": len(settings.cors_allow_origins),
        },
    }
