from __future__ import annotations

from typing import Any, Hashable

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


class GSet(Crdt):
    """Grow-Only Set CRDT.

    Elements can only be added, never removed. Merge takes the union.
    """

    def __init__(
        self,
        elements: set[Any] | None = None,
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self._elements: set[Any] = set(elements) if elements else set()
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self._delta_elements: set[Any] = set()

    def value(self) -> set[Any]:
        return set(self._elements)

    def add(self, element: Hashable) -> None:
        if element not in self._elements:
            self._elements.add(element)
            self._delta_elements.add(element)
            self._vector_clock.tick()

    def contains(self, element: Any) -> bool:
        return element in self._elements

    def merge(self, other: Crdt) -> GSet:
        if not isinstance(other, GSet):
            raise CrdtMergeError(f"Cannot merge GSet with {type(other)}")
        merged = GSet(
            elements=self._elements | other._elements,
            node_id=self._node_id,
            vector_clock=self._vector_clock.merge(other._vector_clock),
        )
        return merged

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value=list(self._delta_elements),
            vector_clock=dict(self._vector_clock),
            source_id=self._node_id,
            timestamp=0.0,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if isinstance(delta.value, list):
            self._elements.update(delta.value)
        self._vector_clock.merge(
            VectorClock.from_dict(delta.vector_clock, node_id=delta.source_id)
        )

    def to_binary(self) -> bytes:
        data = {
            "e": list(self._elements),
            "n": self._node_id,
            "vc": self._vector_clock.to_dict(),
        }
        return msgpack.packb(data, use_bin_type=True)

    @classmethod
    def from_binary(cls, data: bytes) -> GSet:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        return cls(
            elements=set(decoded.get("e", [])),
            node_id=decoded.get("n", NODE_ID),
            vector_clock=vc,
        )

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self._delta_elements.clear()

    def __len__(self) -> int:
        return len(self._elements)

    def __iter__(self):
        return iter(self._elements)
