"""Anonymous visitor sessions.

A visitor gets a session the first time they upload a document. The server
generates the session ID (256 random bits) and sends it in an HttpOnly,
SameSite=Strict cookie; JavaScript never sees it. The server stores only a
hash of the ID (the *owner key*), and every document records the owner key of
the session that uploaded it. Possession of the cookie is what grants access
to those documents, so:

* clients cannot pick an identity: an unknown or malformed cookie is simply
  "no session", and a new random ID is issued on the next upload;
* a leaked copy of ``sessions.json`` or the document registry does not reveal
  any usable cookie value;
* DOCMIND_API_TOKEN plays no part in visitor identity.

Sessions expire after ``SESSION_TTL_HOURS`` without activity; the service then
deletes their documents (see ``DocMindService.expire_sessions``). The store
is persisted to ``DATA_DIR/sessions.json`` so ownership survives a restart
when the disk does.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Callable

from app.utils import atomic_write_json, read_json

logger = logging.getLogger(__name__)

SESSIONS_FILE = "sessions.json"
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{43}$")  # secrets.token_urlsafe(32)
# last_seen is persisted lazily; this bounds how stale it can be on disk.
_FLUSH_INTERVAL_SECONDS = 300


class SessionCapacityError(Exception):
    """The server already holds the maximum number of active sessions."""


def owner_key(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()[:32]


class SessionStore:
    def __init__(
        self,
        path: Path,
        ttl_seconds: float,
        max_sessions: int,
        clock: Callable[[], float] = time.time,
    ):
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, float]] = {}
        self._dirty_since: float | None = None
        try:
            raw = read_json(path, default={}) or {}
            self._sessions = {
                key: {"created": float(v["created"]), "last_seen": float(v["last_seen"])}
                for key, v in raw.items()
                if isinstance(v, dict) and re.fullmatch(r"[0-9a-f]{32}", key)
            }
        except (OSError, ValueError, TypeError, KeyError) as exc:
            # Losing sessions only means visitors lose access to their uploads;
            # the expiry sweep then removes those orphaned documents.
            logger.error("Ignoring unreadable %s (%s); starting with no sessions", path, exc.__class__.__name__)
            self._sessions = {}

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def owners(self) -> set[str]:
        with self._lock:
            return set(self._sessions)

    def resolve(self, session_id: str | None) -> str | None:
        """Owner key for a valid, unexpired session ID; ``None`` otherwise. Refreshes activity."""
        if not session_id or not _SESSION_ID.match(session_id):
            return None
        key = owner_key(session_id)
        now = self._clock()
        with self._lock:
            entry = self._sessions.get(key)
            if entry is None or now - entry["last_seen"] > self.ttl_seconds:
                return None
            entry["last_seen"] = now
            self._mark_dirty(now)
        return key

    def create(self) -> tuple[str, str]:
        """Issue a new session. Returns (session_id for the cookie, owner key)."""
        now = self._clock()
        with self._lock:
            if self.max_sessions and len(self._sessions) >= self.max_sessions:
                self._drop_expired(now)
                if len(self._sessions) >= self.max_sessions:
                    raise SessionCapacityError
            session_id = secrets.token_urlsafe(32)
            key = owner_key(session_id)
            self._sessions[key] = {"created": now, "last_seen": now}
            self._save()
        return session_id, key

    def expire(self) -> list[str]:
        """Remove expired sessions; return their owner keys. Also flushes activity to disk."""
        now = self._clock()
        with self._lock:
            expired = self._drop_expired(now)
            if expired or (self._dirty_since is not None and now - self._dirty_since >= _FLUSH_INTERVAL_SECONDS):
                self._save()
        return expired

    def flush(self) -> None:
        with self._lock:
            if self._dirty_since is not None:
                self._save()

    def _drop_expired(self, now: float) -> list[str]:
        expired = [k for k, v in self._sessions.items() if now - v["last_seen"] > self.ttl_seconds]
        for key in expired:
            del self._sessions[key]
        return expired

    def _mark_dirty(self, now: float) -> None:
        if self._dirty_since is None:
            self._dirty_since = now

    def _save(self) -> None:
        atomic_write_json(self.path, self._sessions)
        self._dirty_since = None
