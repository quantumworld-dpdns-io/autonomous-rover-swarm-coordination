from __future__ import annotations

import time
from typing import Any

from loguru import logger

from rover_swarm.constants import NODE_ID
from rover_swarm.types import RoverRole


class RoleAssignmentEngine:
    """Dynamic role assignment for rovers based on capability and need."""

    ROLE_PRIORITIES: dict[str, int] = {
        RoverRole.RELAY.value: 1,
        RoverRole.CHARGER.value: 2,
        RoverRole.SCOUT.value: 3,
        RoverRole.TRANSPORTER.value: 4,
        RoverRole.GENERAL.value: 5,
    }

    def __init__(self, node_id: str = NODE_ID) -> None:
        self._node_id = node_id
        self._current_roles: dict[str, str] = {}

    def assign_role(self, rover_id: str, capabilities: list[str], swarm_needs: dict[str, int]) -> str:
        role_scores: dict[str, float] = {}
        for role, needed in swarm_needs.items():
            if needed <= 0:
                continue
            capability_match = sum(1 for c in capabilities if c in role)
            score = capability_match * 10 + self.ROLE_PRIORITIES.get(role, 5) - needed
            role_scores[role] = score
        if not role_scores:
            assigned = RoverRole.GENERAL.value
        else:
            assigned = max(role_scores, key=role_scores.get)
        self._current_roles[rover_id] = assigned
        logger.info("Assigned role {} to {}", assigned, rover_id)
        return assigned

    def get_role(self, rover_id: str) -> str | None:
        return self._current_roles.get(rover_id)

    def release_role(self, rover_id: str) -> None:
        self._current_roles.pop(rover_id, None)

    def redistribute(self, available_rovers: list[str], swarm_needs: dict[str, int]) -> dict[str, str]:
        assignments: dict[str, str] = {}
        unmet_needs = dict(swarm_needs)
        for rover_id in available_rovers:
            role = self.assign_role(rover_id, [], unmet_needs)
            assignments[rover_id] = role
            if role in unmet_needs:
                unmet_needs[role] = max(0, unmet_needs[role] - 1)
        return assignments

    def swarm_role_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for role in self._current_roles.values():
            counts[role] = counts.get(role, 0) + 1
        return counts
