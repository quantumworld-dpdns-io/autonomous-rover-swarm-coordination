from __future__ import annotations

import asyncio
import signal
from typing import Any

from loguru import logger

from rover_swarm.communication import MqttClient, WebSocketBridge
from rover_swarm.config import settings
from rover_swarm.constants import NODE_ID
from rover_swarm.crdt import CrdtDeserializer, RoverState, SwarmState
from rover_swarm.observability import MetricsRegistry, init_metrics


class GroundStation:
    def __init__(
        self,
        node_id: str = f"ground-station-{NODE_ID}",
        port: int = settings.api.port,
    ) -> None:
        self.node_id = node_id
        self.port = port
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._server: Any = None

        self.swarm_state = SwarmState(swarm_id=settings.mission_id, node_id=node_id)
        self.mqtt = MqttClient(client_id=node_id)
        self.ws_bridge = WebSocketBridge()
        self.metrics = MetricsRegistry()

    async def start(self) -> None:
        self._running = True
        logger.info("GroundStation {} starting on port {}", self.node_id, self.port)

        await self.mqtt.connect()

        init_metrics()
        self._start_prometheus()

        await self._subscribe_mqtt_topics()

        self._tasks = [
            asyncio.create_task(self._run_api_server()),
            asyncio.create_task(self._health_check_loop()),
        ]

        logger.info("GroundStation {} started", self.node_id)

    async def stop(self) -> None:
        self._running = False
        logger.info("GroundStation {} stopping", self.node_id)

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        await self.mqtt.disconnect()
        await self.ws_bridge.stop()
        logger.info("GroundStation {} stopped", self.node_id)

    async def handle_rover_telemetry(self, rover_id: str, data: dict[str, Any]) -> None:
        rover_state = self.swarm_state.get_rover(rover_id)
        if rover_state is None:
            rover_state = RoverState(rover_id=rover_id, node_id=self.node_id)
            self.swarm_state.add_rover(rover_state)

        if "position" in data:
            from rover_swarm.types import Position
            pos_data = data.get("position", {})
            if isinstance(pos_data, dict):
                rover_state.update_position(Position(**pos_data))
        if "status" in data:
            from rover_swarm.types import RoverStatus
            rover_state.update_status(RoverStatus(data["status"]))

        self.metrics.set_rover_state(rover_id, "general", "online")

        await self.ws_bridge.broadcast("telemetry", {
            "rover_id": rover_id,
            "data": data,
        })

        logger.debug("Processed telemetry from {}", rover_id)

    async def _run_api_server(self) -> None:
        try:
            import uvicorn
            config = uvicorn.Config(
                "rover_swarm.api.app:app",
                host=settings.api.host,
                port=self.port,
                log_level="info",
            )
            self._server = uvicorn.Server(config)
            await self._server.serve()
        except ImportError:
            logger.warning("uvicorn not available; API server disabled")
            stop_event = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop_event.set)
            await stop_event.wait()

    async def _health_check_loop(self) -> None:
        while self._running:
            await asyncio.sleep(30)
            if self._running:
                summary = {
                    "node_id": self.node_id,
                    "rover_count": len(self.swarm_state.rover_ids()),
                    "ws_clients": self.ws_bridge.client_count,
                    "mqtt_connected": self.mqtt.connected,
                }
                logger.debug("Ground station health: {}", summary)

    async def _on_mqtt_message(self, topic: str, payload: bytes) -> None:
        try:
            parts = topic.split("/")
            if len(parts) >= 3:
                rover_id = parts[1]
                msg_type = parts[2]

                if msg_type == "telemetry":
                    try:
                        crdt = CrdtDeserializer.deserialize(payload)
                        if isinstance(crdt, RoverState):
                            data = crdt.value()
                            await self.handle_rover_telemetry(rover_id, data)
                    except Exception:
                        import json
                        data = json.loads(payload.decode())
                        await self.handle_rover_telemetry(rover_id, data)

                elif msg_type == "heartbeat":
                    self.metrics.inc_messages_received("heartbeat")

                elif msg_type == "crdt" and len(parts) >= 4 and parts[3] == "sync":
                    try:
                        remote_state = CrdtDeserializer.deserialize(payload)
                        if isinstance(remote_state, RoverState):
                            existing = self.swarm_state.get_rover(rover_id)
                            if existing:
                                merged = existing.merge(remote_state)
                            else:
                                self.swarm_state.add_rover(remote_state)
                    except Exception as e:
                        logger.debug("CRDT sync parse error: {}", e)

        except Exception as e:
            logger.warning("MQTT message handler error: {}", e)

    async def _subscribe_mqtt_topics(self) -> None:
        await self.mqtt.subscribe("rover/+/telemetry", self._on_mqtt_message)
        await self.mqtt.subscribe("rover/+/heartbeat", self._on_mqtt_message)
        await self.mqtt.subscribe("rover/+/crdt/sync", self._on_mqtt_message)
        logger.info("Subscribed to rover telemetry topics")

    def _start_prometheus(self) -> None:
        try:
            from rover_swarm.observability import init_metrics
            init_metrics()
            self.metrics = MetricsRegistry()
            logger.info("Prometheus metrics initialized")
        except Exception as e:
            logger.warning("Prometheus init failed: {}", e)
