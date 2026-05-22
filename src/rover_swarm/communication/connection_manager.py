from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable

from loguru import logger

from rover_swarm.constants import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT, MAX_PEERS, STALE_ROVER_TIMEOUT


@dataclass
class PeerConnection:
    node_id: str
    address: str
    connected_at: float = 0.0
    last_heartbeat: float = 0.0
    latency_ms: float = 0.0
    protocol: str = "mqtt"
    is_active: bool = True


class ConnectionManager:
    """Manages peer connections in the swarm mesh network."""

    def __init__(self, node_id: str) -> None:
        self._node_id = node_id
        self._peers: dict[str, PeerConnection] = {}
        self._on_connect: list[Callable] = []
        self._on_disconnect: list[Callable] = []
        self._running = False

    def register_peer(self, node_id: str, address: str, protocol: str = "mqtt") -> None:
        if len(self._peers) >= MAX_PEERS:
            logger.warning("Max peers reached, dropping oldest")
            oldest = min(self._peers.keys(), key=lambda k: self._peers[k].connected_at)
            self._peers.pop(oldest)
        if node_id not in self._peers:
            self._peers[node_id] = PeerConnection(
                node_id=node_id,
                address=address,
                connected_at=time.time(),
                last_heartbeat=time.time(),
                protocol=protocol,
            )
            logger.info("Peer registered: {} at {} ({})", node_id, address, protocol)
            for cb in self._on_connect:
                cb(node_id)
        else:
            self._peers[node_id].last_heartbeat = time.time()
            self._peers[node_id].address = address
            self._peers[node_id].is_active = True

    def remove_peer(self, node_id: str) -> None:
        peer = self._peers.pop(node_id, None)
        if peer:
            logger.info("Peer removed: {}", node_id)
            for cb in self._on_disconnect:
                cb(node_id)

    def handle_heartbeat(self, node_id: str, address: str = "") -> None:
        if node_id in self._peers:
            self._peers[node_id].last_heartbeat = time.time()
            self._peers[node_id].is_active = True
        elif address:
            self.register_peer(node_id, address)

    def get_peer(self, node_id: str) -> PeerConnection | None:
        return self._peers.get(node_id)

    def active_peers(self) -> list[PeerConnection]:
        now = time.time()
        return [
            p for p in self._peers.values()
            if p.is_active and (now - p.last_heartbeat) < HEARTBEAT_TIMEOUT
        ]

    def all_peers(self) -> list[PeerConnection]:
        return list(self._peers.values())

    def peer_count(self) -> int:
        return len(self.active_peers())

    def on_peer_connect(self, callback: Callable) -> None:
        self._on_connect.append(callback)

    def on_peer_disconnect(self, callback: Callable) -> None:
        self._on_disconnect.append(callback)

    async def monitor(self) -> None:
        self._running = True
        while self._running:
            now = time.time()
            stale_peers = [
                nid for nid, peer in self._peers.items()
                if peer.is_active and (now - peer.last_heartbeat) > STALE_ROVER_TIMEOUT
            ]
            for nid in stale_peers:
                self._peers[nid].is_active = False
                logger.warning("Peer marked stale: {}", nid)
                for cb in self._on_disconnect:
                    cb(nid)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        self._peers.clear()
        logger.info("Connection manager stopped")
