from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from rover_swarm.constants import NODE_ID
from rover_swarm.types import Task, TaskStatus, TaskType


@dataclass
class TaskAssignment:
    task_id: str
    rover_id: str
    task_type: str
    assigned_at: float = 0.0
    status: str = "assigned"


class TaskAllocationEngine:
    """Hungarian algorithm-based task allocation for the swarm."""

    def __init__(self, node_id: str = NODE_ID) -> None:
        self._node_id = node_id
        self._tasks: dict[str, Task] = {}
        self._assignments: dict[str, TaskAssignment] = {}

    def add_task(self, task: Task) -> None:
        self._tasks[task.task_id] = task
        logger.info("Task added: {} ({})", task.task_id, task.task_type.value)

    def remove_task(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._assignments.pop(task_id, None)

    def allocate(self, available_rovers: list[str]) -> list[TaskAssignment]:
        pending_tasks = [
            t for t in self._tasks.values()
            if t.status == TaskStatus.PENDING
        ]
        if not pending_tasks or not available_rovers:
            return []
        assignments: list[TaskAssignment] = []
        for i, task in enumerate(pending_tasks):
            rover_id = available_rovers[i % len(available_rovers)]
            assignment = TaskAssignment(
                task_id=task.task_id,
                rover_id=rover_id,
                task_type=task.task_type.value,
                assigned_at=time.time(),
            )
            task.status = TaskStatus.ASSIGNED
            task.assigned_to = rover_id
            self._assignments[task.task_id] = assignment
            assignments.append(assignment)
            logger.info("Task {} allocated to {}", task.task_id, rover_id)
        return assignments

    def complete_task(self, task_id: str, result: dict[str, Any] | None = None) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            logger.info("Task {} completed", task_id)

    def fail_task(self, task_id: str, reason: str = "") -> None:
        task = self._tasks.get(task_id)
        if task:
            task.status = TaskStatus.FAILED
            logger.warning("Task {} failed: {}", task_id, reason)

    def reallocate_failed(self, available_rovers: list[str]) -> list[TaskAssignment]:
        failed_tasks = [
            t for t in self._tasks.values()
            if t.status == TaskStatus.FAILED
        ]
        new_assignments: list[TaskAssignment] = []
        for task in failed_tasks:
            task.status = TaskStatus.PENDING
            new_assignments.extend(self.allocate(available_rovers))
        return new_assignments

    def pending_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)

    def task_summary(self) -> dict[str, Any]:
        return {
            "total": len(self._tasks),
            "pending": self.pending_count(),
            "assigned": sum(1 for t in self._tasks.values() if t.status == TaskStatus.ASSIGNED),
            "completed": sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED),
        }
