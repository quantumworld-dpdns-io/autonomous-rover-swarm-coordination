from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from rover_swarm.constants import HEARTBEAT_INTERVAL, NODE_ID, STALE_ROVER_TIMEOUT
from rover_swarm.types import RoverStatus


class SwarmHealthMonitor:
    """Monitors health of all rovers in the swarm."""

    def __init__(self, node_id: str = NODE_ID) -> None:
        self._node_id = node_id
        self._rover_health: dict[str, dict[str, Any]] = {}
        self._running = False
        self._alerts: list[dict[str, Any]] = []

    def report_health(self, rover_id: str, status: str, metrics: dict[str, Any] | None = None) -> None:
        self._rover_health[rover_id] = {
            "rover_id": rover_id,
            "status": status,
            "last_seen": time.time(),
            "metrics": metrics or {},
        }
        if status == RoverStatus.ERROR.value:
            self._add_alert(rover_id, "error", metrics)

    def get_health(self, rover_id: str) -> dict[str, Any] | None:
        return self._rover_health.get(rover_id)

    def all_healthy(self) -> list[dict[str, Any]]:
        now = time.time()
        return [
            h for h in self._rover_health.values()
            if h["status"] == RoverStatus.ONLINE.value
            and (now - h["last_seen"]) < STALE_ROVER_TIMEOUT
        ]

    def unhealthy_rovers(self) -> list[dict[str, Any]]:
        now = time.time()
        return [
            h for h in self._rover_health.values()
            if h["status"] != RoverStatus.ONLINE.value
            or (now - h["last_seen"]) >= STALE_ROVER_TIMEOUT
        ]

    def _add_alert(self, rover_id: str, alert_type: str, details: Any = None) -> None:
        alert = {
            "rover_id": rover_id,
            "type": alert_type,
            "details": details,
            "timestamp": time.time(),
        }
        self._alerts.append(alert)
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-500:]
        logger.warning("Health alert: {} - {}", rover_id, alert_type)

    def recent_alerts(self, count: int = 10) -> list[dict[str, Any]]:
        return self._alerts[-count:]

    def swarm_health_summary(self) -> dict[str, Any]:
        now = time.time()
        all_rov = list(self._rover_health.values())
        return {
            "total_rovers": len(all_rov),
            "online": sum(1 for h in all_rov if h["status"] == RoverStatus.ONLINE.value),
            "offline": sum(1 for h in all_rov if h["status"] == RoverStatus.OFFLINE.value),
            "error": sum(1 for h in all_rov if h["status"] == RoverStatus.ERROR.value),
            "stale": sum(1 for h in all_rov if (now - h["last_seen"]) >= STALE_ROVER_TIMEOUT),
            "active_alerts": len(self._alerts),
        }

    async def monitor_loop(self) -> None:
        self._running = True
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        logger.info("Health monitor stopped")
