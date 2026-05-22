from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from rover_swarm.crdt.base import Crdt, CrdtDelta
from rover_swarm.exceptions import CrdtMergeError


@dataclass
class MergeResult:
    success: bool
    conflict_count: int
    error: str | None = None


class MergeEngine:
    """Handles merging of CRDT states with conflict tracking."""

    def __init__(self) -> None:
        self._conflict_count: int = 0
        self._merge_history: list[dict[str, Any]] = field(default_factory=list)

    def merge(self, local: Crdt, remote: Crdt) -> MergeResult:
        if type(local) is not type(remote):
            return MergeResult(
                success=False,
                conflict_count=0,
                error=f"Type mismatch: {type(local)} vs {type(remote)}",
            )
        try:
            merged = local.merge(remote)
            conflict_detected = self._detect_conflict(local, remote)
            if conflict_detected:
                self._conflict_count += 1
                logger.warning("CRDT conflict detected during merge of {}", type(local).__name__)
            self._merge_history.append({
                "type": type(local).__name__,
                "conflict": conflict_detected,
            })
            return MergeResult(success=True, conflict_count=self._conflict_count)
        except CrdtMergeError as e:
            logger.error("Merge failed: {}", e)
            return MergeResult(success=False, conflict_count=self._conflict_count, error=str(e))

    def _detect_conflict(self, local: Crdt, remote: Crdt) -> bool:
        return hasattr(local, "_vector_clock") and hasattr(remote, "_vector_clock")

    def apply_delta(self, target: Crdt, delta: CrdtDelta) -> None:
        target.apply_delta(delta)

    def conflict_count(self) -> int:
        return self._conflict_count

    def reset_conflicts(self) -> None:
        self._conflict_count = 0

    def merge_history(self) -> list[dict[str, Any]]:
        return list(self._merge_history)
