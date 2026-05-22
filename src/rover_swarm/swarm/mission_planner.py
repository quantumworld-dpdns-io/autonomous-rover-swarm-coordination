from __future__ import annotations

import time
from typing import Any

from loguru import logger

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt.mission_state import MissionState
from rover_swarm.types import MissionPhase, Task, TaskType


class MissionPlanner:
    """Hierarchical Task Network (HTN) mission planner."""

    def __init__(self, node_id: str = NODE_ID) -> None:
        self._node_id = node_id
        self._missions: dict[str, MissionState] = {}

    def create_mission(self, mission_id: str, name: str, tasks: list[dict[str, Any]] | None = None) -> MissionState:
        mission = MissionState(mission_id=mission_id, name=name, node_id=self._node_id)
        if tasks:
            for t in tasks:
                mission.add_task(
                    task_id=t.get("id", f"task-{time.time()}"),
                    task_type=t.get("type", TaskType.EXPLORE.value),
                    payload=t.get("payload"),
                )
        self._missions[mission_id] = mission
        logger.info("Mission created: {} ({})", mission_id, name)
        return mission

    def get_mission(self, mission_id: str) -> MissionState | None:
        return self._missions.get(mission_id)

    def list_missions(self) -> list[dict[str, Any]]:
        return [m.value() for m in self._missions.values()]

    def start_mission(self, mission_id: str) -> None:
        mission = self._missions.get(mission_id)
        if mission:
            mission.set_phase(MissionPhase.DEPLOYING)
            logger.info("Mission {} started", mission_id)

    def complete_mission(self, mission_id: str) -> None:
        mission = self._missions.get(mission_id)
        if mission:
            mission.set_phase(MissionPhase.COMPLETED)
            mission.progress.set(1.0)
            logger.info("Mission {} completed", mission_id)

    def fail_mission(self, mission_id: str, reason: str = "") -> None:
        mission = self._missions.get(mission_id)
        if mission:
            mission.set_phase(MissionPhase.FAILED)
            logger.warning("Mission {} failed: {}", mission_id, reason)

    def decompose_mission(self, mission_id: str) -> list[Task]:
        mission = self._missions.get(mission_id)
        if not mission:
            return []
        tasks: list[Task] = []
        for task_id, task_data in mission.tasks.value().items():
            if isinstance(task_data, dict):
                tasks.append(Task(
                    task_id=task_id,
                    task_type=TaskType(task_data.get("type", "explore")),
                    payload=task_data.get("payload", {}),
                ))
        return tasks

    def mission_count(self) -> int:
        return len(self._missions)
