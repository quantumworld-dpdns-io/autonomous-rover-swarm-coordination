from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from rover_swarm.types import Position


class FormationType(Enum):
    LINE = auto()
    VEE = auto()
    DIAMOND = auto()
    WEDGE = auto()
    COLUMN = auto()
    CIRCLE = auto()
    ECHELON_LEFT = auto()
    ECHELON_RIGHT = auto()


@dataclass
class FormationSlot:
    position: Position
    role: str | None = None


class FormationController:
    """Manages formation geometry and slot assignment for the swarm."""

    def __init__(self, spacing: float = 5.0) -> None:
        self._spacing = spacing
        self._current_formation = FormationType.LINE
        self._slots: dict[str, FormationSlot] = {}

    def set_formation(self, formation: FormationType) -> None:
        self._current_formation = formation
        self._slots.clear()

    def get_slots(self, count: int) -> list[FormationSlot]:
        return self._compute_formation(self._current_formation, count)

    def assign_slots(self, rover_ids: list[str], origin: Position) -> list[tuple[str, Position]]:
        slots = self.get_slots(len(rover_ids))
        result: list[tuple[str, Position]] = []
        for i, rover_id in enumerate(rover_ids):
            if i < len(slots):
                slot = slots[i]
                pos = Position(
                    x=origin.x + slot.position.x,
                    y=origin.y + slot.position.y,
                    z=origin.z + slot.position.z,
                )
                self._slots[rover_id] = FormationSlot(position=pos)
                result.append((rover_id, pos))
        return result

    def _compute_formation(self, formation: FormationType, count: int) -> list[FormationSlot]:
        slots: list[FormationSlot] = []
        s = self._spacing

        if formation == FormationType.LINE:
            for i in range(count):
                slots.append(FormationSlot(position=Position(x=i * s - (count - 1) * s / 2, y=0.0)))

        elif formation == FormationType.VEE:
            for i in range(count):
                row = i // 2
                side = -1 if i % 2 == 0 else 1
                slots.append(FormationSlot(position=Position(
                    x=row * s,
                    y=side * (row + 1) * s / 2,
                )))

        elif formation == FormationType.DIAMOND:
            center = count // 2
            for i in range(count):
                offset = i - center
                slots.append(FormationSlot(position=Position(
                    x=offset * s,
                    y=abs(offset) * s / 2 - center * s / 2,
                )))

        elif formation == FormationType.WEDGE:
            for i in range(count):
                angle = -math.pi / 2 + (i / max(count - 1, 1)) * math.pi
                radius = s * 2
                slots.append(FormationSlot(position=Position(
                    x=math.cos(angle) * radius,
                    y=math.sin(angle) * radius,
                )))

        elif formation == FormationType.COLUMN:
            for i in range(count):
                slots.append(FormationSlot(position=Position(x=0.0, y=-i * s)))

        elif formation == FormationType.CIRCLE:
            for i in range(count):
                angle = (2 * math.pi * i) / count
                radius = s * count / (2 * math.pi)
                slots.append(FormationSlot(position=Position(
                    x=math.cos(angle) * radius,
                    y=math.sin(angle) * radius,
                )))

        elif formation == FormationType.ECHELON_LEFT:
            for i in range(count):
                slots.append(FormationSlot(position=Position(
                    x=i * s,
                    y=i * s / 2,
                )))

        elif formation == FormationType.ECHELON_RIGHT:
            for i in range(count):
                slots.append(FormationSlot(position=Position(
                    x=i * s,
                    y=-i * s / 2,
                )))

        return slots

    def current_formation(self) -> str:
        return self._current_formation.name

    def get_slot(self, rover_id: str) -> Position | None:
        slot = self._slots.get(rover_id)
        return slot.position if slot else None
