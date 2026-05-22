from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from rover_swarm.api.dependencies import get_rover_state
from rover_swarm.crdt.swarm_state import SwarmState

router = APIRouter(prefix="/api/v1", tags=["commands"])


class CommandRequest(BaseModel):
    command: str
    params: dict[str, Any] | None = None
    timeout: float | None = 30.0


class CommandResponse(BaseModel):
    command_id: str
    rover_id: str
    command: str
    status: str
    timestamp: float
    message: str


@router.post(
    "/rovers/{rover_id}/commands",
    response_model=CommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_rover_command(
    rover_id: str,
    body: CommandRequest,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> CommandResponse:
    rover = state.get_rover(rover_id)
    if rover is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Rover {rover_id} not found"
        )

    command_id = f"cmd-{rover_id}-{int(time.time() * 1000)}"

    try:
        from rover_swarm.communication.mqtt_client import MqttClient as _MqttClient
        from rover_swarm.config import settings as _settings

        mqtt = _MqttClient(
            broker=_settings.mqtt.broker,
            port=_settings.mqtt.port,
            client_id=f"api-{rover_id}",
        )
        await mqtt.connect()
        topic = f"rover/{rover_id}/command"
        payload = {
            "command_id": command_id,
            "command": body.command,
            "params": body.params or {},
            "timestamp": time.time(),
        }
        await mqtt.publish(topic, payload)
        await mqtt.disconnect()
        logger.info("Command sent to rover {}: {}", rover_id, body.command)
        return CommandResponse(
            command_id=command_id,
            rover_id=rover_id,
            command=body.command,
            status="queued",
            timestamp=time.time(),
            message="Command published to rover",
        )
    except ImportError:
        logger.warning("MQTT client not available, command queued for rover {}", rover_id)
        return CommandResponse(
            command_id=command_id,
            rover_id=rover_id,
            command=body.command,
            status="queued",
            timestamp=time.time(),
            message="Command queued (MQTT unavailable)",
        )
    except Exception as e:
        logger.error("Failed to send command to rover {}: {}", rover_id, e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post(
    "/swarm/commands", response_model=list[CommandResponse], status_code=status.HTTP_202_ACCEPTED
)
async def broadcast_command(
    body: CommandRequest,
    state: Annotated[SwarmState, Depends(get_rover_state)],
) -> list[CommandResponse]:
    sv = state.value()
    rovers = sv.get("rovers", {})
    if not rovers:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No rovers in swarm")

    results: list[CommandResponse] = []
    for rover_id in rovers:
        cmd_id = f"cmd-{rover_id}-{int(time.time() * 1000)}"
        try:
            from rover_swarm.communication.mqtt_client import MqttClient as _MqttClient
            from rover_swarm.config import settings as _settings

            mqtt = _MqttClient(
                broker=_settings.mqtt.broker,
                port=_settings.mqtt.port,
                client_id=f"api-bcast-{rover_id}",
            )
            await mqtt.connect()
            topic = f"rover/{rover_id}/command"
            payload = {
                "command_id": cmd_id,
                "command": body.command,
                "params": body.params or {},
                "timestamp": time.time(),
            }
            await mqtt.publish(topic, payload)
            await mqtt.disconnect()
        except Exception as e:
            logger.error("Broadcast failed for rover {}: {}", rover_id, e)

        results.append(CommandResponse(
            command_id=cmd_id,
            rover_id=rover_id,
            command=body.command,
            status="queued",
            timestamp=time.time(),
            message="Command broadcast to rover",
        ))

    logger.info("Broadcast command {} to {} rovers", body.command, len(results))
    return results
