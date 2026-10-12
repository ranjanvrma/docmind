"""In-process rate limiting for anonymous public use.

A sliding-window counter per key (for example ``"qa:ip:203.0.113.7"``). Every
public request is counted against the client's IP address *and* its session,
so neither dropping the cookie nor sharing it across machines escapes the
limits.

This lives in process memory, which is correct for DocMind's single-process,
single-instance deployment (one Render instance, one Uvicorn worker). With
several instances each would count separately; a shared store (e.g. Redis) or
the platform's own rate limiting would then be needed. Counters reset when
the process restarts.
"""

from __future__ import annotations

import ipaddress
import math
import threading
import time
from collections import deque
from typing import Callable

from starlette.requests import Request

# Keys idle for longer than the longest window are dropped; this caps memory.
_MAX_KEYS = 100_000


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def hit(self, key: str, limit: int, window: float, cost: int = 1) -> float | None:
        """Record ``cost`` events for ``key``.

        Returns ``None`` if allowed, or the number of seconds until enough
        capacity frees up. A rejected attempt is not recorded. ``limit <= 0``
        disables the limit.
        """
        if limit <= 0:
            return None
        now = self._clock()
        with self._lock:
            events = self._hits.setdefault(key, deque())
            while events and now - events[0] >= window:
                events.popleft()
            if len(events) + cost > limit:
                if cost > limit:
                    return window
                # Oldest events that must expire before this request fits.
                release_at = events[len(events) + cost - limit - 1] + window
                return max(release_at - now, 0.0)
            events.extend([now] * cost)
            self._calls += 1
            if self._calls % 1000 == 0 or len(self._hits) > _MAX_KEYS:
                self._sweep(now, window)
        return None

    def _sweep(self, now: float, window: float) -> None:
        horizon = max(window, 3600.0)
        for key in [k for k, ev in self._hits.items() if not ev or now - ev[-1] >= horizon]:
            del self._hits[key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._hits)


def retry_after_header(seconds: float) -> dict[str, str]:
    return {"Retry-After": str(max(1, math.ceil(seconds)))}


FORWARDING_HEADERS = ("x-forwarded-for", "cf-connecting-ip", "true-client-ip", "x-real-ip", "forwarded")


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: Request, trusted_proxy_count: int, client_ip_header: str = "") -> str:
    """The client's IP address for rate limiting.

    * ``client_ip_header`` (e.g. ``cf-connecting-ip``): a single-value header
      that the platform's edge proxy sets itself and overwrites if a client
      sends it. Only configure a header your proxy is documented to overwrite.
    * Otherwise, with ``trusted_proxy_count = n``, the n-th entry from the right
      of X-Forwarded-For, i.e. the one appended by the outermost proxy we trust.
      Entries further left are supplied by the client and ignored, so a forged
      header cannot change the result.
    * Otherwise the TCP peer address.
    """
    peer = request.client.host if request.client else "unknown"
    if client_ip_header:
        value = _valid_ip(request.headers.get(client_ip_header, ""))
        if value:
            return value
    if trusted_proxy_count <= 0:
        return peer
    forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if len(forwarded) < trusted_proxy_count:
        return peer
    return _valid_ip(forwarded[-trusted_proxy_count]) or peer
