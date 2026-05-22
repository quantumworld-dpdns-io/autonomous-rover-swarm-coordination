from __future__ import annotations

import asyncio
import json
import socket
import time
from dataclasses import dataclass, field
from typing import Callable

from loguru import logger


@dataclass
class DiscoveredRover:
    node_id: str
    address: str
    port: int
    protocol: str
    capabilities: list[str] = field(default_factory=list)
    last_seen: float = 0.0


class RoverDiscovery:
    """mDNS/Zeroconf-based rover discovery for ad-hoc swarm formation."""

    DISCOVERY_ADDR = "224.0.0.251"
    DISCOVERY_PORT = 5353
    DISCOVERY_MSG = b"rover-swarm-discovery"

    def __init__(self, node_id: str, port: int = 0) -> None:
        self._node_id = node_id
        self._port = port
        self._sock: socket.socket | None = None
        self._discovered: dict[str, DiscoveredRover] = {}
        self._on_discover: list[Callable] = []
        self._running = False

    def on_discover(self, callback: Callable) -> None:
        self._on_discover.append(callback)

    async def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self._sock.bind(("", self.DISCOVERY_PORT))
        mreq = socket.inet_aton(self.DISCOVERY_ADDR) + socket.inet_aton("0.0.0.0")
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._sock.setblocking(False)
        self._running = True
        logger.info("Discovery started on {}:{}", self.DISCOVERY_ADDR, self.DISCOVERY_PORT)

    async def advertise(self) -> None:
        if not self._sock:
            return
        msg = json.dumps({
            "node_id": self._node_id,
            "port": self._port,
            "protocol": "mqtt",
            "capabilities": ["crdt", "telemetry", "command"],
        }).encode()
        while self._running:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self._sock.sendto(msg, (self.DISCOVERY_ADDR, self.DISCOVERY_PORT)),
                )
            except Exception as e:
                logger.warning("Advertise error: {}", e)
            await asyncio.sleep(30)

    async def listen(self) -> None:
        if not self._sock:
            return
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                data, addr = await loop.run_in_executor(None, lambda: self._sock.recvfrom(1024))
                info = json.loads(data.decode())
                node_id = info.get("node_id", "")
                if node_id and node_id != self._node_id:
                    rover = DiscoveredRover(
                        node_id=node_id,
                        address=addr[0],
                        port=info.get("port", 0),
                        protocol=info.get("protocol", "unknown"),
                        capabilities=info.get("capabilities", []),
                        last_seen=time.time(),
                    )
                    if node_id not in self._discovered:
                        self._discovered[node_id] = rover
                        logger.info("Discovered rover: {} at {}:{}", node_id, addr[0], info.get("port"))
                        for cb in self._on_discover:
                            cb(rover)
                    else:
                        self._discovered[node_id].last_seen = time.time()
            except (json.JSONDecodeError, OSError):
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Discovery listen error: {}", e)

    def discovered_rovers(self) -> list[DiscoveredRover]:
        now = time.time()
        return [r for r in self._discovered.values() if (now - r.last_seen) < 120]

    async def stop(self) -> None:
        self._running = False
        if self._sock:
            self._sock.close()
        logger.info("Discovery stopped")
