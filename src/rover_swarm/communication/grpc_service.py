from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from loguru import logger

from rover_swarm.config import settings
from rover_swarm.constants import MAX_MESSAGE_SIZE
from rover_swarm.exceptions import GrpcError

_grpc_available = False
try:
    import grpc
    import grpc.aio

    _grpc_available = True
except ImportError:
    logger.warning("gRPC not available, install with: pip install rover-swarm[grpc]")


class GrpcServer:
    """Async gRPC server for rover-to-rover RPC."""

    def __init__(self, port: int = settings.grpc.port) -> None:
        self._port = port
        self._server: Any = None

    async def start(self) -> None:
        if not _grpc_available:
            logger.warning("gRPC not available, skipping server start")
            return
        self._server = grpc.aio.server(
            options=[
                ("grpc.max_send_message_length", MAX_MESSAGE_SIZE),
                ("grpc.max_receive_message_length", MAX_MESSAGE_SIZE),
            ]
        )
        listen_addr = f"[::]:{self._port}"
        self._server.add_insecure_port(listen_addr)
        await self._server.start()
        logger.info("gRPC server started on {}", listen_addr)

    async def stop(self) -> None:
        if self._server:
            await self._server.stop(grace=5)
            logger.info("gRPC server stopped")

    async def wait_for_termination(self) -> None:
        if self._server:
            await self._server.wait_for_termination()


class GrpcClient:
    """Async gRPC client for rover-to-rover communication."""

    def __init__(self) -> None:
        self._channels: dict[str, Any] = {}

    async def get_channel(self, address: str) -> Any:
        if not _grpc_available:
            raise GrpcError("gRPC not available")
        if address not in self._channels:
            self._channels[address] = grpc.aio.insecure_channel(
                address,
                options=[
                    ("grpc.max_send_message_length", MAX_MESSAGE_SIZE),
                    ("grpc.max_receive_message_length", MAX_MESSAGE_SIZE),
                ],
            )
        return self._channels[address]

    async def close(self) -> None:
        for addr, channel in self._channels.items():
            await channel.close()
        self._channels.clear()


_grpc_server: GrpcServer | None = None
_grpc_client: GrpcClient | None = None


async def get_grpc_server() -> GrpcServer:
    global _grpc_server
    if _grpc_server is None:
        _grpc_server = GrpcServer()
    return _grpc_server


async def get_grpc_client() -> GrpcClient:
    global _grpc_client
    if _grpc_client is None:
        _grpc_client = GrpcClient()
    return _grpc_client


def create_grpc_proto() -> str:
    return """
syntax = "proto3";

package rover_swarm;

service RoverService {
    rpc SyncState (StateSyncRequest) returns (StateSyncResponse);
    rpc GetState (StateQuery) returns (StateSnapshot);
    rpc ForwardCommand (CommandRequest) returns (CommandResponse);
    rpc StreamTelemetry (TelemetryQuery) returns (stream TelemetryPacket);
    rpc Heartbeat (HeartbeatRequest) returns (HeartbeatResponse);
}

message StateSyncRequest {
    string rover_id = 1;
    bytes crdt_delta = 2;
    map<string, int32> vector_clock = 3;
}

message StateSyncResponse {
    bool accepted = 1;
    bytes merged_state = 2;
    string error = 3;
}

message StateQuery {
    string rover_id = 1;
    repeated string fields = 2;
}

message StateSnapshot {
    string rover_id = 1;
    bytes crdt_state = 2;
    int64 timestamp = 3;
}

message CommandRequest {
    string target_rover = 1;
    string command = 2;
    map<string, string> params = 3;
    int32 ttl = 4;
}

message CommandResponse {
    bool accepted = 1;
    string result = 2;
    string error = 3;
}

message TelemetryQuery {
    string rover_id = 1;
    repeated string metrics = 2;
    int32 interval_ms = 3;
}

message TelemetryPacket {
    string rover_id = 1;
    map<string, double> values = 2;
    int64 timestamp = 3;
}

message HeartbeatRequest {
    string rover_id = 1;
    int64 timestamp = 2;
}

message HeartbeatResponse {
    bool alive = 1;
    int64 server_timestamp = 2;
}
"""
