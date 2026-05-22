from __future__ import annotations

import asyncio

import pytest

from rover_swarm.crdt import (
    CrdtDeserializer,
    CrdtSerializer,
    RoverState,
    SwarmState,
    VectorClock,
)
from rover_swarm.types import Position, RoverStatus


@pytest.fixture
def rover_a() -> RoverState:
    state = RoverState(rover_id="rover-a", node_id="rover-a")
    state.update_status(RoverStatus.ONLINE)
    state.update_position(Position(x=10.0, y=20.0))
    state.update_battery(85.0)
    state.messages_sent.increment(5)
    return state


@pytest.fixture
def rover_b() -> RoverState:
    state = RoverState(rover_id="rover-b", node_id="rover-b")
    state.update_status(RoverStatus.BUSY)
    state.update_position(Position(x=30.0, y=40.0))
    state.update_battery(60.0)
    state.messages_sent.increment(3)
    return state


class TestSwarmSync:
    async def test_crdt_sync_between_rovers(
        self,
        rover_a: RoverState,
        rover_b: RoverState,
    ) -> None:
        state_a = rover_a
        state_b = rover_b

        assert state_a.value()["status"] == "online"
        assert state_b.value()["status"] == "busy"

        merged_a = state_a.merge(state_b)
        assert merged_a.rover_id == "rover-a"
        assert merged_a.status.value() == "online"
        assert merged_a.battery.value() == 85.0

        assert merged_a.messages_sent.value() == 8

    async def test_state_propagation_via_serialization(
        self,
        rover_a: RoverState,
    ) -> None:
        original = rover_a
        data = CrdtSerializer.serialize(original)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, RoverState)
        assert restored.rover_id == "rover-a"
        assert restored.status.value() == "online"
        assert restored.battery.value() == 85.0
        assert restored.messages_sent.value() == 5

    async def test_swarm_state_aggregation(
        self,
        rover_a: RoverState,
        rover_b: RoverState,
    ) -> None:
        swarm = SwarmState(swarm_id="integration-test", node_id="test-gs")
        swarm.add_rover(rover_a)
        swarm.add_rover(rover_b)

        assert len(swarm.rover_ids()) == 2
        assert swarm.get_rover("rover-a") is not None
        assert swarm.get_rover("rover-b") is not None

        val = swarm.value()
        assert val["rover_count"] == 2

        data = CrdtSerializer.serialize(swarm)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, SwarmState)
        assert restored.swarm_id == "integration-test"
        assert len(restored.rover_ids()) == 2

    async def test_swarm_state_merge_propagation(
        self,
        rover_a: RoverState,
        rover_b: RoverState,
    ) -> None:
        swarm_a = SwarmState(swarm_id="mission-1", node_id="gs-a")
        swarm_b = SwarmState(swarm_id="mission-1", node_id="gs-b")

        swarm_a.add_rover(rover_a)
        swarm_b.add_rover(rover_b)

        merged = swarm_a.merge(swarm_b)
        assert len(merged.rover_ids()) == 2
        assert merged.get_rover("rover-a") is not None
        assert merged.get_rover("rover-b") is not None

        rover_a_merged = merged.get_rover("rover-a")
        assert rover_a_merged is not None
        assert rover_a_merged.battery.value() == 85.0

    async def test_vector_clock_happens_before_across_rovers(self) -> None:
        vc_a = VectorClock(node_id="rover-a")
        vc_b = VectorClock(node_id="rover-b")

        vc_a.tick()
        vc_a.tick()
        vc_b.tick()

        merged = vc_a.merge(vc_b)
        assert merged.get("rover-a") == 2
        assert merged.get("rover-b") == 1

    async def test_concurrent_state_updates(self) -> None:
        state_a = RoverState(rover_id="rover-x", node_id="rover-a")
        state_b = RoverState(rover_id="rover-x", node_id="rover-b")

        state_a.update_battery(90.0)
        await asyncio.sleep(0.01)
        state_a.update_position(Position(x=1.0, y=1.0))

        state_b.update_battery(50.0)
        await asyncio.sleep(0.01)
        state_b.update_position(Position(x=5.0, y=5.0))

        merged = state_a.merge(state_b)
        assert merged.rover_id == "rover-x"
        assert merged.battery.value() == 90.0

    async def test_full_crdt_sync_round_trip(self) -> None:
        state_a = RoverState(rover_id="sync-test", node_id="node-a")
        state_b = RoverState(rover_id="sync-test", node_id="node-b")

        for i in range(3):
            state_a.messages_sent.increment(1)

        for i in range(2):
            state_b.messages_sent.increment(1)

        serialized_a = CrdtSerializer.serialize(state_a)
        serialized_b = CrdtSerializer.serialize(state_b)

        deserialized_a = CrdtDeserializer.deserialize(serialized_a)
        deserialized_b = CrdtDeserializer.deserialize(serialized_b)

        assert isinstance(deserialized_a, RoverState)
        assert isinstance(deserialized_b, RoverState)

        merged = deserialized_a.merge(deserialized_b)
        assert merged.messages_sent.value() == 5
