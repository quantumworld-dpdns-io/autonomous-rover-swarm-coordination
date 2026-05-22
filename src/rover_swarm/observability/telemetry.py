from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

from loguru import logger

try:
    from opentelemetry import metrics as otel_metrics, trace as otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

    class _NoopSpan:
        def set_attribute(self, key: str, value: Any) -> None: ...
        def set_status(self, status: Any) -> None: ...
        def end(self) -> None: ...

    class _NoopTracer:
        def start_span(self, name: str, **kwargs: Any) -> _NoopSpan:
            return _NoopSpan()

        def start_as_current_span(self, name: str, **kwargs: Any) -> Any:
            return self

        def __enter__(self) -> _NoopTracer:
            return self

        def __exit__(self, *args: Any) -> None: ...


from rover_swarm.config import settings


@dataclass
class CounterMetrics:
    """Helper for creating and updating OTel counter instruments."""

    _counters: dict[str, Any] = field(default_factory=dict)

    def add(self, name: str, value: int | float = 1, attributes: dict[str, Any] | None = None) -> None:
        if not _OTEL_AVAILABLE:
            return
        if name not in self._counters:
            meter = otel_metrics.get_meter(settings.otel.service_name)
            self._counters[name] = meter.create_counter(name)
        self._counters[name].add(value, attributes or {})


@dataclass
class GaugeMetrics:
    """Helper for creating and updating OTel gauge instruments."""

    _gauges: dict[str, Any] = field(default_factory=dict)

    def set(self, name: str, value: int | float, attributes: dict[str, Any] | None = None) -> None:
        if not _OTEL_AVAILABLE:
            return
        if name not in self._gauges:
            meter = otel_metrics.get_meter(settings.otel.service_name)
            self._gauges[name] = meter.create_gauge(name)
        self._gauges[name].set(value, attributes or {})


@dataclass
class HistogramMetrics:
    """Helper for creating and updating OTel histogram instruments."""

    _histograms: dict[str, Any] = field(default_factory=dict)

    def record(self, name: str, value: int | float, attributes: dict[str, Any] | None = None) -> None:
        if not _OTEL_AVAILABLE:
            return
        if name not in self._histograms:
            meter = otel_metrics.get_meter(settings.otel.service_name)
            self._histograms[name] = meter.create_histogram(name)
        self._histograms[name].record(value, attributes or {})


class SwarmTracer:
    """Context manager for creating spans with rover/mission attributes."""

    def __init__(self, tracer: Any | None = None) -> None:
        self._tracer = tracer

    @contextmanager
    def span(
        self,
        name: str,
        rover_id: str | None = None,
        mission_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Any, None, None]:
        attrs: dict[str, Any] = {
            "service.name": settings.otel.service_name,
            "node.id": settings.node_id,
        }
        if rover_id:
            attrs["rover.id"] = rover_id
        if mission_id:
            attrs["mission.id"] = mission_id
        if attributes:
            attrs.update(attributes)

        if not _OTEL_AVAILABLE or self._tracer is None:
            yield None
            return

        with self._tracer.start_as_current_span(name, attributes=attrs) as span:
            yield span


class TelemetryCollector:
    """Manages OTel traces, metrics, and logs."""

    def __init__(self) -> None:
        self._tracer_provider: TracerProvider | None = None
        self._meter_provider: MeterProvider | None = None
        self._tracer: Any = None
        self.counters = CounterMetrics()
        self.gauges = GaugeMetrics()
        self.histograms = HistogramMetrics()
        self.swarm_tracer = SwarmTracer()

    @property
    def tracer(self) -> Any:
        return self._tracer

    def shutdown(self) -> None:
        if self._tracer_provider:
            self._tracer_provider.shutdown()
        if self._meter_provider:
            self._meter_provider.shutdown()
        logger.info("Telemetry collector shut down")


def init_telemetry(
    service_name: str | None = None,
    otlp_endpoint: str | None = None,
) -> TelemetryCollector:
    """Initialise OTel SDK with OTLP exporter."""
    collector = TelemetryCollector()

    if not _OTEL_AVAILABLE:
        logger.warning("OpenTelemetry not installed; telemetry disabled")
        return collector

    name = service_name or settings.otel.service_name
    endpoint = otlp_endpoint or settings.otel.exporter_otlp_endpoint

    resource = Resource.create({"service.name": name})

    try:
        span_exporter = OTLPSpanExporter(endpoint=endpoint)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        otel_trace.set_tracer_provider(tracer_provider)
        collector._tracer_provider = tracer_provider
        collector._tracer = tracer_provider.get_tracer(name)
        collector.swarm_tracer = SwarmTracer(collector._tracer)
        logger.info("OTel trace exporter configured", endpoint=endpoint)
    except Exception:
        logger.exception("Failed to initialise OTel trace exporter")

    try:
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint),
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        otel_metrics.set_meter_provider(meter_provider)
        collector._meter_provider = meter_provider
        logger.info("OTel metric exporter configured", endpoint=endpoint)
    except Exception:
        logger.exception("Failed to initialise OTel metric exporter")

    return collector
