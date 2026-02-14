"""Lightweight Prometheus-compatible metrics collection.

Collects request counts, latency histograms, and application-level gauges
without requiring the prometheus_client library. Exports metrics in
Prometheus text exposition format at /api/metrics.
"""

import time
import threading
from collections import defaultdict


class Metrics:
    """Thread-safe metrics collector with Prometheus text format export."""

    # Histogram buckets for request duration (seconds)
    DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self):
        self._lock = threading.Lock()
        # Counter: request count by method, path, status
        self._request_count: dict[tuple[str, str, int], int] = defaultdict(int)
        # Histogram: request duration by method, path
        self._duration_buckets: dict[tuple[str, str], list[int]] = {}
        self._duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._duration_count: dict[tuple[str, str], int] = defaultdict(int)
        # Gauges: set externally
        self._gauges: dict[str, float] = {}
        self._gauge_help: dict[str, str] = {}

    def record_request(self, method: str, path: str, status: int, duration: float):
        """Record a completed HTTP request."""
        # Normalize path to reduce cardinality (collapse IDs to {id})
        normalized = self._normalize_path(path)
        with self._lock:
            self._request_count[(method, normalized, status)] += 1
            key = (method, normalized)
            self._duration_sum[key] += duration
            self._duration_count[key] += 1
            if key not in self._duration_buckets:
                self._duration_buckets[key] = [0] * len(self.DURATION_BUCKETS)
            # Record into the smallest matching bucket only; cumulative computed at export
            for i, bound in enumerate(self.DURATION_BUCKETS):
                if duration <= bound:
                    self._duration_buckets[key][i] += 1
                    break
            else:
                # Duration exceeds all buckets — record in the largest bucket
                self._duration_buckets[key][-1] += 1

    def set_gauge(self, name: str, value: float, help_text: str = ""):
        """Set a gauge value (e.g., active_agents, db_size_bytes)."""
        with self._lock:
            self._gauges[name] = value
            if help_text:
                self._gauge_help[name] = help_text

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Collapse numeric path segments to {id} to reduce metric cardinality."""
        parts = path.split("/")
        normalized = []
        for part in parts:
            if part.isdigit():
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/".join(normalized)

    def export(self) -> str:
        """Export all metrics in Prometheus text exposition format."""
        lines: list[str] = []

        with self._lock:
            # Request count
            if self._request_count:
                lines.append("# HELP lu_http_requests_total Total HTTP requests")
                lines.append("# TYPE lu_http_requests_total counter")
                for (method, path, status), count in sorted(self._request_count.items()):
                    lines.append(
                        f'lu_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
                    )

            # Request duration histogram
            if self._duration_buckets:
                lines.append("")
                lines.append("# HELP lu_http_request_duration_seconds Request duration in seconds")
                lines.append("# TYPE lu_http_request_duration_seconds histogram")
            for (method, path), buckets in sorted(self._duration_buckets.items()):
                cumulative = 0
                for i, bound in enumerate(self.DURATION_BUCKETS):
                    cumulative += buckets[i]
                    lines.append(
                        f'lu_http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="{bound}"}} {cumulative}'
                    )
                total_count = self._duration_count[(method, path)]
                lines.append(
                    f'lu_http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="+Inf"}} {total_count}'
                )
                lines.append(
                    f'lu_http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {self._duration_sum[(method, path)]:.6f}'
                )
                lines.append(
                    f'lu_http_request_duration_seconds_count{{method="{method}",path="{path}"}} {total_count}'
                )

            # Gauges
            for name in sorted(self._gauges.keys()):
                help_text = self._gauge_help.get(name, "")
                if help_text:
                    lines.append(f"")
                    lines.append(f"# HELP {name} {help_text}")
                    lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {self._gauges[name]}")

        lines.append("")
        return "\n".join(lines)

    def reset(self):
        """Reset all metrics. Used by tests."""
        with self._lock:
            self._request_count.clear()
            self._duration_buckets.clear()
            self._duration_sum.clear()
            self._duration_count.clear()
            self._gauges.clear()
            self._gauge_help.clear()


# Global metrics instance
metrics = Metrics()
