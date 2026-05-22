from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from rover_swarm.api.dependencies import get_rover_state
from rover_swarm.crdt.swarm_state import SwarmState
from rover_swarm.types import RoverStatus

router = APIRouter(prefix="/api/v1/swarm", tags=["swarm"])


class RoverSummary(BaseModel):
    rover_id: str
    status: str
    battery: float
    role: str
    position: dict | None
    speed: float
    heading: float


class RoverDetail(BaseModel):
    rover_id: str
    position: dict | None
    status: str
    battery: float
    role: str
    speed: float
    heading: float
    tasks: dict
    messages_sent: int
    messages_received: int
    distance_traveled: float


class SwarmStatus(BaseModel):
    total_rovers: int
    online: int
    offline: int
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    leader: str | None


class SwarmTopology(BaseModel):
    swarm_id: str
    rover_count: int
    topology: dict
    rovers: list[str]


@router.get("/rovers", response_model=list[RoverSummary])
async def list_rovers(
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> list[RoverSummary]:
    rovers = state.value().get("rovers", {})
    result = [
        RoverSummary(
            rover_id=rid,
            status=r.get("status", RoverStatus.OFFLINE.value),
            battery=r.get("battery", 0.0),
            role=r.get("role", "general"),
            position=r.get("position"),
            speed=r.get("speed", 0.0),
            heading=r.get("heading", 0.0),
        )
        for rid, r in rovers.items()
    ]
    logger.debug("Listed {} rovers", len(result))
    return result


@router.get("/rovers/{rover_id}", response_model=RoverDetail)
async def get_rover(
    rover_id: str,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> RoverDetail:
    rover = state.get_rover(rover_id)
    if rover is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rover {rover_id} not found")
    r = rover.value()
    return RoverDetail(
        rover_id=r["rover_id"],
        position=r.get("position"),
        status=r.get("status", RoverStatus.OFFLINE.value),
        battery=r.get("battery", 0.0),
        role=r.get("role", "general"),
        speed=r.get("speed", 0.0),
        heading=r.get("heading", 0.0),
        tasks=r.get("tasks", {}),
        messages_sent=r.get("messages_sent", 0),
        messages_received=r.get("messages_received", 0),
        distance_traveled=r.get("distance_traveled", 0.0),
    )


@router.get("/status", response_model=SwarmStatus)
async def swarm_status(
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> SwarmStatus:
    sv = state.value()
    rovers = sv.get("rovers", {})
    online = sum(
        1 for r in rovers.values()
        if r.get("status") == RoverStatus.ONLINE.value
    )
    return SwarmStatus(
        total_rovers=len(rovers),
        online=online,
        offline=len(rovers) - online,
        total_tasks=sv.get("total_tasks", 0),
        completed_tasks=sv.get("completed_tasks", 0),
        failed_tasks=sv.get("failed_tasks", 0),
        leader=sv.get("leader"),
    )


@router.get("/topology", response_model=SwarmTopology)
async def swarm_topology(
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> SwarmTopology:
    sv = state.value()
    return SwarmTopology(
        swarm_id=sv.get("swarm_id", ""),
        rover_count=sv.get("rover_count", 0),
        topology=sv.get("topology", {}),
        rovers=list(sv.get("rovers", {}).keys()),
    )
