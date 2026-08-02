from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional

from app.config import Settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("request rate limit exceeded")


class RateLimiter:
    """Bounded local limiter with an optional Redis-backed deployment adapter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: Dict[str, Deque[float]] = {}
        self._redis: Optional[object] = None

    def _redis_client(self, settings: Settings) -> object:
        if self._redis is not None:
            return self._redis
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("RATE_LIMIT_BACKEND=redis requires the redis extra") from exc
        self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    def check(self, *, scope: str, key: str, limit: int, settings: Settings) -> None:
        window = settings.rate_limit_window_seconds
        if settings.rate_limit_backend == "redis":
            client = self._redis_client(settings)
            redis_key = f"bfr:rate:{scope}:{key}"
            try:
                count = int(client.incr(redis_key))  # type: ignore[attr-defined]
                if count == 1:
                    client.expire(redis_key, window)  # type: ignore[attr-defined]
            except Exception:
                if settings.app_env.lower() in {"production", "staging"}:
                    raise
                return
            if count > limit:
                raise RateLimitExceeded(window)
            return

        now = time.monotonic()
        with self._lock:
            bucket = self._windows.setdefault(f"{scope}:{key}", deque())
            while bucket and bucket[0] <= now - window:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window - (now - bucket[0])))
                raise RateLimitExceeded(retry_after)
            bucket.append(now)
            if len(self._windows) > 10_000:
                stale = [name for name, values in self._windows.items() if not values]
                for name in stale[:1_000]:
                    self._windows.pop(name, None)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


limiter = RateLimiter()


def client_key(host: Optional[str]) -> str:
    return host or "unknown"
