from __future__ import annotations

from typing import Any

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.gcounter import GCounter
from rover_swarm.crdt.lwwmap import LwwMap
from rover_swarm.crdt.lwwreg import LwwReg
from rover_swarm.crdt.rover_state import RoverState
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


class SwarmState(Crdt):
    """Aggregate CRDT state for the entire swarm.

    Tracks all rovers, swarm-level metrics, topology, and mission context.
    """

    def __init__(
        self,
        swarm_id: str,
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self.swarm_id = swarm_id
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self._rovers: dict[str, RoverState] = {}
        self.swarm_metadata = LwwMap(node_id=node_id)
        self.topology = LwwMap(node_id=node_id)
        self.mission_plan = LwwMap(node_id=node_id)
        self.total_tasks = GCounter(node_id=node_id)
        self.completed_tasks = GCounter(node_id=node_id)
        self.failed_tasks = GCounter(node_id=node_id)
        self.leader_id = LwwReg(value=None, node_id=node_id)

    def value(self) -> dict[str, Any]:
        return {
            "swarm_id": self.swarm_id,
            "rover_count": len(self._rovers),
            "rovers": {rid: r.value() for rid, r in self._rovers.items()},
            "metadata": self.swarm_metadata.value(),
            "topology": self.topology.value(),
            "mission_plan": self.mission_plan.value(),
            "total_tasks": self.total_tasks.value(),
            "completed_tasks": self.completed_tasks.value(),
            "failed_tasks": self.failed_tasks.value(),
            "leader": self.leader_id.value(),
        }

    def add_rover(self, state: RoverState) -> None:
        self._rovers[state.rover_id] = state

    def get_rover(self, rover_id: str) -> RoverState | None:
        return self._rovers.get(rover_id)

    def remove_rover(self, rover_id: str) -> None:
        self._rovers.pop(rover_id, None)

    def rover_ids(self) -> list[str]:
        return list(self._rovers.keys())

    def active_rovers(self) -> list[RoverState]:
        return [r for r in self._rovers.values() if r.status.value() == "online"]

    def set_leader(self, rover_id: str) -> None:
        self.leader_id.set(rover_id)

    def merge(self, other: Crdt) -> SwarmState:
        if not isinstance(other, SwarmState):
            raise CrdtMergeError(f"Cannot merge SwarmState with {type(other)}")
        if self.swarm_id != other.swarm_id:
            raise CrdtMergeError(f"Swarm ID mismatch: {self.swarm_id} vs {other.swarm_id}")
        merged = SwarmState(
            swarm_id=self.swarm_id,
            node_id=self._node_id,
            vector_clock=self._vector_clock.merge(other._vector_clock),
        )
        merged.swarm_metadata = self.swarm_metadata.merge(other.swarm_metadata)
        merged.topology = self.topology.merge(other.topology)
        merged.mission_plan = self.mission_plan.merge(other.mission_plan)
        merged.total_tasks = self.total_tasks.merge(other.total_tasks)
        merged.completed_tasks = self.completed_tasks.merge(other.completed_tasks)
        merged.failed_tasks = self.failed_tasks.merge(other.failed_tasks)
        merged.leader_id = self.leader_id.merge(other.leader_id)
        all_rovers = set(self._rovers) | set(other._rovers)
        for rid in all_rovers:
            self_rover = self._rovers.get(rid)
            other_rover = other._rovers.get(rid)
            if self_rover and other_rover:
                merged._rovers[rid] = self_rover.merge(other_rover)
            elif self_rover:
                merged._rovers[rid] = self_rover
            elif other_rover:
                merged._rovers[rid] = other_rover
        return merged

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value={
                "swarm_id": self.swarm_id,
                "rover_count": len(self._rovers),
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
            "sid": self.swarm_id,
            "n": self._node_id,
            "vc": self._vector_clock.to_dict(),
            "r": {rid: rs.to_binary() for rid, rs in self._rovers.items()},
            "sm": self.swarm_metadata.to_binary(),
            "tp": self.topology.to_binary(),
            "mp": self.mission_plan.to_binary(),
            "tt": self.total_tasks.to_binary(),
            "ct": self.completed_tasks.to_binary(),
            "ft": self.failed_tasks.to_binary(),
            "ld": self.leader_id.to_binary(),
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> SwarmState:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        state = cls(swarm_id=decoded.get("sid", ""), node_id=decoded.get("n", NODE_ID), vector_clock=vc)
        for rid, rs_bytes in decoded.get("r", {}).items():
            state._rovers[rid] = RoverState.from_binary(rs_bytes)
        if "sm" in decoded:
            state.swarm_metadata = LwwMap.from_binary(decoded["sm"])
        if "tp" in decoded:
            state.topology = LwwMap.from_binary(decoded["tp"])
        if "mp" in decoded:
            state.mission_plan = LwwMap.from_binary(decoded["mp"])
        if "tt" in decoded:
            state.total_tasks = GCounter.from_binary(decoded["tt"])
        if "ct" in decoded:
            state.completed_tasks = GCounter.from_binary(decoded["ct"])
        if "ft" in decoded:
            state.failed_tasks = GCounter.from_binary(decoded["ft"])
        if "ld" in decoded:
            state.leader_id = LwwReg.from_binary(decoded["ld"])
        return state

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self.swarm_metadata.reset_delta()
        self.topology.reset_delta()
        self.mission_plan.reset_delta()
        self.total_tasks.reset_delta()
        self.completed_tasks.reset_delta()
        self.failed_tasks.reset_delta()
        self.leader_id.reset_delta()
        for rover in self._rovers.values():
            rover.reset_delta()
