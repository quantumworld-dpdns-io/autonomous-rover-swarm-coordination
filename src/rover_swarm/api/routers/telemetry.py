from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel

from rover_swarm.api.dependencies import get_rover_state
from rover_swarm.crdt.swarm_state import SwarmState

router = APIRouter(prefix="/api/v1", tags=["telemetry"])


class TelemetrySample(BaseModel):
    timestamp: float
    battery: float | None
    speed: float | None
    heading: float | None
    position: dict | None
    status: str | None


class TelemetryResponse(BaseModel):
    rover_id: str
    samples: list[TelemetrySample]


@router.get("/rovers/{rover_id}/telemetry", response_model=TelemetryResponse)
async def get_rover_telemetry(
    rover_id: str,
    state: Annotated[SwarmState, Depends(get_rover_state)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> TelemetryResponse:
    rover = state.get_rover(rover_id)
    if rover is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rover {rover_id} not found")

    rv = rover.value()
    sample = TelemetrySample(
        timestamp=rv.get("last_updated", 0.0),
        battery=rv.get("battery"),
        speed=rv.get("speed"),
        heading=rv.get("heading"),
        position=rv.get("position"),
        status=rv.get("status"),
    )

    samples: list[TelemetrySample] = []
    try:
        import duckdb

        from rover_swarm.config import settings as _settings

        conn = duckdb.connect(_settings.data.duckdb_path)
        rows = conn.execute(
            "SELECT timestamp, battery, speed, heading, position, status "
            "FROM telemetry WHERE rover_id = ? ORDER BY timestamp DESC LIMIT ?",
            [rover_id, limit],
        ).fetchall()
        for row in rows:
            samples.append(TelemetrySample(
                timestamp=row[0],
                battery=row[1],
                speed=row[2],
                heading=row[3],
                position=row[4],
                status=row[5],
            ))
        conn.close()
        logger.debug("Retrieved {} telemetry samples for rover {}", len(samples), rover_id)
    except ImportError:
        logger.debug("DuckDB not available, returning current state for rover {}", rover_id)
        samples = [sample]
    except Exception as e:
        logger.warning("Failed to query telemetry from DuckDB for rover {}: {}", rover_id, e)
        samples = [sample]

    if not samples:
        samples = [sample]

    return TelemetryResponse(rover_id=rover_id, samples=samples)
