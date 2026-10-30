import ipaddress
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    """Small in-process limiter; each Gunicorn worker keeps its own window."""

    def __init__(self) -> None:
        self._events = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> bool:
        now = monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


limiter = SlidingWindowLimiter()


def get_client_ip(request: Request) -> str:
    """Prefer Cloudflare's client IP, then a valid X-Forwarded-For entry."""
    candidates = [request.headers.get("cf-connecting-ip", "")]
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        candidates.append(forwarded_for.split(",")[0].strip())
    for candidate in candidates:
        if not candidate:
            continue
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            continue
    return request.client.host if request.client else "unknown"


def limit_key(request: Request, scope: str, suffix: str = "") -> str:
    key = f"{scope}:{get_client_ip(request)}"
    if suffix:
        key += f":{suffix.lower()}"
    return key


def enforce_rate_limit(
    request: Request,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    if not limiter.check(key, limit, window_seconds):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
