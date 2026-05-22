from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from rover_swarm.communication import MqttClient
from rover_swarm.config import settings
from rover_swarm.constants import (
    CRDT_SYNC_INTERVAL,
    HEARTBEAT_INTERVAL,
    NODE_ID,
    TELEMETRY_PUBLISH_INTERVAL,
)
from rover_swarm.crdt import (
    CrdtDeserializer,
    CrdtSerializer,
    RoverState,
)
from rover_swarm.exceptions import MqttError
from rover_swarm.swarm import ConsensusModule, SwarmHealthMonitor
from rover_swarm.types import MessageType, Position, RoverStatus


class RoverNode:
    def __init__(
        self,
        node_id: str = NODE_ID,
        rover_id: str | None = None,
    ) -> None:
        self.node_id = node_id
        self.rover_id = rover_id or node_id
        self._running = False
        self._tasks: list[asyncio.Task] = []

        self.state = RoverState(rover_id=self.rover_id, node_id=node_id)
        self.mqtt = MqttClient(client_id=node_id)
        self.consensus = ConsensusModule(node_id=node_id)
        self.health_monitor = SwarmHealthMonitor(node_id=node_id)

        self._state.update_status(RoverStatus.ONLINE)

    async def start(self) -> None:
        self._running = True
        logger.info("RoverNode {} starting", self.node_id)

        await self.mqtt.connect()
        self.consensus.start()
        self.health_monitor.monitor_loop()

        self._tasks = [
            asyncio.create_task(self._sync_crdt_loop()),
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._telemetry_loop()),
            asyncio.create_task(self._consensus_loop()),
            asyncio.create_task(self._health_loop()),
        ]

        await self.mqtt.subscribe(
            f"rover/{self.rover_id}/command",
            self._on_command,
        )

        logger.info("RoverNode {} started", self.node_id)

    async def stop(self) -> None:
        self._running = False
        logger.info("RoverNode {} stopping", self.node_id)

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        self.state.update_status(RoverStatus.OFFLINE)
        await self.mqtt.disconnect()
        await self.consensus.stop()
        logger.info("RoverNode {} stopped", self.node_id)

    async def sync_state(self, peer_state: RoverState) -> None:
        merged = self.state.merge(peer_state)
        self.state = merged
        logger.debug("State synced with peer {}", peer_state.rover_id)

    async def handle_command(self, command: dict[str, Any]) -> dict[str, Any]:
        cmd = command.get("command", "")
        logger.info("Handling command: {}", cmd)

        if cmd == "set_status":
            status = RoverStatus(command.get("value", "online"))
            self.state.update_status(status)
            return {"status": "ok", "new_status": status.value}
        elif cmd == "set_position":
            pos_data = command.get("position", {})
            pos = Position(x=pos_data.get("x", 0.0), y=pos_data.get("y", 0.0))
            self.state.update_position(pos)
            return {"status": "ok"}
        elif cmd == "ping":
            return {"status": "ok", "timestamp": time.time()}
        else:
            return {"status": "error", "message": f"Unknown command: {cmd}"}

    async def publish_telemetry(self) -> None:
        if not self.mqtt.connected:
            return

        telemetry = {
            "rover_id": self.rover_id,
            "timestamp": time.time(),
            "position": self.state.position.value(),
            "status": self.state.status.value(),
            "battery": self.state.battery.value(),
            "speed": self.state.speed.value(),
            "heading": self.state.heading.value(),
            "messages_sent": self.state.messages_sent.value(),
            "messages_received": self.state.messages_received.value(),
        }

        topic = f"rover/{self.rover_id}/telemetry"
        serialized = CrdtSerializer.serialize(self.state)
        await self.mqtt.publish(topic, serialized)
        logger.debug("Telemetry published to {}", topic)

    async def _sync_crdt_loop(self) -> None:
        while self._running:
            try:
                if self.mqtt.connected:
                    sync_payload = CrdtSerializer.serialize(self.state)
                    await self.mqtt.publish(
                        f"rover/{self.rover_id}/crdt/sync",
                        sync_payload,
                    )
            except Exception as e:
                logger.warning("CRDT sync error: {}", e)
            await asyncio.sleep(CRDT_SYNC_INTERVAL)

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                if self.mqtt.connected:
                    await self.mqtt.publish(
                        f"rover/{self.rover_id}/heartbeat",
                        f"{time.time()}".encode(),
                        qos=0,
                    )
            except MqttError:
                pass
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _telemetry_loop(self) -> None:
        while self._running:
            try:
                await self.publish_telemetry()
            except Exception as e:
                logger.warning("Telemetry publish error: {}", e)
            await asyncio.sleep(TELEMETRY_PUBLISH_INTERVAL)

    async def _consensus_loop(self) -> None:
        while self._running:
            try:
                result = await self.consensus.step()
                if result:
                    await self.mqtt.publish(
                        f"rover/{self.rover_id}/consensus",
                        result.encode(),
                    )
            except Exception as e:
                logger.warning("Consensus step error: {}", e)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _health_loop(self) -> None:
        while self._running:
            try:
                self.health_monitor.report_health(
                    rover_id=self.rover_id,
                    status=str(self.state.status.value()),
                )
            except Exception as e:
                logger.warning("Health report error: {}", e)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _on_command(self, topic: str, payload: bytes) -> None:
        try:
            import json

            command = json.loads(payload.decode())
            result = await self.handle_command(command)
            if result.get("status") == "ok":
                logger.debug("Command processed: {}", command.get("command"))
            else:
                logger.warning("Command failed: {}", result.get("message"))
        except Exception as e:
            logger.error("Command handler error: {}", e)
