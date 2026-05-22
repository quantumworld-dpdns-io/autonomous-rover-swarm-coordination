from __future__ import annotations

from typing import Any, Hashable

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


class MvReg(Crdt):
    """Multi-Value Register CRDT.

    Maintains all concurrently-written values as a set. When values are
    causally related, only the latest survives. This ensures no data is
    lost during concurrent writes.
    """

    def __init__(
        self,
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self._values: dict[str, tuple[Any, VectorClock]] = {}

    def value(self) -> list[Any]:
        """Return all concurrent values (usually 1, but can be >1)."""
        if not self._values:
            return []
        max_vc = max((vc for _, vc in self._values.values()), key=lambda vc: list(vc.clocks.values()))
        concurrent = [v for v, vc in self._values.values() if vc.concurrent(max_vc) or vc == max_vc]
        return concurrent

    def write(self, value: Hashable) -> None:
        tag = f"{self._node_id}:{self._vector_clock.tick()}"
        self._vector_clock.tick()
        self._values[tag] = (value, self._vector_clock.copy())

    def merge(self, other: Crdt) -> MvReg:
        if not isinstance(other, MvReg):
            raise CrdtMergeError(f"Cannot merge MvReg with {type(other)}")
        merged = MvReg(
            node_id=self._node_id,
            vector_clock=self._vector_clock.merge(other._vector_clock),
        )
        all_tags = set(self._values) | set(other._values)
        for tag in all_tags:
            if tag in self._values and tag in other._values:
                s_val, s_vc = self._values[tag]
                o_val, o_vc = other._values[tag]
                merged._values[tag] = (s_val, s_vc) if list(s_vc.clocks.values()) >= list(o_vc.clocks.values()) else (o_val, o_vc)
            elif tag in self._values:
                merged._values[tag] = self._values[tag]
            else:
                merged._values[tag] = other._values[tag]
        merged._prune_ancestors()
        return merged

    def _prune_ancestors(self) -> None:
        tags = list(self._values.keys())
        for i, t1 in enumerate(tags):
            for t2 in tags[i + 1:]:
                vc1 = self._values[t1][1]
                vc2 = self._values[t2][1]
                if vc1.happens_before(vc2):
                    self._values.pop(t1, None)
                    break
                elif vc2.happens_before(vc1):
                    self._values.pop(t2, None)

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value={k: v for k, (v, _) in self._values.items()},
            vector_clock=dict(self._vector_clock),
            source_id=self._node_id,
            timestamp=0.0,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if not isinstance(delta.value, dict):
            return
        incoming_vc = VectorClock.from_dict(delta.vector_clock, node_id=delta.source_id)
        for tag, val in delta.value.items():
            if tag not in self._values:
                self._values[tag] = (val, incoming_vc)
        self._vector_clock.merge(incoming_vc)
        self._prune_ancestors()

    def to_binary(self) -> bytes:
        data = {
            "v": {k: v for k, (v, _) in self._values.items()},
            "vc": {k: list(vc.clocks.items()) for k, (_, vc) in self._values.items()},
            "n": self._node_id,
            "gvc": self._vector_clock.to_dict(),
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> MvReg:
        decoded = msgpack.unpackb(data)
        gvc = VectorClock.from_dict(decoded.get("gvc", {}), node_id=decoded.get("n", NODE_ID))
        obj = cls(node_id=decoded.get("n", NODE_ID), vector_clock=gvc)
        vals = decoded.get("v", {})
        vcs = decoded.get("vc", {})
        for tag, val in vals.items():
            vc_data = vcs.get(tag, [])
            vc = VectorClock(node_id=obj._node_id, clocks=dict(vc_data))
            obj._values[tag] = (val, vc)
        return obj

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        pass
