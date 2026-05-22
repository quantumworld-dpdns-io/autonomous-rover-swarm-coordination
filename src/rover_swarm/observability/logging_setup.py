from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Generator

from loguru import logger

from rover_swarm.config import LogLevel, settings

try:
    from opentelemetry import trace as otel_trace

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


@dataclass
class LogConfig:
    """Log level, format, and output destinations."""

    level: LogLevel = LogLevel.INFO
    json_format: bool = False
    log_file: Path | None = None
    enable_loki: bool = False
    loki_url: str = ""
    enable_datadog: bool = False
    datadog_api_key: str = ""
    datadog_host: str = "http-intake.logs.datadoghq.com"


class LokiHandler:
    """Minimal Loki log push."""

    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/") + "/loki/api/v1/push"

    def send(self, record: dict[str, Any]) -> None:
        try:
            import httpx

            payload = {
                "streams": [
                    {
                        "stream": {"service": "rover-swarm", "level": record.get("level", "INFO")},
                        "values": [[str(int(datetime.now(timezone.utc).timestamp() * 1e9)), json.dumps(record)]],
                    }
                ]
            }
            httpx.post(self._url, json=payload, timeout=5.0)
        except Exception:
            logger.opt(exception=True).debug("Failed to send log to Loki")


class DataDogHandler:
    """Minimal Datadog log push."""

    def __init__(self, api_key: str, host: str) -> None:
        self._url = f"https://{host}/api/v2/logs"
        self._api_key = api_key

    def send(self, record: dict[str, Any]) -> None:
        try:
            import httpx

            httpx.post(
                self._url,
                headers={"DD-API-KEY": self._api_key, "Content-Type": "application/json"},
                json=[record],
                timeout=5.0,
            )
        except Exception:
            logger.opt(exception=True).debug("Failed to send log to Datadog")


class LogCollector:
    """Structured log aggregation with Loki/DataDog format support."""

    def __init__(self, config: LogConfig | None = None) -> None:
        self._config = config or LogConfig()
        self._lock = Lock()
        self._buffer: list[dict[str, Any]] = []
        self._loki_handler: LokiHandler | None = None
        self._datadog_handler: DataDogHandler | None = None

        self._configure()

        if self._config.enable_loki and self._config.loki_url:
            self._loki_handler = LokiHandler(self._config.loki_url)
        if self._config.enable_datadog and self._config.datadog_api_key:
            self._datadog_handler = DataDogHandler(self._config.datadog_api_key, self._config.datadog_host)

    def _configure(self) -> None:
        logger.remove()

        if self._config.json_format:

            def json_sink(message: Any) -> None:
                record = message.record
                structured: dict[str, Any] = {
                    "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "level": record["level"].name,
                    "logger": record["name"],
                    "module": record["module"],
                    "function": record["function"],
                    "line": record["line"],
                    "message": record["message"],
                    "extra": record.get("extra", {}),
                }
                if record.get("exception"):
                    structured["exception"] = str(record["exception"])
                sys.stdout.write(json.dumps(structured) + "\n")
                sys.stdout.flush()

            logger.add(json_sink, level=self._config.level.value, colorize=False)
        else:
            log_format = (
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} | {message}"
            )
            logger.add(
                sys.stdout,
                format=log_format,
                level=self._config.level.value,
                colorize=True,
                backtrace=True,
                diagnose=True,
            )

        if self._config.log_file:
            self._config.log_file.parent.mkdir(parents=True, exist_ok=True)
            logger.add(
                str(self._config.log_file),
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {message}",
                level=self._config.level.value,
                rotation="100 MB",
                retention="30 days",
                compression="gz",
            )

        logging.basicConfig(handlers=[], level=logging.INFO, force=True)
        for lib_logger in ("uvicorn", "fastapi", "httpx", "aiohttp", "grpc"):
            logging.getLogger(lib_logger).handlers = []
            logging.getLogger(lib_logger).propagate = False

        logger.info("LogCollector configured", level=self._config.level.value, json=self._config.json_format)

    def emit(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._buffer.append(record)
            if self._loki_handler:
                self._loki_handler.send(record)
            if self._datadog_handler:
                self._datadog_handler.send(record)

    def flush(self) -> list[dict[str, Any]]:
        with self._lock:
            buf = self._buffer[:]
            self._buffer.clear()
        return buf

    @property
    def config(self) -> LogConfig:
        return self._config


@contextmanager
def log_span(
    operation: str,
    rover_id: str | None = None,
    mission_id: str | None = None,
    level: str = "INFO",
    **extra: Any,
) -> Generator[dict[str, Any], None, None]:
    """Log with span context — start and end of an operation."""
    span_context: dict[str, Any] = {
        "operation": operation,
        "rover_id": rover_id or "",
        "mission_id": mission_id or "",
        "trace_id": "",
        "span_id": "",
    }

    if _OTEL_AVAILABLE:
        current_span = otel_trace.get_current_span()
        span_context_attrs = current_span.get_span_context() if hasattr(current_span, "get_span_context") else None
        if span_context_attrs:
            span_context["trace_id"] = hex(span_context_attrs.trace_id) if hasattr(span_context_attrs, "trace_id") else ""
            span_context["span_id"] = hex(span_context_attrs.span_id) if hasattr(span_context_attrs, "span_id") else ""

    attrs = {**span_context, **extra}
    start = datetime.now(timezone.utc)

    logger.log(level, "Span started", **attrs)

    try:
        yield attrs
    except Exception as exc:
        attrs["error"] = str(exc)
        attrs["duration_ms"] = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        logger.log(level, "Span failed", **attrs)
        raise
    else:
        attrs["duration_ms"] = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        logger.log(level, "Span completed", **attrs)
