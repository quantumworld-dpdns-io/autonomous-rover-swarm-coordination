from __future__ import annotations

from typing import Any

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.gcounter import GCounter
from rover_swarm.crdt.lwwmap import LwwMap
from rover_swarm.crdt.lwwreg import LwwReg
from rover_swarm.crdt.merge_engine import MergeEngine
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError
from rover_swarm.types import Position, RoverStatus


class RoverState(Crdt):
    """Composite CRDT state for a single rover.

    Combines multiple CRDT types to represent the full state of a rover:
    position, status, battery, role, tasks, sensor readings, etc.
    """

    def __init__(
        self,
        rover_id: str,
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self.rover_id = rover_id
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self._merge_engine = MergeEngine()

        self.position = LwwReg(value=None, node_id=node_id)
        self.status = LwwReg(value=RoverStatus.OFFLINE.value, node_id=node_id)
        self.battery = LwwReg(value=100.0, node_id=node_id)
        self.role = LwwReg(value="general", node_id=node_id)
        self.speed = LwwReg(value=0.0, node_id=node_id)
        self.heading = LwwReg(value=0.0, node_id=node_id)
        self.tasks = LwwMap(node_id=node_id)
        self.sensor_data = LwwMap(node_id=node_id)
        self.metrics = LwwMap(node_id=node_id)
        self.messages_sent = GCounter(node_id=node_id)
        self.messages_received = GCounter(node_id=node_id)
        self.distance_traveled = GCounter(node_id=node_id)

    def value(self) -> dict[str, Any]:
        return {
            "rover_id": self.rover_id,
            "position": self.position.value(),
            "status": self.status.value(),
            "battery": self.battery.value(),
            "role": self.role.value(),
            "speed": self.speed.value(),
            "heading": self.heading.value(),
            "tasks": self.tasks.value(),
            "messages_sent": self.messages_sent.value(),
            "messages_received": self.messages_received.value(),
            "distance_traveled": self.distance_traveled.value(),
        }

    def update_position(self, pos: Position) -> None:
        self.position.set(pos.__dict__ if hasattr(pos, "__dict__") else pos)

    def update_status(self, status: RoverStatus) -> None:
        self.status.set(status.value if isinstance(status, RoverStatus) else status)

    def update_battery(self, level: float) -> None:
        self.battery.set(max(0.0, min(100.0, level)))

    def update_role(self, role: str) -> None:
        self.role.set(role)

    def merge(self, other: Crdt) -> RoverState:
        if not isinstance(other, RoverState):
            raise CrdtMergeError(f"Cannot merge RoverState with {type(other)}")
        if self.rover_id != other.rover_id:
            raise CrdtMergeError(f"Rover ID mismatch: {self.rover_id} vs {other.rover_id}")
        merged = RoverState(
            rover_id=self.rover_id,
            node_id=self._node_id,
            vector_clock=self._vector_clock.merge(other._vector_clock),
        )
        merged.position = self.position.merge(other.position)
        merged.status = self.status.merge(other.status)
        merged.battery = self.battery.merge(other.battery)
        merged.role = self.role.merge(other.role)
        merged.speed = self.speed.merge(other.speed)
        merged.heading = self.heading.merge(other.heading)
        merged.tasks = self.tasks.merge(other.tasks)
        merged.sensor_data = self.sensor_data.merge(other.sensor_data)
        merged.metrics = self.metrics.merge(other.metrics)
        merged.messages_sent = self.messages_sent.merge(other.messages_sent)
        merged.messages_received = self.messages_received.merge(other.messages_received)
        merged.distance_traveled = self.distance_traveled.merge(other.distance_traveled)
        return merged

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value={
                "rover_id": self.rover_id,
                "position": self.position.delta(),
                "status": self.status.delta(),
                "battery": self.battery.delta(),
            },
            vector_clock=dict(self._vector_clock),
            source_id=self._node_id,
            timestamp=0.0,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if not isinstance(delta.value, dict):
            return
        self._vector_clock.merge(
            VectorClock.from_dict(delta.vector_clock, node_id=delta.source_id)
        )

    def to_binary(self) -> bytes:
        data = {
            "id": self.rover_id,
            "n": self._node_id,
            "vc": self._vector_clock.to_dict(),
            "p": self.position.to_binary(),
            "s": self.status.to_binary(),
            "b": self.battery.to_binary(),
            "r": self.role.to_binary(),
            "sp": self.speed.to_binary(),
            "h": self.heading.to_binary(),
            "t": self.tasks.to_binary(),
            "sd": self.sensor_data.to_binary(),
            "m": self.metrics.to_binary(),
            "ms": self.messages_sent.to_binary(),
            "mr": self.messages_received.to_binary(),
            "dt": self.distance_traveled.to_binary(),
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> RoverState:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        state = cls(rover_id=decoded.get("id", ""), node_id=decoded.get("n", NODE_ID), vector_clock=vc)
        if "p" in decoded:
            state.position = LwwReg.from_binary(decoded["p"])
        if "s" in decoded:
            state.status = LwwReg.from_binary(decoded["s"])
        if "b" in decoded:
            state.battery = LwwReg.from_binary(decoded["b"])
        if "r" in decoded:
            state.role = LwwReg.from_binary(decoded["r"])
        if "sp" in decoded:
            state.speed = LwwReg.from_binary(decoded["sp"])
        if "h" in decoded:
            state.heading = LwwReg.from_binary(decoded["h"])
        if "t" in decoded:
            state.tasks = LwwMap.from_binary(decoded["t"])
        if "sd" in decoded:
            state.sensor_data = LwwMap.from_binary(decoded["sd"])
        if "m" in decoded:
            state.metrics = LwwMap.from_binary(decoded["m"])
        if "ms" in decoded:
            state.messages_sent = GCounter.from_binary(decoded["ms"])
        if "mr" in decoded:
            state.messages_received = GCounter.from_binary(decoded["mr"])
        if "dt" in decoded:
            state.distance_traveled = GCounter.from_binary(decoded["dt"])
        return state

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        for attr in ("position", "status", "battery", "role", "speed", "heading"):
            getattr(self, attr).reset_delta()
        self.tasks.reset_delta()
        self.sensor_data.reset_delta()
        self.metrics.reset_delta()
        self.messages_sent.reset_delta()
        self.messages_received.reset_delta()
        self.distance_traveled.reset_delta()
