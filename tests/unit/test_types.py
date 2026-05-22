from __future__ import annotations

from dataclasses import fields

from rover_swarm.types import (
    MessageEnvelope,
    MissionPhase,
    Orientation,
    Position,
    RoverIdentity,
    RoverRole,
    RoverStatus,
    SensorReading,
    SensorType,
    Task,
    TaskStatus,
    TaskType,
    TelemetryPacket,
)


class TestEnums:
    def test_rover_role_values(self) -> None:
        assert RoverRole.SCOUT.value == "scout"
        assert RoverRole.TRANSPORTER.value == "transporter"
        assert RoverRole.RELAY.value == "relay"
        assert RoverRole.CHARGER.value == "charger"
        assert RoverRole.GENERAL.value == "general"

    def test_rover_status_values(self) -> None:
        assert RoverStatus.ONLINE.value == "online"
        assert RoverStatus.OFFLINE.value == "offline"
        assert RoverStatus.BUSY.value == "busy"
        assert RoverStatus.CHARGING.value == "charging"
        assert RoverStatus.ERROR.value == "error"
        assert RoverStatus.RECOVERING.value == "recovering"
        assert RoverStatus.PARTITIONED.value == "partitioned"

    def test_mission_phase_values(self) -> None:
        assert MissionPhase.INITIALIZING.value == "initializing"
        assert MissionPhase.DEPLOYING.value == "deploying"
        assert MissionPhase.EXPLORING.value == "exploring"
        assert MissionPhase.RETURNING.value == "returning"
        assert MissionPhase.COMPLETED.value == "completed"
        assert MissionPhase.FAILED.value == "failed"
        assert MissionPhase.ABORTED.value == "aborted"

    def test_task_type_values(self) -> None:
        assert TaskType.EXPLORE.value == "explore"
        assert TaskType.SURVEY.value == "survey"
        assert TaskType.TRANSPORT.value == "transport"
        assert TaskType.RELAY.value == "relay"
        assert TaskType.CHARGE.value == "charge"
        assert TaskType.RECONNAISSANCE.value == "reconnaissance"
        assert TaskType.PATROL.value == "patrol"

    def test_task_status_values(self) -> None:
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.ASSIGNED.value == "assigned"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_sensor_type_values(self) -> None:
        assert SensorType.GPS.value == "gps"
        assert SensorType.IMU.value == "imu"
        assert SensorType.LIDAR.value == "lidar"
        assert SensorType.CAMERA.value == "camera"
        assert SensorType.TEMPERATURE.value == "temperature"
        assert SensorType.BATTERY.value == "battery"
        assert SensorType.SONAR.value == "sonar"
        assert SensorType.INFRARED.value == "infrared"


class TestPosition:
    def test_defaults(self) -> None:
        pos = Position()
        assert pos.x == 0.0
        assert pos.y == 0.0
        assert pos.z == 0.0

    def test_distance_to(self) -> None:
        a = Position(x=0.0, y=0.0)
        b = Position(x=3.0, y=4.0)
        assert a.distance_to(b) == 5.0

    def test_timestamp(self) -> None:
        pos = Position()
        assert pos.timestamp > 0


class TestOrientation:
    def test_defaults(self) -> None:
        o = Orientation()
        assert o.roll == 0.0
        assert o.pitch == 0.0
        assert o.yaw == 0.0


class TestRoverIdentity:
    def test_fields(self) -> None:
        identity = RoverIdentity(node_id="node-1", rover_id="rover-1")
        assert identity.node_id == "node-1"
        assert identity.rover_id == "rover-1"
        assert identity.role == RoverRole.GENERAL
        assert identity.version == "0.1.0"


class TestSensorReading:
    def test_fields(self) -> None:
        reading = SensorReading(
            sensor_type=SensorType.GPS,
            rover_id="rover-1",
            value={"lat": 51.5, "lon": -0.1},
        )
        assert reading.sensor_type == SensorType.GPS
        assert reading.rover_id == "rover-1"
        assert reading.value == {"lat": 51.5, "lon": -0.1}


class TestTelemetryPacket:
    def test_fields(self) -> None:
        pos = Position(x=1.0, y=2.0)
        orient = Orientation(roll=0.1, pitch=0.2, yaw=0.3)
        packet = TelemetryPacket(
            rover_id="rover-1",
            position=pos,
            orientation=orient,
            battery_level=85.0,
            speed=1.5,
            heading=45.0,
            status=RoverStatus.ONLINE,
        )
        assert packet.rover_id == "rover-1"
        assert packet.battery_level == 85.0
        assert packet.speed == 1.5


class TestTask:
    def test_fields(self) -> None:
        task = Task(
            task_id="task-1",
            task_type=TaskType.EXPLORE,
            priority=5,
        )
        assert task.task_id == "task-1"
        assert task.task_type == TaskType.EXPLORE
        assert task.status == TaskStatus.PENDING
        assert task.priority == 5


class TestMessageEnvelope:
    def test_fields(self) -> None:
        msg = MessageEnvelope(
            msg_type="crdt_sync",
            sender="rover-1",
            receiver="rover-2",
            payload={"seq": 1},
        )
        assert msg.msg_type == "crdt_sync"
        assert msg.sender == "rover-1"
        assert msg.receiver == "rover-2"
        assert msg.payload == {"seq": 1}
        assert msg.sequence == 0
        assert msg.signature is None


class TestDataclassIntegrity:
    def test_all_dataclasses_have_type_hints(self) -> None:
        dataclasses = [
            Position,
            Orientation,
            RoverIdentity,
            SensorReading,
            TelemetryPacket,
            Task,
            MessageEnvelope,
        ]
        for dc in dataclasses:
            for f in fields(dc):
                assert f.type is not None, f"{dc.__name__}.{f.name} lacks type hint"
