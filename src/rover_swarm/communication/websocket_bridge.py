from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from loguru import logger

from rover_swarm.config import settings


class WebSocketBridge:
    """Bridges MQTT messages to WebSocket clients for the dashboard."""

    def __init__(self) -> None:
        self._ws_clients: dict[str, Any] = {}
        self._running = False

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        """Broadcast data to all WebSocket clients on a channel."""
        message = json.dumps({"channel": channel, "data": data, "timestamp": time.time()})
        stale = []
        for cid, ws in self._ws_clients.items():
            try:
                await ws.send_text(message)
            except Exception:
                stale.append(cid)
        for cid in stale:
            self._ws_clients.pop(cid, None)

    async def register(self, client_id: str, websocket: Any) -> None:
        self._ws_clients[client_id] = websocket
        logger.info("WebSocket client registered: {}", client_id)

    async def unregister(self, client_id: str) -> None:
        self._ws_clients.pop(client_id, None)
        logger.info("WebSocket client unregistered: {}", client_id)

    @property
    def client_count(self) -> int:
        return len(self._ws_clients)

    async def stop(self) -> None:
        self._running = False
        self._ws_clients.clear()
        logger.info("WebSocket bridge stopped")
