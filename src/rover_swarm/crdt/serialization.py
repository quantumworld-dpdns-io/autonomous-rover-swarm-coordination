from __future__ import annotations

from typing import Any

import msgpack

from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.crdt.gcounter import GCounter
from rover_swarm.crdt.gset import GSet
from rover_swarm.crdt.lwwmap import LwwMap
from rover_swarm.crdt.lwwreg import LwwReg
from rover_swarm.crdt.mvreg import MvReg
from rover_swarm.crdt.orset import OrSet
from rover_swarm.crdt.pncounter import PnCounter
from rover_swarm.crdt.rga import Rga
from rover_swarm.exceptions import CrdtSerializationError

CRDT_TYPE_MAP: dict[str, type[Crdt]] = {
    "LwwReg": LwwReg,
    "GCounter": GCounter,
    "PnCounter": PnCounter,
    "GSet": GSet,
    "OrSet": OrSet,
    "LwwMap": LwwMap,
    "MvReg": MvReg,
    "Rga": Rga,
    "RoverState": RoverState,
    "SwarmState": SwarmState,
    "MissionState": MissionState,
}


class CrdtSerializer:
    @staticmethod
    def serialize(crdt: Crdt) -> bytes:
        type_name = type(crdt).__name__
        payload = crdt.to_binary()
        envelope = {"type": type_name, "payload": payload}
        return msgpack.packb(envelope)

    @staticmethod
    def serialize_delta(delta: CrdtDelta, crdt_type: type[Crdt]) -> bytes:
        envelope = {
            "type": crdt_type.__name__,
            "delta": {
                "value": delta.value,
                "vector_clock": delta.vector_clock,
                "source_id": delta.source_id,
                "timestamp": delta.timestamp,
            },
        }
        return msgpack.packb(envelope)


class CrdtDeserializer:
    @staticmethod
    def deserialize(data: bytes) -> Crdt:
        try:
            envelope = msgpack.unpackb(data)
        except Exception as e:
            raise CrdtSerializationError(f"Failed to unpack: {e}")
        type_name = envelope.get("type", "")
        crdt_cls = CRDT_TYPE_MAP.get(type_name)
        if crdt_cls is None:
            raise CrdtSerializationError(f"Unknown CRDT type: {type_name}")
        payload = envelope.get("payload", b"")
        if isinstance(payload, list):
            payload = bytes(payload)
        return crdt_cls.from_binary(payload)

    @staticmethod
    def deserialize_delta(data: bytes) -> tuple[CrdtDelta, type[Crdt]]:
        try:
            envelope = msgpack.unpackb(data)
        except Exception as e:
            raise CrdtSerializationError(f"Failed to unpack delta: {e}")
        type_name = envelope.get("type", "")
        crdt_cls = CRDT_TYPE_MAP.get(type_name)
        if crdt_cls is None:
            raise CrdtSerializationError(f"Unknown CRDT type in delta: {type_name}")
        delta_data = envelope.get("delta", {})
        delta = CrdtDelta(
            value=delta_data.get("value"),
            vector_clock=delta_data.get("vector_clock", {}),
            source_id=delta_data.get("source_id", ""),
            timestamp=delta_data.get("timestamp", 0.0),
        )
        return delta, crdt_cls
