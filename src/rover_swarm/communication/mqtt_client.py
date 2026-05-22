from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Coroutine

from loguru import logger

from rover_swarm.config import settings
from rover_swarm.constants import (
    HEARTBEAT_INTERVAL,
    MAX_QUEUE_SIZE,
    RECONNECT_BACKOFF_FACTOR,
    RECONNECT_BACKOFF_MAX,
    RECONNECT_BACKOFF_MIN,
)
from rover_swarm.exceptions import MqttError

MqttMessageHandler = Callable[[str, bytes], Coroutine[Any, Any, None] | None]


class MqttClient:
    """Async MQTT client for rover swarm communication."""

    def __init__(
        self,
        broker: str = settings.mqtt.broker,
        port: int = settings.mqtt.port,
        client_id: str = settings.mqtt.client_id,
        username: str | None = settings.mqtt.username,
        password: str | None = settings.mqtt.password,
    ) -> None:
        self._broker = broker
        self._port = port
        self._client_id = client_id
        self._username = username
        self._password = password
        self._connected = False
        self._running = False
        self._handlers: dict[str, list[MqttMessageHandler]] = {}
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._client: Any = None

    async def connect(self) -> None:
        try:
            import gmqtt
        except ImportError:
            logger.warning("gmqtt not installed, falling back to paho-mqtt")
            await self._connect_paho()
            return
        self._client = gmqtt.Client(self._client_id)
        if self._username:
            self._client.set_auth_credentials(self._username, self._password or "")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        await self._client.connect(self._broker, self._port)
        self._connected = True
        logger.info("Connected to MQTT broker at {}:{}", self._broker, self._port)

    async def _connect_paho(self) -> None:
        import paho.mqtt.client as paho
        self._client = paho.Client(client_id=self._client_id, protocol=paho.MQTTv311)
        if self._username:
            self._client.username_pw_set(self._username, self._password or "")
        self._client.on_connect = self._on_connect_paho
        self._client.on_message = self._on_message_paho
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: self._client.connect(self._broker, self._port, 60)
        )
        if result != 0:
            raise MqttError(f"Failed to connect: return code {result}")
        self._client.loop_start()
        self._connected = True
        logger.info("Connected to MQTT (paho) at {}:{}", self._broker, self._port)

    def _on_connect(self, client, flags, rc, properties) -> None:
        logger.info("MQTT connected with result code {}", rc)

    def _on_connect_paho(self, client, userdata, flags, rc) -> None:
        logger.info("MQTT (paho) connected with result code {}", rc)

    def _on_message(self, client, topic, payload, qos, properties) -> None:
        asyncio.ensure_future(self._dispatch(topic, payload))

    def _on_message_paho(self, client, userdata, msg) -> None:
        asyncio.ensure_future(self._dispatch(msg.topic, msg.payload))

    def _on_disconnect(self, client, packet, exc=None) -> None:
        self._connected = False
        logger.warning("MQTT disconnected")

    async def _dispatch(self, topic: str, payload: bytes) -> None:
        handlers = self._handlers.get(topic, [])
        for handler in handlers:
            try:
                result = handler(topic, payload)
                if result:
                    await result
            except Exception as e:
                logger.error("Handler error for {}: {}", topic, e)

    async def subscribe(self, topic: str, handler: MqttMessageHandler) -> None:
        if topic not in self._handlers:
            self._handlers[topic] = []
            if self._client:
                await self._client.subscribe(topic)
        self._handlers[topic].append(handler)
        logger.debug("Subscribed to {}", topic)

    async def publish(self, topic: str, payload: bytes | str, qos: int = 1) -> None:
        if not self._connected:
            raise MqttError("Not connected to MQTT broker")
        if isinstance(payload, str):
            payload = payload.encode()
        await self._client.publish(topic, payload, qos=qos)

    async def start_heartbeat(self, topic: str = "rover/heartbeat") -> None:
        async def _beat():
            while self._running:
                try:
                    await self.publish(topic, f"{time.time()}".encode(), qos=0)
                except Exception as e:
                    logger.warning("Heartbeat failed: {}", e)
                await asyncio.sleep(HEARTBEAT_INTERVAL)

        self._running = True
        asyncio.create_task(_beat())

    async def disconnect(self) -> None:
        self._running = False
        if self._client:
            await self._client.disconnect()
        self._connected = False
        logger.info("MQTT disconnected")

    @property
    def connected(self) -> bool:
        return self._connected

    async def ensure_connected(self) -> None:
        backoff = RECONNECT_BACKOFF_MIN
        while not self._connected:
            try:
                await self.connect()
            except Exception as e:
                logger.warning("Reconnect failed (backoff={}s): {}", backoff, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * RECONNECT_BACKOFF_FACTOR, RECONNECT_BACKOFF_MAX)
