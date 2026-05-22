from __future__ import annotations

from copy import deepcopy
from typing import Any, Generic

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


class LwwReg(Crdt):
    """Last-Writer-Wins Register CRDT.

    Resolves concurrent writes by timestamp: the most recent write wins.
    For identical timestamps, the highest node_id (lexicographic) wins.
    """

    def __init__(
        self,
        value: Any = None,
        timestamp: float = 0.0,
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self._value = value
        self._timestamp = timestamp
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self._delta_value: Any = None
        self._delta_timestamp: float = 0.0
        self._delta_node_id: str = node_id

    def value(self) -> Any:
        return self._value

    def set(self, new_value: Any, timestamp: float | None = None) -> None:
        ts = timestamp if timestamp is not None else __import__("time").time()
        if ts > self._timestamp or (ts == self._timestamp and self._node_id > self._delta_node_id):
            self._delta_value = new_value
            self._delta_timestamp = ts
            self._delta_node_id = self._node_id
            self._value = new_value
            self._timestamp = ts
            self._vector_clock.tick()

    def merge(self, other: Crdt) -> LwwReg:
        if not isinstance(other, LwwReg):
            raise CrdtMergeError(f"Cannot merge LwwReg with {type(other)}")
        merged = LwwReg(value=self._value, timestamp=self._timestamp, node_id=self._node_id)
        merged._vector_clock = self._vector_clock.merge(other._vector_clock)
        if other._timestamp > self._timestamp or (
            other._timestamp == self._timestamp and other._node_id > self._node_id
        ):
            merged._value = deepcopy(other._value)
            merged._timestamp = other._timestamp
            merged._node_id = other._node_id
        return merged

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value=self._delta_value,
            vector_clock=dict(self._vector_clock),
            source_id=self._delta_node_id,
            timestamp=self._delta_timestamp,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if delta.timestamp > self._timestamp or (
            delta.timestamp == self._timestamp and delta.source_id > self._node_id
        ):
            self._value = deepcopy(delta.value)
            self._timestamp = delta.timestamp
            self._node_id = delta.source_id
        self._vector_clock.merge(
            VectorClock.from_dict(delta.vector_clock, node_id=delta.source_id)
        )

    def to_binary(self) -> bytes:
        data = {
            "v": self._value,
            "ts": self._timestamp,
            "n": self._node_id,
            "vc": self._vector_clock.to_dict(),
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> LwwReg:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        return cls(
            value=decoded.get("v"),
            timestamp=decoded.get("ts", 0.0),
            node_id=decoded.get("n", NODE_ID),
            vector_clock=vc,
        )

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self._delta_value = None
        self._delta_timestamp = 0.0
