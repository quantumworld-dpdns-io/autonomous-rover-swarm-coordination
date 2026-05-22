from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from rover_swarm.constants import NODE_ID


@dataclass
class VectorClock:
    node_id: str = NODE_ID
    clocks: dict[str, int] = field(default_factory=dict)

    def tick(self, node_id: str | None = None) -> int:
        nid = node_id or self.node_id
        self.clocks[nid] = self.clocks.get(nid, 0) + 1
        return self.clocks[nid]

    def get(self, node_id: str) -> int:
        return self.clocks.get(node_id, 0)

    def merge(self, other: VectorClock) -> VectorClock:
        merged = VectorClock(node_id=self.node_id)
        all_nodes = set(self.clocks) | set(other.clocks)
        for node in all_nodes:
            merged.clocks[node] = max(self.clocks.get(node, 0), other.clocks.get(node, 0))
        return merged

    def happens_before(self, other: VectorClock) -> bool:
        """Check if this clock happens-before other clock."""
        at_least_one_less = False
        for node in set(self.clocks) | set(other.clocks):
            self_val = self.clocks.get(node, 0)
            other_val = other.clocks.get(node, 0)
            if self_val > other_val:
                return False
            if self_val < other_val:
                at_least_one_less = True
        return at_least_one_less

    def concurrent(self, other: VectorClock) -> bool:
        """Check if two clocks are concurrent (neither happens-before the other)."""
        return not self.happens_before(other) and not other.happens_before(self)

    def __iter__(self) -> Iterator[tuple[str, int]]:
        return iter(sorted(self.clocks.items()))

    def copy(self) -> VectorClock:
        return VectorClock(node_id=self.node_id, clocks=dict(self.clocks))

    def to_dict(self) -> dict[str, int]:
        return dict(self.clocks)

    @classmethod
    def from_dict(cls, data: dict[str, int], node_id: str = NODE_ID) -> VectorClock:
        return VectorClock(node_id=node_id, clocks=dict(data))

    def __len__(self) -> int:
        return len(self.clocks)

    def __repr__(self) -> str:
        items = ",".join(f"{k}:{v}" for k, v in self)
        return f"VC({items})"
