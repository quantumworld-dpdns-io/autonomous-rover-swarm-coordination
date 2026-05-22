from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from rover_swarm.api.dependencies import get_rover_state
from rover_swarm.crdt.swarm_state import SwarmState
from rover_swarm.swarm.mission_planner import MissionPlanner

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])


class CreateMissionRequest(BaseModel):
    mission_id: str
    name: str
    tasks: list[dict] | None = None


class UpdateMissionRequest(BaseModel):
    name: str | None = None
    phase: str | None = None
    tasks: list[dict] | None = None


class MissionResponse(BaseModel):
    mission_id: str
    name: str
    phase: str
    tasks: dict
    assigned_rovers: dict
    progress: float
    completed_objectives: int
    total_objectives: int
    errors: int


_planner: MissionPlanner | None = None


def _get_planner() -> MissionPlanner:
    global _planner
    if _planner is None:
        _planner = MissionPlanner()
    return _planner


@router.post("", response_model=MissionResponse, status_code=status.HTTP_201_CREATED)
async def create_mission(
    body: CreateMissionRequest,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> MissionResponse:
    planner = _get_planner()
    existing = planner.get_mission(body.mission_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mission {body.mission_id} already exists",
        )
    mission = planner.create_mission(
        mission_id=body.mission_id,
        name=body.name,
        tasks=body.tasks,
    )
    sv = mission.value()
    logger.info("Mission created: {} ({})", body.mission_id, body.name)
    return MissionResponse(
        mission_id=sv["mission_id"],
        name=sv["name"],
        phase=sv["phase"],
        tasks=sv["tasks"],
        assigned_rovers=sv["assigned_rovers"],
        progress=sv["progress"],
        completed_objectives=sv["completed_objectives"],
        total_objectives=sv["total_objectives"],
        errors=sv["errors"],
    )


@router.get("", response_model=list[MissionResponse])
async def list_missions(
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> list[MissionResponse]:
    planner = _get_planner()
    missions = planner.list_missions()
    result = [
        MissionResponse(
            mission_id=m["mission_id"],
            name=m["name"],
            phase=m["phase"],
            tasks=m["tasks"],
            assigned_rovers=m["assigned_rovers"],
            progress=m["progress"],
            completed_objectives=m["completed_objectives"],
            total_objectives=m["total_objectives"],
            errors=m["errors"],
        )
        for m in missions
    ]
    logger.debug("Listed {} missions", len(result))
    return result


@router.get("/{mission_id}", response_model=MissionResponse)
async def get_mission(
    mission_id: str,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> MissionResponse:
    planner = _get_planner()
    mission = planner.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission {mission_id} not found")
    sv = mission.value()
    return MissionResponse(
        mission_id=sv["mission_id"],
        name=sv["name"],
        phase=sv["phase"],
        tasks=sv["tasks"],
        assigned_rovers=sv["assigned_rovers"],
        progress=sv["progress"],
        completed_objectives=sv["completed_objectives"],
        total_objectives=sv["total_objectives"],
        errors=sv["errors"],
    )


@router.put("/{mission_id}", response_model=MissionResponse)
async def update_mission(
    mission_id: str,
    body: UpdateMissionRequest,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> MissionResponse:
    planner = _get_planner()
    mission = planner.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission {mission_id} not found")
    if body.name is not None:
        mission.name.set(body.name)
    if body.phase is not None:
        from rover_swarm.types import MissionPhase
        mission.set_phase(MissionPhase(body.phase))
    if body.tasks is not None:
        for t in body.tasks:
            tid = t.get("id", f"task-{time.time()}")
            mission.add_task(
                task_id=tid,
                task_type=t.get("type", "explore"),
                payload=t.get("payload"),
            )
    logger.info("Mission updated: {}", mission_id)
    sv = mission.value()
    return MissionResponse(
        mission_id=sv["mission_id"],
        name=sv["name"],
        phase=sv["phase"],
        tasks=sv["tasks"],
        assigned_rovers=sv["assigned_rovers"],
        progress=sv["progress"],
        completed_objectives=sv["completed_objectives"],
        total_objectives=sv["total_objectives"],
        errors=sv["errors"],
    )


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_mission(
    mission_id: str,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> None:
    planner = _get_planner()
    mission = planner.get_mission(mission_id)
    if mission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mission {mission_id} not found")
    planner.fail_mission(mission_id, reason="Cancelled by user")
    logger.info("Mission cancelled: {}", mission_id)
