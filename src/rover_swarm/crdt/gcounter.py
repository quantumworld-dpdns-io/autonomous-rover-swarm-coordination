from __future__ import annotations

from dataclasses import dataclass, field

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


@dataclass
class GCounter(Crdt):
    """Grow-Only Counter CRDT.

    Only supports increment operations. Merge takes the max per node.
    """

    node_id: str = NODE_ID
    counts: dict[str, int] = field(default_factory=dict)
    _vector_clock: VectorClock = field(default_factory=lambda: VectorClock())
    _delta_counts: dict[str, int] = field(default_factory=dict)

    def value(self) -> int:
        return sum(self.counts.values())

    def increment(self, amount: int = 1) -> None:
        if amount <= 0:
            raise ValueError("Increment amount must be positive")
        current = self.counts.get(self.node_id, 0)
        new_val = current + amount
        self.counts[self.node_id] = new_val
        self._delta_counts[self.node_id] = new_val
        self._vector_clock.tick()

    def merge(self, other: Crdt) -> GCounter:
        if not isinstance(other, GCounter):
            raise CrdtMergeError(f"Cannot merge GCounter with {type(other)}")
        merged = GCounter(node_id=self.node_id)
        all_nodes = set(self.counts) | set(other.counts)
        for node in all_nodes:
            merged.counts[node] = max(self.counts.get(node, 0), other.counts.get(node, 0))
        merged._vector_clock = self._vector_clock.merge(other._vector_clock)
        return merged

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value=dict(self._delta_counts),
            vector_clock=dict(self._vector_clock),
            source_id=self.node_id,
            timestamp=0.0,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if not isinstance(delta.value, dict):
            return
        for node, count in delta.value.items():
            self.counts[node] = max(self.counts.get(node, 0), count)
        self._vector_clock.merge(
            VectorClock.from_dict(delta.vector_clock, node_id=delta.source_id)
        )

    def to_binary(self) -> bytes:
        data = {"c": dict(self.counts), "n": self.node_id, "vc": self._vector_clock.to_dict()}
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> GCounter:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        return cls(
            node_id=decoded.get("n", NODE_ID),
            counts=decoded.get("c", {}),
            _vector_clock=vc,
        )

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self._delta_counts.clear()
