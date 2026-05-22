from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from loguru import logger


class NetworkSimulator:
    """Simulates network conditions (latency, packet loss, partition) for testing."""

    def __init__(
        self,
        min_latency_ms: float = 0.0,
        max_latency_ms: float = 50.0,
        packet_loss_rate: float = 0.0,
        partition_probability: float = 0.0,
    ) -> None:
        self._min_latency = min_latency_ms / 1000.0
        self._max_latency = max_latency_ms / 1000.0
        self._packet_loss_rate = packet_loss_rate
        self._partition_probability = partition_probability
        self._partitioned_nodes: set[str] = set()
        self._node_id: str = ""

    def configure(self, **kwargs: float) -> None:
        if "min_latency_ms" in kwargs:
            self._min_latency = kwargs["min_latency_ms"] / 1000.0
        if "max_latency_ms" in kwargs:
            self._max_latency = kwargs["max_latency_ms"] / 1000.0
        if "packet_loss_rate" in kwargs:
            self._packet_loss_rate = kwargs["packet_loss_rate"]
        if "partition_probability" in kwargs:
            self._partition_probability = kwargs["partition_probability"]

    async def apply_latency(self) -> None:
        if self._max_latency > 0:
            delay = random.uniform(self._min_latency, self._max_latency)
            if delay > 0:
                await asyncio.sleep(delay)

    def should_drop(self) -> bool:
        return random.random() < self._packet_loss_rate

    def is_partitioned(self, target_node: str) -> bool:
        return target_node in self._partitioned_nodes

    def simulate_partition(self, target_node: str) -> None:
        if random.random() < self._partition_probability:
            self._partitioned_nodes.add(target_node)
            logger.warning("Network partition simulated for {}", target_node)

    def heal_partition(self, target_node: str) -> None:
        self._partitioned_nodes.discard(target_node)
        logger.info("Network partition healed for {}", target_node)

    def heal_all(self) -> None:
        self._partitioned_nodes.clear()
        logger.info("All network partitions healed")

    async def simulate_packet(self, target_node: str = "") -> bool:
        """Returns True if packet should be sent, False if dropped."""
        await self.apply_latency()
        if target_node and self.is_partitioned(target_node):
            return False
        if self.should_drop():
            return False
        return True

    def stats(self) -> dict[str, Any]:
        return {
            "min_latency_ms": self._min_latency * 1000,
            "max_latency_ms": self._max_latency * 1000,
            "packet_loss_rate": self._packet_loss_rate,
            "partition_probability": self._partition_probability,
            "partitioned_nodes": list(self._partitioned_nodes),
        }
