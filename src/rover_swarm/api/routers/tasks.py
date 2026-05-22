from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from rover_swarm.api.dependencies import get_rover_state
from rover_swarm.crdt.swarm_state import SwarmState
from rover_swarm.swarm.task_allocation import TaskAllocationEngine
from rover_swarm.types import Task, TaskStatus, TaskType

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    task_id: str
    task_type: str
    priority: int = 0
    payload: dict[str, Any] | None = None
    deadline: float | None = None


class UpdateTaskRequest(BaseModel):
    status: str | None = None
    assigned_to: str | None = None
    priority: int | None = None


class TaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    assigned_to: str | None
    priority: int
    payload: dict[str, Any]
    created_at: float
    deadline: float | None


_engine: TaskAllocationEngine | None = None


def _get_engine() -> TaskAllocationEngine:
    global _engine
    if _engine is None:
        _engine = TaskAllocationEngine()
    return _engine


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> list[TaskResponse]:
    engine = _get_engine()
    summary = engine.task_summary()
    logger.debug("Listed tasks: {}", summary)
    result: list[TaskResponse] = []
    for task in list(engine._tasks.values()):  # type: ignore[attr-defined]
        result.append(TaskResponse(
            task_id=task.task_id,
            task_type=(
                task.task_type.value if hasattr(task.task_type, "value") else str(task.task_type)
            ),
            status=task.status.value if hasattr(task.status, "value") else str(task.status),
            assigned_to=task.assigned_to,
            priority=task.priority,
            payload=task.payload,
            created_at=task.created_at,
            deadline=task.deadline,
        ))
    return result


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: CreateTaskRequest,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> TaskResponse:
    engine = _get_engine()
    task = Task(
        task_id=body.task_id,
        task_type=TaskType(body.task_type),
        priority=body.priority,
        payload=body.payload or {},
        deadline=body.deadline,
    )
    engine.add_task(task)
    logger.info("Task created: {} ({})", body.task_id, body.task_type)
    return TaskResponse(
        task_id=task.task_id,
        task_type=task.task_type.value,
        status=task.status.value,
        assigned_to=task.assigned_to,
        priority=task.priority,
        payload=task.payload,
        created_at=task.created_at,
        deadline=task.deadline,
    )


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task_status(
    task_id: str,
    body: UpdateTaskRequest,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> TaskResponse:
    engine = _get_engine()
    task = engine._tasks.get(task_id)  # type: ignore[attr-defined]
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found"
        )

    if body.status is not None:
        new_status = TaskStatus(body.status)
        if new_status == TaskStatus.COMPLETED:
            engine.complete_task(task_id)
        elif new_status == TaskStatus.FAILED:
            engine.fail_task(task_id)
        elif new_status == TaskStatus.PENDING:
            task.status = TaskStatus.PENDING
            task.assigned_to = None
        elif new_status == TaskStatus.ASSIGNED:
            task.status = TaskStatus.ASSIGNED
            task.assigned_to = body.assigned_to
        elif new_status == TaskStatus.IN_PROGRESS:
            task.status = TaskStatus.IN_PROGRESS
        elif new_status == TaskStatus.CANCELLED:
            task.status = TaskStatus.CANCELLED
            engine.remove_task(task_id)

    if body.priority is not None:
        task.priority = body.priority

    if body.assigned_to is not None:
        task.assigned_to = body.assigned_to

    logger.info("Task updated: {} status={}", task_id, body.status)
    return TaskResponse(
        task_id=task.task_id,
        task_type=task.task_type.value,
        status=task.status.value,
        assigned_to=task.assigned_to,
        priority=task.priority,
        payload=task.payload,
        created_at=task.created_at,
        deadline=task.deadline,
    )
