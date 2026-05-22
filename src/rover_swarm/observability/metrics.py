from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

    class _NoopMetric:
        def labels(self, **labels: Any) -> _NoopMetric:
            return self
        def inc(self, value: float = 1) -> None: ...
        def set(self, value: float) -> None: ...
        def observe(self, value: float) -> None: ...

    def start_http_server(port: int) -> None: ...

    Counter = _NoopMetric  # type: ignore[assignment]
    Gauge = _NoopMetric  # type: ignore[assignment]
    Histogram = _NoopMetric  # type: ignore[assignment]


from rover_swarm.config import settings


# Pre-defined metric labels
ROVER_LABELS = ["rover_id", "role", "status"]
MESSAGE_LABELS = ["msg_type", "direction"]
TASK_LABELS = ["task_type", "rover_id"]
CRDT_LABELS = ["operation", "node_id"]
LATENCY_LABELS = ["target", "protocol"]


class MetricsRegistry:
    """Manages Prometheus metrics (counters, gauges, histograms)."""

    def __init__(self, namespace: str = "rover_swarm") -> None:
        self._namespace = namespace
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = threading.Lock()

        if _PROMETHEUS_AVAILABLE:
            self._register_defaults()

    def _register_defaults(self) -> None:
        self._gauges["rover_state"] = Gauge(
            f"{self._namespace}_rover_state",
            "Current rover state (1=online, 0=offline)",
            ROVER_LABELS,
        )
        self._counters["messages_sent"] = Counter(
            f"{self._namespace}_messages_sent_total",
            "Total messages sent",
            MESSAGE_LABELS,
        )
        self._counters["messages_received"] = Counter(
            f"{self._namespace}_messages_received_total",
            "Total messages received",
            MESSAGE_LABELS,
        )
        self._histograms["task_completion_time"] = Histogram(
            f"{self._namespace}_task_completion_seconds",
            "Task completion time in seconds",
            TASK_LABELS,
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, float("inf")),
        )
        self._histograms["crdt_merge_time"] = Histogram(
            f"{self._namespace}_crdt_merge_seconds",
            "CRDT merge time in seconds",
            CRDT_LABELS,
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, float("inf")),
        )
        self._histograms["network_latency"] = Histogram(
            f"{self._namespace}_network_latency_seconds",
            "Network latency in seconds",
            LATENCY_LABELS,
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, float("inf")),
        )
        self._gauges["battery_level"] = Gauge(
            f"{self._namespace}_battery_level_percent",
            "Rover battery level percentage",
            ROVER_LABELS,
        )
        self._histograms["inference_latency"] = Histogram(
            f"{self._namespace}_inference_latency_seconds",
            "AI inference latency in seconds",
            ["model", "operation"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf")),
        )

    def _metric_name(self, name: str) -> str:
        return f"{self._namespace}_{name}"

    def counter(self, name: str, documentation: str = "", labelnames: list[str] | None = None) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(
                    self._metric_name(name),
                    documentation or name,
                    labelnames or [],
                )
            return self._counters[name]

    def gauge(self, name: str, documentation: str = "", labelnames: list[str] | None = None) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(
                    self._metric_name(name),
                    documentation or name,
                    labelnames or [],
                )
            return self._gauges[name]

    def histogram(self, name: str, documentation: str = "", labelnames: list[str] | None = None, buckets: tuple[float, ...] | None = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(
                    self._metric_name(name),
                    documentation or name,
                    labelnames or [],
                    buckets=buckets or Histogram.DEFAULT_BUCKETS,
                )
            return self._histograms[name]

    # ---- Pre-defined metric helpers ----

    def set_rover_state(self, rover_id: str, role: str, status: str, value: float = 1.0) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self._gauges["rover_state"].labels(rover_id=rover_id, role=role, status=status).set(value)

    def inc_messages_sent(self, msg_type: str = "unknown", direction: str = "outbound") -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self._counters["messages_sent"].labels(msg_type=msg_type, direction=direction).inc()

    def inc_messages_received(self, msg_type: str = "unknown", direction: str = "inbound") -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self._counters["messages_received"].labels(msg_type=msg_type, direction=direction).inc()

    def observe_task_completion(self, task_type: str, rover_id: str, duration: float) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self._histograms["task_completion_time"].labels(task_type=task_type, rover_id=rover_id).observe(duration)

    def observe_crdt_merge(self, operation: str, node_id: str, duration: float) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self._histograms["crdt_merge_time"].labels(operation=operation, node_id=node_id).observe(duration)

    def observe_network_latency(self, target: str, protocol: str, duration: float) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self._histograms["network_latency"].labels(target=target, protocol=protocol).observe(duration)

    def set_battery_level(self, rover_id: str, role: str, status: str, level: float) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self._gauges["battery_level"].labels(rover_id=rover_id, role=role, status=status).set(level)

    def observe_inference_latency(self, model: str, operation: str, duration: float) -> None:
        if not _PROMETHEUS_AVAILABLE:
            return
        self._histograms["inference_latency"].labels(model=model, operation=operation).observe(duration)


@dataclass
class _MetricsServerState:
    thread: threading.Thread | None = None
    started: bool = False


_metrics_server = _MetricsServerState()


def init_metrics(port: int | None = None) -> MetricsRegistry:
    """Start Prometheus HTTP server on configurable port and return registry."""
    port = port or settings.prometheus.port
    registry = MetricsRegistry()

    if not _PROMETHEUS_AVAILABLE:
        logger.warning("prometheus_client not installed; metrics disabled")
        return registry

    if _metrics_server.started:
        logger.debug("Prometheus HTTP server already running on port {}", port)
        return registry

    try:
        start_http_server(port)
        _metrics_server.thread = threading.current_thread()
        _metrics_server.started = True
        logger.info("Prometheus metrics server started on port {}", port)
    except Exception:
        logger.exception("Failed to start Prometheus HTTP server on port {}", port)

    return registry
