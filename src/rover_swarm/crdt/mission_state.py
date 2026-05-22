from __future__ import annotations

from typing import Any

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.gcounter import GCounter
from rover_swarm.crdt.lwwmap import LwwMap
from rover_swarm.crdt.lwwreg import LwwReg
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError
from rover_swarm.types import MissionPhase, TaskStatus, TaskType


class MissionState(Crdt):
    """CRDT state for a mission plan.

    Tracks mission phase, tasks, assigned rovers, progress, and results.
    """

    def __init__(
        self,
        mission_id: str,
        name: str = "",
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self.mission_id = mission_id
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self.name = LwwReg(value=name, node_id=node_id)
        self.phase = LwwReg(value=MissionPhase.INITIALIZING.value, node_id=node_id)
        self.tasks = LwwMap(node_id=node_id)
        self.assigned_rovers = LwwMap(node_id=node_id)
        self.metadata = LwwMap(node_id=node_id)
        self.progress = LwwReg(value=0.0, node_id=node_id)
        self.completed_objectives = GCounter(node_id=node_id)
        self.total_objectives = GCounter(node_id=node_id)
        self.errors = GCounter(node_id=node_id)

    def value(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "name": self.name.value(),
            "phase": self.phase.value(),
            "tasks": self.tasks.value(),
            "assigned_rovers": self.assigned_rovers.value(),
            "metadata": self.metadata.value(),
            "progress": self.progress.value(),
            "completed_objectives": self.completed_objectives.value(),
            "total_objectives": self.total_objectives.value(),
            "errors": self.errors.value(),
        }

    def set_phase(self, phase: MissionPhase) -> None:
        self.phase.set(phase.value if isinstance(phase, MissionPhase) else phase)

    def add_task(self, task_id: str, task_type: str, payload: dict[str, Any] | None = None) -> None:
        self.tasks.set(task_id, {
            "task_id": task_id,
            "type": task_type,
            "status": TaskStatus.PENDING.value,
            "payload": payload or {},
            "assigned_to": None,
        })

    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        task = self.tasks.get(task_id)
        if task and isinstance(task, dict):
            task["status"] = status.value if isinstance(status, TaskStatus) else status
            self.tasks.set(task_id, task)

    def assign_rover(self, rover_id: str, role: str = "member") -> None:
        self.assigned_rovers.set(rover_id, {"rover_id": rover_id, "role": role, "joined_at": __import__("time").time()})

    def remove_rover(self, rover_id: str) -> None:
        self.assigned_rovers.delete(rover_id)

    def advance_progress(self, delta: float = 0.1) -> None:
        current = self.progress.value() or 0.0
        self.progress.set(min(1.0, current + delta))

    def complete_objective(self) -> None:
        self.completed_objectives.increment(1)

    def merge(self, other: Crdt) -> MissionState:
        if not isinstance(other, MissionState):
            raise CrdtMergeError(f"Cannot merge MissionState with {type(other)}")
        if self.mission_id != other.mission_id:
            raise CrdtMergeError(f"Mission ID mismatch: {self.mission_id} vs {other.mission_id}")
        merged = MissionState(
            mission_id=self.mission_id,
            node_id=self._node_id,
            vector_clock=self._vector_clock.merge(other._vector_clock),
        )
        merged.name = self.name.merge(other.name)
        merged.phase = self.phase.merge(other.phase)
        merged.tasks = self.tasks.merge(other.tasks)
        merged.assigned_rovers = self.assigned_rovers.merge(other.assigned_rovers)
        merged.metadata = self.metadata.merge(other.metadata)
        merged.progress = self.progress.merge(other.progress)
        merged.completed_objectives = self.completed_objectives.merge(other.completed_objectives)
        merged.total_objectives = self.total_objectives.merge(other.total_objectives)
        merged.errors = self.errors.merge(other.errors)
        return merged

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value={
                "mission_id": self.mission_id,
                "phase": self.phase.value(),
                "progress": self.progress.value(),
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
            "mid": self.mission_id,
            "n": self._node_id,
            "vc": self._vector_clock.to_dict(),
            "nm": self.name.to_binary(),
            "ph": self.phase.to_binary(),
            "tk": self.tasks.to_binary(),
            "ar": self.assigned_rovers.to_binary(),
            "md": self.metadata.to_binary(),
            "pr": self.progress.to_binary(),
            "co": self.completed_objectives.to_binary(),
            "to": self.total_objectives.to_binary(),
            "er": self.errors.to_binary(),
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> MissionState:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        state = cls(mission_id=decoded.get("mid", ""), node_id=decoded.get("n", NODE_ID), vector_clock=vc)
        if "nm" in decoded:
            state.name = LwwReg.from_binary(decoded["nm"])
        if "ph" in decoded:
            state.phase = LwwReg.from_binary(decoded["ph"])
        if "tk" in decoded:
            state.tasks = LwwMap.from_binary(decoded["tk"])
        if "ar" in decoded:
            state.assigned_rovers = LwwMap.from_binary(decoded["ar"])
        if "md" in decoded:
            state.metadata = LwwMap.from_binary(decoded["md"])
        if "pr" in decoded:
            state.progress = LwwReg.from_binary(decoded["pr"])
        if "co" in decoded:
            state.completed_objectives = GCounter.from_binary(decoded["co"])
        if "to" in decoded:
            state.total_objectives = GCounter.from_binary(decoded["to"])
        if "er" in decoded:
            state.errors = GCounter.from_binary(decoded["er"])
        return state

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self.name.reset_delta()
        self.phase.reset_delta()
        self.tasks.reset_delta()
        self.assigned_rovers.reset_delta()
        self.metadata.reset_delta()
        self.progress.reset_delta()
        self.completed_objectives.reset_delta()
        self.total_objectives.reset_delta()
        self.errors.reset_delta()
