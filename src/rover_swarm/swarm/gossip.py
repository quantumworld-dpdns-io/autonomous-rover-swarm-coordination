from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable

from loguru import logger

from rover_swarm.constants import GOSSIP_FANOUT, GOSSIP_INTERVAL, GOSSIP_MAX_PEERS, NODE_ID


class GossipProtocol:
    """Entropy-based anti-entropy gossip protocol for state dissemination."""

    def __init__(
        self,
        node_id: str = NODE_ID,
        fanout: int = GOSSIP_FANOUT,
        interval: float = GOSSIP_INTERVAL,
    ) -> None:
        self._node_id = node_id
        self._fanout = fanout
        self._interval = interval
        self._peers: list[str] = []
        self._message_buffer: list[dict[str, Any]] = []
        self._seen_messages: set[str] = set()
        self._running = False
        self._on_gossip: list[Callable] = []

    def on_message(self, callback: Callable) -> None:
        self._on_gossip.append(callback)

    def update_peers(self, peers: list[str]) -> None:
        self._peers = [p for p in peers if p != self._node_id][:GOSSIP_MAX_PEERS]

    def gossip(self, message: dict[str, Any]) -> None:
        msg_id = message.get("id", f"{self._node_id}:{time.time()}")
        if msg_id not in self._seen_messages:
            self._seen_messages.add(msg_id)
            message["id"] = msg_id
            message["origin"] = self._node_id
            message["ttl"] = message.get("ttl", 3)
            self._message_buffer.append(message)
            if len(self._seen_messages) > 10000:
                self._seen_messages = set(list(self._seen_messages)[-5000:])

    async def disseminate(self) -> None:
        self._running = True
        while self._running:
            if self._message_buffer and self._peers:
                batch = self._message_buffer[:50]
                self._message_buffer = self._message_buffer[50:]
                targets = random.sample(
                    self._peers,
                    min(self._fanout, len(self._peers)),
                )
                for target in targets:
                    for msg in batch:
                        msg["ttl"] = msg.get("ttl", 3) - 1
                        if msg["ttl"] >= 0:
                            await self._send_to_peer(target, msg)
            await asyncio.sleep(self._interval)

    async def _send_to_peer(self, target: str, message: dict[str, Any]) -> None:
        for callback in self._on_gossip:
            try:
                result = callback(target, message)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.warning("Gossip send error to {}: {}", target, e)

    def receive(self, message: dict[str, Any]) -> None:
        msg_id = message.get("id", "")
        if msg_id and msg_id not in self._seen_messages:
            self._seen_messages.add(msg_id)
            if message.get("ttl", 0) > 0:
                message["ttl"] -= 1
                self._message_buffer.append(message)

    async def stop(self) -> None:
        self._running = False
        logger.info("Gossip protocol stopped")

    def stats(self) -> dict[str, Any]:
        return {
            "peers": len(self._peers),
            "buffer_size": len(self._message_buffer),
            "seen_messages": len(self._seen_messages),
        }
