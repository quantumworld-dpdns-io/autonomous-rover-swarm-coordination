from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from rover_swarm.api.dependencies import get_jwt_provider, get_rover_state, get_settings
from rover_swarm.crdt.swarm_state import SwarmState
from rover_swarm.exceptions import AuthenticationError


class ConnectionManager:
    def __init__(self) -> None:
        self._swarm_connections: set[WebSocket] = set()
        self._rover_connections: dict[str, set[WebSocket]] = {}
        self._alert_connections: set[WebSocket] = set()

    async def connect_swarm(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._swarm_connections.add(websocket)
        logger.info("WebSocket connected: /ws/swarm")

    async def connect_rover(self, websocket: WebSocket, rover_id: str) -> None:
        await websocket.accept()
        self._rover_connections.setdefault(rover_id, set()).add(websocket)
        logger.info("WebSocket connected: /ws/rovers/{}", rover_id)

    async def connect_alerts(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._alert_connections.add(websocket)
        logger.info("WebSocket connected: /ws/alerts")

    def disconnect_swarm(self, websocket: WebSocket) -> None:
        self._swarm_connections.discard(websocket)

    def disconnect_rover(self, websocket: WebSocket, rover_id: str) -> None:
        rovers = self._rover_connections.get(rover_id)
        if rovers:
            rovers.discard(websocket)
            if not rovers:
                self._rover_connections.pop(rover_id, None)

    def disconnect_alerts(self, websocket: WebSocket) -> None:
        self._alert_connections.discard(websocket)

    async def broadcast_swarm(self, message: dict[str, Any]) -> None:
        dead: set[WebSocket] = set()
        for ws in self._swarm_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._swarm_connections.discard(ws)

    async def broadcast_rover(self, rover_id: str, message: dict[str, Any]) -> None:
        rovers = self._rover_connections.get(rover_id, set())
        dead: set[WebSocket] = set()
        for ws in rovers:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            rovers.discard(ws)

    async def broadcast_alerts(self, message: dict[str, Any]) -> None:
        dead: set[WebSocket] = set()
        for ws in self._alert_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._alert_connections.discard(ws)

    @property
    def swarm_connections(self) -> int:
        return len(self._swarm_connections)

    @property
    def alert_connections(self) -> int:
        return len(self._alert_connections)


_manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if token:
        try:
            provider = get_jwt_provider()
            provider.validate_token(token)
        except AuthenticationError:
            await websocket.close(code=4001)
            return

    await _manager.connect_swarm(websocket)
    try:
        state = await get_rover_state()
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass

            await _manager.broadcast_swarm({
                "type": "swarm_state",
                "timestamp": time.time(),
                "data": state.value(),
            })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        _manager.disconnect_swarm(websocket)
        logger.info("WebSocket disconnected: /ws/swarm")
    except Exception:
        logger.exception("WebSocket error: /ws/swarm")
        _manager.disconnect_swarm(websocket)


async def websocket_rover(websocket: WebSocket, rover_id: str) -> None:
    token = websocket.query_params.get("token")
    if token:
        try:
            provider = get_jwt_provider()
            provider.validate_token(token)
        except AuthenticationError:
            await websocket.close(code=4001)
            return

    await _manager.connect_rover(websocket, rover_id)
    try:
        state = await get_rover_state()
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass

            rover = state.get_rover(rover_id)
            if rover:
                await _manager.broadcast_rover(rover_id, {
                    "type": "rover_telemetry",
                    "rover_id": rover_id,
                    "timestamp": time.time(),
                    "data": rover.value(),
                })
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        _manager.disconnect_rover(websocket, rover_id)
        logger.info("WebSocket disconnected: /ws/rovers/{}", rover_id)
    except Exception:
        logger.exception("WebSocket error: /ws/rovers/{}", rover_id)
        _manager.disconnect_rover(websocket, rover_id)


async def websocket_alerts(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if token:
        try:
            provider = get_jwt_provider()
            provider.validate_token(token)
        except AuthenticationError:
            await websocket.close(code=4001)
            return

    await _manager.connect_alerts(websocket)
    try:
        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass

            await asyncio.sleep(5)
    except WebSocketDisconnect:
        _manager.disconnect_alerts(websocket)
        logger.info("WebSocket disconnected: /ws/alerts")
    except Exception:
        logger.exception("WebSocket error: /ws/alerts")
        _manager.disconnect_alerts(websocket)


__all__ = [
    "ConnectionManager",
    "websocket_endpoint",
    "websocket_rover",
    "websocket_alerts",
]
