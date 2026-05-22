from __future__ import annotations

from typing import Any, Hashable

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


class OrSet(Crdt):
    """Observed-Remove Set CRDT.

    Supports both add and remove operations. Uses tags (unique IDs) to
    track element identity. An element is in the set if at least one
    add-tag for it exists and no matching remove-tag exists.
    """

    def __init__(
        self,
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self._add_set: dict[Any, set[str]] = {}
        self._rem_set: dict[Any, set[str]] = {}
        self._delta_add: dict[Any, set[str]] = {}
        self._delta_rem: dict[Any, set[str]] = {}
        self._tag_counter: int = 0

    def value(self) -> set[Any]:
        visible: set[Any] = set()
        for elem, tags in self._add_set.items():
            removed = self._rem_set.get(elem, set())
            if tags - removed:
                visible.add(elem)
        return visible

    def _next_tag(self) -> str:
        self._tag_counter += 1
        return f"{self._node_id}:{self._tag_counter}"

    def add(self, element: Hashable) -> None:
        tag = self._next_tag()
        if element not in self._add_set:
            self._add_set[element] = set()
        self._add_set[element].add(tag)
        if element not in self._delta_add:
            self._delta_add[element] = set()
        self._delta_add[element].add(tag)
        self._vector_clock.tick()

    def remove(self, element: Hashable) -> None:
        tags = self._add_set.get(element, set())
        if not tags:
            return
        removed = self._rem_set.get(element, set())
        new_tags = tags - removed
        if not new_tags:
            return
        self._rem_set[element] = removed | new_tags
        if element not in self._delta_rem:
            self._delta_rem[element] = set()
        self._delta_rem[element] |= new_tags
        self._vector_clock.tick()

    def contains(self, element: Any) -> bool:
        add_tags = self._add_set.get(element, set())
        rem_tags = self._rem_set.get(element, set())
        return bool(add_tags - rem_tags)

    def merge(self, other: Crdt) -> OrSet:
        if not isinstance(other, OrSet):
            raise CrdtMergeError(f"Cannot merge OrSet with {type(other)}")
        merged = OrSet(
            node_id=self._node_id,
            vector_clock=self._vector_clock.merge(other._vector_clock),
        )
        all_elements = set(self._add_set) | set(other._add_set)
        for elem in all_elements:
            merged._add_set[elem] = self._add_set.get(elem, set()) | other._add_set.get(elem, set())
            merged._rem_set[elem] = self._rem_set.get(elem, set()) | other._rem_set.get(elem, set())
        return merged

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value={
                "add": {str(k): list(v) for k, v in self._delta_add.items()},
                "rem": {str(k): list(v) for k, v in self._delta_rem.items()},
            },
            vector_clock=dict(self._vector_clock),
            source_id=self._node_id,
            timestamp=0.0,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if not isinstance(delta.value, dict):
            return
        for elem_str, tags in delta.value.get("add", {}).items():
            if elem_str not in self._add_set:
                self._add_set[elem_str] = set()
            self._add_set[elem_str].update(tags)
        for elem_str, tags in delta.value.get("rem", {}).items():
            if elem_str not in self._rem_set:
                self._rem_set[elem_str] = set()
            self._rem_set[elem_str].update(tags)
        self._vector_clock.merge(
            VectorClock.from_dict(delta.vector_clock, node_id=delta.source_id)
        )

    def to_binary(self) -> bytes:
        data = {
            "a": {str(k): list(v) for k, v in self._add_set.items()},
            "r": {str(k): list(v) for k, v in self._rem_set.items()},
            "n": self._node_id,
            "vc": self._vector_clock.to_dict(),
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> OrSet:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        obj = cls(node_id=decoded.get("n", NODE_ID), vector_clock=vc)
        for elem_str, tags in decoded.get("a", {}).items():
            obj._add_set[elem_str] = set(tags)
        for elem_str, tags in decoded.get("r", {}).items():
            obj._rem_set[elem_str] = set(tags)
        return obj

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self._delta_add.clear()
        self._delta_rem.clear()

    def __len__(self) -> int:
        return len(self.value())
