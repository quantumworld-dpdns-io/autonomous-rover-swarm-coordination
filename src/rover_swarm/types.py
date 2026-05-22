from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, TypeAlias

RoverId: TypeAlias = str
MissionId: TypeAlias = str
NodeId: TypeAlias = str
Timestamp: TypeAlias = float
VectorClock: TypeAlias = dict[NodeId, int]
Payload: TypeAlias = dict[str, Any]
Metadata: TypeAlias = dict[str, Any]


class RoverRole(str, Enum):
    SCOUT = "scout"
    TRANSPORTER = "transporter"
    RELAY = "relay"
    CHARGER = "charger"
    GENERAL = "general"


class RoverStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    CHARGING = "charging"
    ERROR = "error"
    RECOVERING = "recovering"
    PARTITIONED = "partitioned"


class MissionPhase(str, Enum):
    INITIALIZING = "initializing"
    DEPLOYING = "deploying"
    EXPLORING = "exploring"
    RETURNING = "returning"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class TaskType(str, Enum):
    EXPLORE = "explore"
    SURVEY = "survey"
    TRANSPORT = "transport"
    RELAY = "relay"
    CHARGE = "charge"
    RECONNAISSANCE = "reconnaissance"
    PATROL = "patrol"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageType(str, Enum):
    CRDT_SYNC = "crdt_sync"
    CRDT_DELTA = "crdt_delta"
    HEARTBEAT = "heartbeat"
    COMMAND = "command"
    TELEMETRY = "telemetry"
    TASK_ALLOCATION = "task_allocation"
    CONSENSUS = "consensus"
    DISCOVERY = "discovery"
    ALERT = "alert"


class SensorType(str, Enum):
    GPS = "gps"
    IMU = "imu"
    LIDAR = "lidar"
    CAMERA = "camera"
    TEMPERATURE = "temperature"
    BATTERY = "battery"
    SONAR = "sonar"
    INFRARED = "infrared"


@dataclass
class Position:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())

    def distance_to(self, other: Position) -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2) ** 0.5


@dataclass
class Orientation:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


@dataclass
class RoverIdentity:
    node_id: NodeId
    rover_id: RoverId
    role: RoverRole = RoverRole.GENERAL
    version: str = "0.1.0"
    capabilities: list[str] = field(default_factory=list)


@dataclass
class SensorReading:
    sensor_type: SensorType
    rover_id: RoverId
    value: Any
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    metadata: Metadata = field(default_factory=dict)


@dataclass
class TelemetryPacket:
    rover_id: RoverId
    position: Position
    orientation: Orientation
    battery_level: float
    speed: float
    heading: float
    status: RoverStatus
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    extra: Metadata = field(default_factory=dict)


@dataclass
class Task:
    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[RoverId] = None
    priority: int = 0
    payload: Payload = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    deadline: Optional[float] = None


@dataclass
class MessageEnvelope:
    msg_type: MessageType
    sender: NodeId
    receiver: Optional[NodeId]
    payload: Payload
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    signature: Optional[str] = None
    sequence: int = 0


from typing import Optional
