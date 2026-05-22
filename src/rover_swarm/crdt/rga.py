from __future__ import annotations

from typing import Any

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


class Rga(Crdt):
    """Replicated Growable Array (RGA) CRDT.

    A sequence CRDT that supports insert and delete operations.
    Uses a linked-list structure with unique identifiers per element.
    """

    def __init__(
        self,
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self._elements: dict[str, dict] = {}
        self._head: str | None = None
        self._tag_counter: int = 0
        self._delta_ops: list[dict] = []

    def _next_tag(self) -> str:
        self._tag_counter += 1
        return f"{self._node_id}:{self._tag_counter}"

    def value(self) -> list[Any]:
        result: list[Any] = []
        current = self._head
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            elem = self._elements.get(current)
            if elem is None:
                break
            if not elem.get("deleted", False):
                result.append(elem["value"])
            current = elem.get("next")
        return result

    def insert_after(self, after_tag: str | None, value: Any) -> str:
        tag = self._next_tag()
        elem = {
            "id": tag,
            "value": value,
            "next": None,
            "deleted": False,
            "origin": self._node_id,
        }
        self._elements[tag] = elem
        if after_tag is None:
            elem["next"] = self._head
            self._head = tag
        else:
            parent = self._elements.get(after_tag)
            if parent:
                elem["next"] = parent.get("next")
                parent["next"] = tag
        self._delta_ops.append({"op": "insert", "after": after_tag, "elem": elem})
        self._vector_clock.tick()
        return tag

    def append(self, value: Any) -> str:
        if self._head is None:
            return self.insert_after(None, value)
        current = self._head
        while current:
            elem = self._elements.get(current)
            if elem and elem.get("next") is None:
                return self.insert_after(current, value)
            current = elem.get("next") if elem else None
        return self.insert_after(None, value)

    def delete(self, tag: str) -> None:
        elem = self._elements.get(tag)
        if elem and not elem["deleted"]:
            elem["deleted"] = True
            self._delta_ops.append({"op": "delete", "id": tag})
            self._vector_clock.tick()

    def merge(self, other: Crdt) -> Rga:
        if not isinstance(other, Rga):
            raise CrdtMergeError(f"Cannot merge Rga with {type(other)}")
        merged = Rga(
            node_id=self._node_id,
            vector_clock=self._vector_clock.merge(other._vector_clock),
        )
        all_ids = set(self._elements) | set(other._elements)
        for eid in all_ids:
            self_elem = self._elements.get(eid)
            other_elem = other._elements.get(eid)
            if self_elem and other_elem:
                merged._elements[eid] = {
                    "id": eid,
                    "value": other_elem["value"] if other_elem.get("origin", "") > self_elem.get("origin", "") else self_elem["value"],
                    "next": other_elem.get("next") if other_elem.get("origin", "") > self_elem.get("origin", "") else self_elem.get("next"),
                    "deleted": self_elem.get("deleted", False) and other_elem.get("deleted", False),
                    "origin": max(self_elem.get("origin", ""), other_elem.get("origin", "")),
                }
            elif self_elem:
                merged._elements[eid] = dict(self_elem)
            elif other_elem:
                merged._elements[eid] = dict(other_elem)
        merged._head = self._head or other._head
        return merged

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value=list(self._delta_ops),
            vector_clock=dict(self._vector_clock),
            source_id=self._node_id,
            timestamp=0.0,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if not isinstance(delta.value, list):
            return
        for op in delta.value:
            if op.get("op") == "insert":
                elem = op["elem"]
                self._elements[elem["id"]] = elem
                if op.get("after") is None:
                    self._head = elem["id"]
                elif op["after"] in self._elements:
                    self._elements[op["after"]]["next"] = elem["id"]
            elif op.get("op") == "delete":
                elem = self._elements.get(op["id"])
                if elem:
                    elem["deleted"] = True
        self._vector_clock.merge(
            VectorClock.from_dict(delta.vector_clock, node_id=delta.source_id)
        )

    def to_binary(self) -> bytes:
        data = {
            "e": {k: v for k, v in self._elements.items()},
            "h": self._head,
            "n": self._node_id,
            "vc": self._vector_clock.to_dict(),
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> Rga:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        obj = cls(node_id=decoded.get("n", NODE_ID), vector_clock=vc)
        obj._elements = decoded.get("e", {})
        obj._head = decoded.get("h")
        return obj

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self._delta_ops.clear()

    def __len__(self) -> int:
        return len(self.value())

    def __getitem__(self, index: int) -> Any:
        return self.value()[index]

    def __iter__(self):
        return iter(self.value())
