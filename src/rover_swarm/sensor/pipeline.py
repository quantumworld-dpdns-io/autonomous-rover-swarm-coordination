from __future__ import annotations

import asyncio
import time
import zlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from rover_swarm.types import RoverId, SensorReading


class Compression(str, Enum):
    NONE = "none"
    ZLIB = "zlib"


class PipelineState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class PipelineConfig(BaseModel):
    buffer_size: int = Field(default=1000, ge=1, description="Max buffered readings")
    batch_interval: float = Field(default=0.5, ge=0.01, description="Seconds between batch flushes")
    batch_size: int = Field(default=100, ge=1, description="Max readings per batch")
    compression: Compression = Field(default=Compression.ZLIB)
    max_retries: int = Field(default=3, ge=0)
    retry_delay: float = Field(default=1.0, ge=0.1)


@dataclass
class PipelineMetrics:
    total_ingested: int = 0
    total_flushed: int = 0
    total_dropped: int = 0
    total_errors: int = 0
    last_flush_time: float = 0.0
    current_buffer_size: int = 0

    @property
    def loss_rate(self) -> float:
        total = self.total_ingested + self.total_dropped
        if total == 0:
            return 0.0
        return self.total_dropped / total


SinkFn: Callable = Callable[[list[SensorReading]], Any]


class SensorPipeline:
    """Async data ingestion pipeline with buffering, batching, and publishing."""

    def __init__(
        self,
        rover_id: RoverId,
        config: PipelineConfig | None = None,
    ) -> None:
        self._rover_id = rover_id
        self._config = config or PipelineConfig()
        self._buffer: list[SensorReading] = []
        self._sink: SinkFn | None = None
        self._state = PipelineState.STOPPED
        self._metrics = PipelineMetrics()
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

        logger.debug(
            "SensorPipeline initialized",
            rover_id=rover_id,
            config=self._config.model_dump(),
        )

    @property
    def state(self) -> PipelineState:
        return self._state

    @property
    def metrics(self) -> PipelineMetrics:
        return self._metrics

    async def ingest(self, reading: SensorReading) -> None:
        """Add a sensor reading to the pipeline buffer."""
        async with self._lock:
            if len(self._buffer) >= self._config.buffer_size:
                self._metrics.total_dropped += 1
                logger.warning("Buffer full, dropping reading", sensor_type=reading.sensor_type)
                return

            self._buffer.append(reading)
            self._metrics.total_ingested += 1
            self._metrics.current_buffer_size = len(self._buffer)

        logger.trace("Reading ingested", sensor_type=reading.sensor_type)

    async def flush(self) -> None:
        """Flush buffered readings to the sink."""
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer = self._buffer[len(batch) :]
            self._metrics.current_buffer_size = len(self._buffer)

        if self._sink is None:
            logger.warning("No sink configured, discarding {} readings", len(batch))
            self._metrics.total_dropped += len(batch)
            return

        await self._publish_with_retry(batch)

    async def _publish_with_retry(self, batch: list[SensorReading]) -> None:
        assert self._sink is not None

        compressed = self._compress(batch)
        last_error: Exception | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                result = self._sink(compressed)
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    await result

                self._metrics.total_flushed += len(batch)
                self._metrics.last_flush_time = time.monotonic()
                logger.trace("Batch flushed", size=len(batch), attempt=attempt)
                return

            except Exception as exc:
                last_error = exc
                self._metrics.total_errors += 1
                logger.warning(
                    "Flush failed",
                    attempt=attempt,
                    max_retries=self._config.max_retries,
                    error=exc,
                )
                if attempt < self._config.max_retries:
                    await asyncio.sleep(self._config.retry_delay)

        logger.error(
            "Flush failed after all retries",
            batch_size=len(batch),
            error=last_error,
        )
        self._metrics.total_dropped += len(batch)

    def _compress(self, readings: list[SensorReading]) -> list[SensorReading] | bytes:
        if self._config.compression == Compression.NONE:
            return readings

        if self._config.compression == Compression.ZLIB:
            try:
                import msgpack

                serialized = msgpack.packb(
                    [
                        {
                            "sensor_type": r.sensor_type.value,
                            "rover_id": r.rover_id,
                            "value": str(r.value),
                            "timestamp": r.timestamp,
                            "metadata": r.metadata,
                        }
                        for r in readings
                    ]
                )
                return zlib.compress(serialized)
            except ImportError:
                logger.warning("msgpack not available, falling back to uncompressed")
                return readings
            except Exception as exc:
                logger.warning("Compression failed", error=exc)
                return readings

    async def start(self) -> None:
        """Start the pipeline flush loop."""
        if self._state is PipelineState.RUNNING:
            logger.warning("Pipeline already running")
            return

        self._state = PipelineState.STARTING
        self._stop_event.clear()
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._state = PipelineState.RUNNING
        logger.info("Pipeline started")

    async def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self._config.batch_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Flush loop error", error=exc)
                self._state = PipelineState.ERROR
                break

        remaining = len(self._buffer)
        if remaining > 0:
            logger.info("Flushing {} remaining readings before stop", remaining)
            await self.flush()

    async def stop(self) -> None:
        """Stop the pipeline and flush remaining data."""
        if self._state is PipelineState.STOPPED:
            return

        self._state = PipelineState.STOPPING
        self._stop_event.set()

        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        await self.flush()
        self._state = PipelineState.STOPPED
        logger.info("Pipeline stopped", metrics=self._metrics)

    def set_sink(self, sink: SinkFn) -> None:
        """Set the publish sink callable."""
        self._sink = sink
        logger.debug("Sink configured")
