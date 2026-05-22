from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CrdtDelta(Generic[T]):
    value: T
    vector_clock: dict[str, int]
    source_id: str
    timestamp: float


class Crdt(ABC, Generic[T]):
    """Abstract base for all CRDT types."""

    @abstractmethod
    def value(self) -> T:
        """Return the current merged value."""

    @abstractmethod
    def merge(self, other: Crdt[T]) -> Crdt[T]:
        """Merge another CRDT into this one, returning a new instance."""

    @abstractmethod
    def delta(self) -> CrdtDelta[T]:
        """Return the delta (changes since last sync)."""

    @abstractmethod
    def apply_delta(self, delta: CrdtDelta[T]) -> None:
        """Apply a delta from a remote peer."""

    @abstractmethod
    def to_binary(self) -> bytes:
        """Serialize to binary format."""

    @classmethod
    @abstractmethod
    def from_binary(cls, data: bytes) -> Crdt[T]:
        """Deserialize from binary format."""

    @abstractmethod
    def size_bytes(self) -> int:
        """Approximate memory size in bytes."""

    @abstractmethod
    def reset_delta(self) -> None:
        """Reset the delta tracker after sync."""
