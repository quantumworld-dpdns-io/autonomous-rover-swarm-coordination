from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import msgpack

from rover_swarm.constants import NODE_ID
from rover_swarm.types import MessageType


@dataclass
class SignedMessage:
    signature: str
    sender: str
    timestamp: float


@dataclass
class MessageEnvelope:
    msg_type: MessageType
    sender: str
    receiver: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    sequence: int = 0
    ttl: int = 60
    correlation_id: str | None = None

    def to_binary(self) -> bytes:
        data = {
            "t": self.msg_type.value if isinstance(self.msg_type, MessageType) else self.msg_type,
            "s": self.sender,
            "r": self.receiver,
            "p": self.payload,
            "ts": self.timestamp,
            "seq": self.sequence,
            "ttl": self.ttl,
            "cid": self.correlation_id,
        }
        return msgpack.packb(data)

    @classmethod
    def from_binary(cls, data: bytes) -> MessageEnvelope:
        decoded = msgpack.unpackb(data)
        return cls(
            msg_type=MessageType(decoded.get("t", "unknown")),
            sender=decoded.get("s", ""),
            receiver=decoded.get("r"),
            payload=decoded.get("p", {}),
            timestamp=decoded.get("ts", 0.0),
            sequence=decoded.get("seq", 0),
            ttl=decoded.get("ttl", 60),
            correlation_id=decoded.get("cid"),
        )

    @classmethod
    def heartbeat(cls, node_id: str = NODE_ID) -> MessageEnvelope:
        return cls(
            msg_type=MessageType.HEARTBEAT,
            sender=node_id,
            payload={"node_id": node_id, "timestamp": datetime.now(timezone.utc).timestamp()},
        )

    @classmethod
    def command(cls, target: str, command: str, params: dict[str, Any] | None = None) -> MessageEnvelope:
        return cls(
            msg_type=MessageType.COMMAND,
            sender=NODE_ID,
            receiver=target,
            payload={"command": command, "params": params or {}},
        )

    @classmethod
    def telemetry(cls, rover_id: str, data: dict[str, Any]) -> MessageEnvelope:
        return cls(
            msg_type=MessageType.TELEMETRY,
            sender=rover_id,
            payload=data,
        )

    @classmethod
    def crdt_sync(cls, sender: str, crdt_data: dict[str, Any]) -> MessageEnvelope:
        return cls(
            msg_type=MessageType.CRDT_SYNC,
            sender=sender,
            payload=crdt_data,
        )

    @classmethod
    def discovery(cls, node_id: str, capabilities: list[str] | None = None) -> MessageEnvelope:
        return cls(
            msg_type=MessageType.DISCOVERY,
            sender=node_id,
            payload={"node_id": node_id, "capabilities": capabilities or []},
        )
