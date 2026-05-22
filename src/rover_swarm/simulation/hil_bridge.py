from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from rover_swarm.types import TelemetryPacket


@dataclass
class BridgeConfig:
    host: str = "localhost"
    port: int = 0
    timeout: float = 5.0
    extra: dict[str, Any] = field(default_factory=dict)


SensorCallback = Callable[[str, Any], None]


class HilBridge(ABC):
    def __init__(self, config: BridgeConfig | None = None) -> None:
        self.config = config or BridgeConfig()
        self._connected: bool = False
        self._callbacks: dict[str, list[SensorCallback]] = {}

    @property
    def connected(self) -> bool:
        return self._connected

    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> bool: ...

    @abstractmethod
    def publish_state(self, packet: TelemetryPacket) -> bool: ...

    @abstractmethod
    def subscribe_sensor(self, sensor_id: str, callback: SensorCallback) -> None: ...


class GazeboBridge(HilBridge):
    def __init__(self, config: BridgeConfig | None = None) -> None:
        super().__init__(config)
        self._ros2_node: Any = None
        self._publishers: dict[str, Any] = {}
        self._subscribers: dict[str, Any] = {}

    def _import_ros2(self) -> None:
        try:
            import rclpy
            from std_msgs.msg import String

            self._rclpy = rclpy
            self._StringMsg = String
        except ImportError:
            self._rclpy = None
            self._StringMsg = None

    def connect(self) -> bool:
        self._import_ros2()
        if self._rclpy is None:
            return False
        if not self._rclpy.ok():
            self._rclpy.init()
        try:
            from rclpy.node import Node

            self._ros2_node = Node("gazebo_bridge")
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    def disconnect(self) -> bool:
        if self._ros2_node is not None:
            self._ros2_node.destroy_node()
            self._ros2_node = None
        if self._rclpy is not None and self._rclpy.ok():
            self._rclpy.shutdown()
        self._connected = False
        self._publishers.clear()
        self._subscribers.clear()
        return True

    def publish_state(self, packet: TelemetryPacket) -> bool:
        if not self._connected or self._ros2_node is None:
            return False
        topic = f"/rover/{packet.rover_id}/telemetry"
        if topic not in self._publishers:
            pub = self._ros2_node.create_publisher(self._StringMsg, topic, 10)
            self._publishers[topic] = pub
        msg = self._StringMsg()
        msg.data = packet.model_dump_json() if hasattr(packet, "model_dump_json") else str(packet)
        self._publishers[topic].publish(msg)
        return True

    def subscribe_sensor(self, sensor_id: str, callback: SensorCallback) -> None:
        if not self._connected or self._ros2_node is None:
            self._callbacks.setdefault(sensor_id, []).append(callback)
            return
        topic = f"/sensor/{sensor_id}"
        if topic not in self._subscribers:

            def handler(msg: Any) -> None:
                for cb in self._callbacks.get(sensor_id, []):
                    cb(sensor_id, str(msg.data))

            sub = self._ros2_node.create_subscription(self._StringMsg, topic, handler, 10)
            self._subscribers[topic] = sub
        self._callbacks.setdefault(sensor_id, []).append(callback)


class IsaacSimBridge(HilBridge):
    def __init__(self, config: BridgeConfig | None = None) -> None:
        super().__init__(config)
        self._client: Any = None

    def connect(self) -> bool:
        try:
            import carb
            import omni.usd

            self._carb = carb
            self._omni_usd = omni.usd
            self._connected = True
            return True
        except ImportError:
            self._connected = False
            return False

    def disconnect(self) -> bool:
        self._client = None
        self._connected = False
        return True

    def publish_state(self, _packet: TelemetryPacket) -> bool:
        return self._connected

    def subscribe_sensor(self, sensor_id: str, callback: SensorCallback) -> None:
        self._callbacks.setdefault(sensor_id, []).append(callback)
