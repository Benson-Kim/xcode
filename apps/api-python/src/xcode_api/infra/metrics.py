"""Prometheus series of ``docs/08-operability.md`` section 5, one registry per app.

Labels are route templates, methods, status codes, routine names, pool states and the four
internal refusal reasons: never an id, a phone number, an address or a raw path (a request
no route matched is counted as ``unmatched``). The pool and mail-queue gauges are read at
scrape time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from prometheus_client.registry import Collector

UNMATCHED_ROUTE = "unmatched"


class _Gauges(Collector):
    def __init__(
        self,
        pool_states: Callable[[], Mapping[str, int]],
        mail_queue_depth: Callable[[], int],
    ) -> None:
        self._pool_states = pool_states
        self._mail_queue_depth = mail_queue_depth

    def collect(self) -> Iterator[Metric]:
        pool = GaugeMetricFamily(
            "db_pool_connections", "Database pool connections by state", labels=["state"]
        )
        for state, count in self._pool_states().items():
            pool.add_metric([state], count)
        yield pool
        yield GaugeMetricFamily(
            "mail_queue_depth", "Mail messages waiting to be sent", value=self._mail_queue_depth()
        )


class Metrics:
    """The app's series; ``exposition()`` is the ``/metrics`` body and its content type."""

    def __init__(
        self,
        *,
        pool_states: Callable[[], Mapping[str, int]],
        mail_queue_depth: Callable[[], int],
    ) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self._requests = Counter(
            "http_requests_total",
            "HTTP requests by route template, method and status",
            ["route", "method", "status"],
            registry=self.registry,
        )
        self._durations = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration by route template",
            ["route"],
            registry=self.registry,
        )
        self._routines = Histogram(
            "db_routine_duration_seconds",
            "Routine call duration by routine",
            ["routine"],
            registry=self.registry,
        )
        self._refusals = Counter(
            "auth_refusals_total",
            "Sign-in refusals by internal reason",
            ["reason"],
            registry=self.registry,
        )
        self._rate_limited = Counter(
            "rate_limit_rejections_total",
            "Requests refused by the rate limiter",
            registry=self.registry,
        )
        self.registry.register(_Gauges(pool_states, mail_queue_depth))

    def request_finished(self, route: str, method: str, status: int, seconds: float) -> None:
        self._requests.labels(route, method, str(status)).inc()
        self._durations.labels(route).observe(seconds)

    def routine_finished(self, routine: str, seconds: float) -> None:
        self._routines.labels(routine).observe(seconds)

    def auth_refused(self, reason: str) -> None:
        self._refusals.labels(reason).inc()

    def rate_limit_rejected(self) -> None:
        self._rate_limited.inc()

    def exposition(self) -> tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST
