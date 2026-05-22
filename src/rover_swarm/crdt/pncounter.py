from __future__ import annotations

from dataclasses import dataclass, field

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.gcounter import GCounter
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


class PnCounter(Crdt):
    """Positive-Negative Counter CRDT.

    Supports both increment and decrement using two GCounters.
    """

    def __init__(
        self,
        pos: GCounter | None = None,
        neg: GCounter | None = None,
        node_id: str = NODE_ID,
    ) -> None:
        self._pos = pos or GCounter(node_id=node_id)
        self._neg = neg or GCounter(node_id=node_id)
        self._node_id = node_id

    def value(self) -> int:
        return self._pos.value() - self._neg.value()

    def increment(self, amount: int = 1) -> None:
        self._pos.increment(amount)

    def decrement(self, amount: int = 1) -> None:
        self._neg.increment(amount)

    def merge(self, other: Crdt) -> PnCounter:
        if not isinstance(other, PnCounter):
            raise CrdtMergeError(f"Cannot merge PnCounter with {type(other)}")
        return PnCounter(
            pos=self._pos.merge(other._pos),
            neg=self._neg.merge(other._neg),
            node_id=self._node_id,
        )

    def delta(self) -> CrdtDelta:
        return CrdtDelta(
            value={"pos": self._pos._delta_counts, "neg": self._neg._delta_counts},
            vector_clock={},
            source_id=self._node_id,
            timestamp=0.0,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if not isinstance(delta.value, dict):
            return
        if "pos" in delta.value:
            for node, count in delta.value["pos"].items():
                self._pos.counts[node] = max(self._pos.counts.get(node, 0), count)
        if "neg" in delta.value:
            for node, count in delta.value["neg"].items():
                self._neg.counts[node] = max(self._neg.counts.get(node, 0), count)

    def to_binary(self) -> bytes:
        data = {
            "p": self._pos.to_binary(),
            "n": self._neg.to_binary(),
            "id": self._node_id,
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> PnCounter:
        decoded = msgpack.unpackb(data)
        pos = GCounter.from_binary(decoded["p"])
        neg = GCounter.from_binary(decoded["n"])
        return cls(pos=pos, neg=neg, node_id=decoded.get("id", NODE_ID))

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self._pos.reset_delta()
        self._neg.reset_delta()
