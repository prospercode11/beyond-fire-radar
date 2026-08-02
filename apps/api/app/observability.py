from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter, defaultdict
from typing import Dict


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str, int]] = Counter()
        self._durations: Dict[tuple[str, str], list[float]] = defaultdict(list)

    def observe(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        # Keep only the route template supplied by the caller and cap samples to avoid an
        # unbounded metrics process in a long-running local or single-worker deployment.
        key = (method, path, status_code)
        duration_key = (method, path)
        with self._lock:
            if len(self._requests) >= 10_000 and key not in self._requests:
                return
            self._requests[key] += 1
            samples = self._durations[duration_key]
            samples.append(duration_ms)
            if len(samples) > 500:
                del samples[: len(samples) - 500]

    def snapshot(
        self,
    ) -> tuple[dict[tuple[str, str, int], int], dict[tuple[str, str], list[float]]]:
        with self._lock:
            return dict(self._requests), {
                key: list(value) for key, value in self._durations.items()
            }


metrics = RequestMetrics()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
    )


def log_request(
    *, method: str, path: str, status_code: int, duration_ms: float, request_id: str
) -> None:
    logging.getLogger("beyond_fire_radar.http").info(
        json.dumps(
            {
                "event": "http_request",
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "request_id": request_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def prometheus_text() -> str:
    request_counts, durations = metrics.snapshot()
    lines = [
        "# HELP bfr_http_requests_total HTTP requests by method, path, and status.",
        "# TYPE bfr_http_requests_total counter",
    ]
    for (method, path, status_code), count in sorted(request_counts.items()):
        lines.append(
            f'bfr_http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}'
        )
    lines.extend(
        [
            "# HELP bfr_http_request_duration_ms HTTP request duration summary.",
            "# TYPE bfr_http_request_duration_ms summary",
        ]
    )
    for (method, path), samples in sorted(durations.items()):
        if not samples:
            continue
        samples.sort()
        median = samples[len(samples) // 2]
        lines.append(
            f'bfr_http_request_duration_ms{{method="{method}",path="{path}",quantile="0.5"}} {median:.3f}'
        )
        lines.append(
            f'bfr_http_request_duration_ms{{method="{method}",path="{path}",quantile="0.99"}} '
            f"{samples[min(len(samples) - 1, int(len(samples) * 0.99))]:.3f}"
        )
    return "\n".join(lines) + "\n"


def monotonic_ms() -> float:
    return time.monotonic() * 1000
