from __future__ import annotations

from copy import deepcopy
from typing import Any

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.lwwreg import LwwReg
from rover_swarm.crdt.vector_clock import VectorClock
from rover_swarm.exceptions import CrdtMergeError


class LwwMap(Crdt):
    """Last-Writer-Wins Map CRDT.

    A map where each key is an independent LWW Register.
    Supports setting, deleting, and merging individual keys.
    """

    def __init__(
        self,
        node_id: str = NODE_ID,
        vector_clock: VectorClock | None = None,
    ) -> None:
        self._node_id = node_id
        self._vector_clock = vector_clock or VectorClock(node_id=node_id)
        self._data: dict[str, LwwReg] = {}
        self._delta_keys: set[str] = set()

    def _get_or_create(self, key: str) -> LwwReg:
        if key not in self._data:
            self._data[key] = LwwReg(node_id=self._node_id)
        return self._data[key]

    def value(self) -> dict[str, Any]:
        return {k: v.value() for k, v in self._data.items()}

    def get(self, key: str, default: Any = None) -> Any:
        reg = self._data.get(key)
        return reg.value() if reg else default

    def set(self, key: str, value: Any) -> None:
        reg = self._get_or_create(key)
        reg.set(value)
        self._delta_keys.add(key)
        self._vector_clock.tick()

    def delete(self, key: str) -> None:
        if key in self._data:
            self._data[key].set(None)
            self._delta_keys.add(key)
            self._vector_clock.tick()

    def contains(self, key: str) -> bool:
        reg = self._data.get(key)
        return reg is not None and reg.value() is not None

    def keys(self) -> set[str]:
        return {k for k, v in self._data.items() if v.value() is not None}

    def merge(self, other: Crdt) -> LwwMap:
        if not isinstance(other, LwwMap):
            raise CrdtMergeError(f"Cannot merge LwwMap with {type(other)}")
        merged = LwwMap(
            node_id=self._node_id,
            vector_clock=self._vector_clock.merge(other._vector_clock),
        )
        all_keys = set(self._data) | set(other._data)
        for key in all_keys:
            self_reg = self._data.get(key)
            other_reg = other._data.get(key)
            if self_reg and other_reg:
                merged._data[key] = self_reg.merge(other_reg)
            elif self_reg:
                merged._data[key] = deepcopy(self_reg)
            elif other_reg:
                merged._data[key] = deepcopy(other_reg)
        return merged

    def delta(self) -> CrdtDelta:
        delta_values = {}
        for key in self._delta_keys:
            reg = self._data.get(key)
            if reg:
                delta_values[key] = reg.value()
        return CrdtDelta(
            value=delta_values,
            vector_clock=dict(self._vector_clock),
            source_id=self._node_id,
            timestamp=0.0,
        )

    def apply_delta(self, delta: CrdtDelta) -> None:
        if not isinstance(delta.value, dict):
            return
        for key, val in delta.value.items():
            reg = self._get_or_create(key)
            reg.set(val)
        self._vector_clock.merge(
            VectorClock.from_dict(delta.vector_clock, node_id=delta.source_id)
        )

    def to_binary(self) -> bytes:
        data = {
            "d": {k: v.to_binary() for k, v in self._data.items()},
            "n": self._node_id,
            "vc": self._vector_clock.to_dict(),
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> LwwMap:
        decoded = msgpack.unpackb(data)
        vc = VectorClock.from_dict(decoded.get("vc", {}), node_id=decoded.get("n", NODE_ID))
        obj = cls(node_id=decoded.get("n", NODE_ID), vector_clock=vc)
        for key, reg_bytes in decoded.get("d", {}).items():
            obj._data[key] = LwwReg.from_binary(reg_bytes)
        return obj

    def size_bytes(self) -> int:
        return len(self.to_binary())

    def reset_delta(self) -> None:
        self._delta_keys.clear()

    def __len__(self) -> int:
        return len(self.keys())

    def __getitem__(self, key: str) -> Any:
        reg = self._data.get(key)
        if reg is None or reg.value() is None:
            raise KeyError(key)
        return reg.value()

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        self.delete(key)

    def __iter__(self):
        return iter(self.keys())
