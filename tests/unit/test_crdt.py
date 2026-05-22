from __future__ import annotations

import time

import pytest

from rover_swarm.constants import NODE_ID
from rover_swarm.crdt import (
    GCounter,
    GSet,
    LwwMap,
    LwwReg,
    MissionState,
    MvReg,
    OrSet,
    PnCounter,
    Rga,
    RoverState,
    SwarmState,
    VectorClock,
)
from rover_swarm.crdt.serialization import CrdtDeserializer, CrdtSerializer
from rover_swarm.types import MissionPhase, Position, RoverStatus


class TestLwwReg:
    def test_set_and_value(self) -> None:
        reg = LwwReg(node_id="rover-1")
        reg.set("hello")
        assert reg.value() == "hello"

    def test_merge(self) -> None:
        a = LwwReg(node_id="rover-1")
        b = LwwReg(node_id="rover-2")
        a.set("from_a", timestamp=100.0)
        b.set("from_b", timestamp=200.0)
        merged = a.merge(b)
        assert merged.value() == "from_b"

    def test_binary_round_trip(self) -> None:
        reg = LwwReg(node_id="rover-1")
        reg.set(42)
        data = reg.to_binary()
        restored = LwwReg.from_binary(data)
        assert restored.value() == 42
        assert restored._node_id == "rover-1"


class TestGCounter:
    def test_increment(self) -> None:
        c = GCounter(node_id="rover-1")
        c.increment(5)
        assert c.value() == 5

    def test_merge(self) -> None:
        a = GCounter(node_id="rover-1")
        b = GCounter(node_id="rover-2")
        a.increment(3)
        b.increment(7)
        merged = a.merge(b)
        assert merged.value() == 10

    def test_increment_positive_only(self) -> None:
        c = GCounter(node_id="rover-1")
        with pytest.raises(ValueError):
            c.increment(-1)


class TestPnCounter:
    def test_increment_decrement(self) -> None:
        c = PnCounter(node_id="rover-1")
        c.increment(10)
        c.decrement(3)
        assert c.value() == 7

    def test_merge(self) -> None:
        a = PnCounter(node_id="rover-1")
        b = PnCounter(node_id="rover-2")
        a.increment(5)
        b.increment(3)
        b.decrement(2)
        merged = a.merge(b)
        assert merged.value() == 6


class TestGSet:
    def test_add_and_contains(self) -> None:
        s = GSet(node_id="rover-1")
        s.add("a")
        s.add("b")
        assert s.contains("a")
        assert s.contains("b")
        assert not s.contains("c")

    def test_merge(self) -> None:
        a = GSet(node_id="rover-1", elements={"a", "b"})
        b = GSet(node_id="rover-2", elements={"b", "c"})
        merged = a.merge(b)
        assert merged.value() == {"a", "b", "c"}


class TestOrSet:
    def test_add_remove_contains(self) -> None:
        s = OrSet(node_id="rover-1")
        s.add("a")
        assert s.contains("a")
        s.remove("a")
        assert not s.contains("a")

    def test_merge(self) -> None:
        a = OrSet(node_id="rover-1")
        b = OrSet(node_id="rover-2")
        a.add("x")
        b.add("y")
        merged = a.merge(b)
        assert merged.contains("x")
        assert merged.contains("y")


class TestLwwMap:
    def test_set_get_delete(self) -> None:
        m = LwwMap(node_id="rover-1")
        m.set("key1", "value1")
        assert m.get("key1") == "value1"
        m.delete("key1")
        assert m.get("key1") is None

    def test_merge(self) -> None:
        a = LwwMap(node_id="rover-1")
        b = LwwMap(node_id="rover-2")
        a.set("a", 1)
        b.set("b", 2)
        merged = a.merge(b)
        assert merged.get("a") == 1
        assert merged.get("b") == 2


class TestMvReg:
    def test_write_and_value(self) -> None:
        r = MvReg(node_id="rover-1")
        r.write("val1")
        values = r.value()
        assert "val1" in values

    def test_concurrent_writes(self) -> None:
        a = MvReg(node_id="rover-1")
        b = MvReg(node_id="rover-2")
        a.write("from_a")
        b.write("from_b")
        merged = a.merge(b)
        vals = merged.value()
        assert "from_a" in vals
        assert "from_b" in vals


class TestRga:
    def test_append_and_value(self) -> None:
        r = Rga(node_id="rover-1")
        r.append("a")
        r.append("b")
        r.append("c")
        assert r.value() == ["a", "b", "c"]

    def test_delete(self) -> None:
        r = Rga(node_id="rover-1")
        tag = r.append("x")
        r.append("y")
        r.delete(tag)
        assert r.value() == ["y"]


class TestVectorClock:
    def test_tick(self) -> None:
        vc = VectorClock(node_id="rover-1")
        assert vc.tick() == 1
        assert vc.tick() == 2

    def test_happens_before(self) -> None:
        a = VectorClock(node_id="rover-1")
        b = VectorClock(node_id="rover-1")
        a.tick()
        assert a.happens_before(b) is False
        assert b.happens_before(a) is True

    def test_concurrent(self) -> None:
        a = VectorClock(node_id="rover-1")
        b = VectorClock(node_id="rover-2")
        a.tick()
        b.tick()
        assert a.concurrent(b) is True


class TestSerialization:
    def test_serialize_deserialize_lwwreg(self) -> None:
        reg = LwwReg(node_id="rover-1")
        reg.set(99)
        data = CrdtSerializer.serialize(reg)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, LwwReg)
        assert restored.value() == 99

    def test_serialize_deserialize_gcounter(self) -> None:
        c = GCounter(node_id="rover-1")
        c.increment(42)
        data = CrdtSerializer.serialize(c)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, GCounter)
        assert restored.value() == 42

    def test_serialize_deserialize_gset(self) -> None:
        s = GSet(node_id="rover-1", elements={"a", "b", "c"})
        data = CrdtSerializer.serialize(s)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, GSet)
        assert restored.value() == {"a", "b", "c"}

    def test_serialize_deserialize_orset(self) -> None:
        s = OrSet(node_id="rover-1")
        s.add("x")
        s.add("y")
        data = CrdtSerializer.serialize(s)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, OrSet)
        assert restored.contains("x")
        assert restored.contains("y")

    def test_serialize_deserialize_pncounter(self) -> None:
        c = PnCounter(node_id="rover-1")
        c.increment(10)
        c.decrement(3)
        data = CrdtSerializer.serialize(c)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, PnCounter)
        assert restored.value() == 7

    def test_serialize_deserialize_lwwmap(self) -> None:
        m = LwwMap(node_id="rover-1")
        m.set("k1", "v1")
        m.set("k2", 42)
        data = CrdtSerializer.serialize(m)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, LwwMap)
        assert restored.get("k1") == "v1"
        assert restored.get("k2") == 42

    def test_serialize_deserialize_mvreg(self) -> None:
        r = MvReg(node_id="rover-1")
        r.write("hello")
        data = CrdtSerializer.serialize(r)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, MvReg)
        assert "hello" in restored.value()

    def test_serialize_deserialize_rga(self) -> None:
        r = Rga(node_id="rover-1")
        r.append("a")
        r.append("b")
        data = CrdtSerializer.serialize(r)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, Rga)
        assert restored.value() == ["a", "b"]


class TestRoverState:
    def test_composite_value(self) -> None:
        state = RoverState(rover_id="rover-1", node_id="rover-1")
        state.update_status(RoverStatus.ONLINE)
        state.update_battery(85.5)
        state.update_position(Position(x=10.0, y=20.0))
        val = state.value()
        assert val["rover_id"] == "rover-1"
        assert val["status"] == "online"
        assert val["battery"] == 85.5

    def test_binary_round_trip(self) -> None:
        state = RoverState(rover_id="rover-1", node_id="rover-1")
        state.update_battery(75.0)
        data = state.to_binary()
        restored = RoverState.from_binary(data)
        assert restored.rover_id == "rover-1"
        assert restored.battery.value() == 75.0

    def test_merge(self) -> None:
        a = RoverState(rover_id="rover-1", node_id="rover-1")
        b = RoverState(rover_id="rover-1", node_id="rover-2")
        a.update_status(RoverStatus.ONLINE)
        a.update_battery(90.0)
        b.update_battery(50.0)
        b.update_position(Position(x=5.0, y=5.0))
        merged = a.merge(b)
        assert merged.rover_id == "rover-1"
        assert merged.status.value() == "online"
        assert merged.battery.value() == 90.0

    def test_serialization_round_trip(self) -> None:
        state = RoverState(rover_id="rover-1", node_id="rover-1")
        state.update_status(RoverStatus.ONLINE)
        state.update_battery(100.0)
        data = CrdtSerializer.serialize(state)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, RoverState)
        assert restored.rover_id == "rover-1"
        assert restored.battery.value() == 100.0
        assert restored.status.value() == "online"


class TestSwarmState:
    def test_add_and_get_rover(self) -> None:
        swarm = SwarmState(swarm_id="mission-1", node_id="gs-1")
        rover = RoverState(rover_id="rover-1", node_id="rover-1")
        swarm.add_rover(rover)
        assert swarm.get_rover("rover-1") is rover
        assert "rover-1" in swarm.rover_ids()

    def test_merge(self) -> None:
        a = SwarmState(swarm_id="mission-1", node_id="gs-1")
        b = SwarmState(swarm_id="mission-1", node_id="gs-2")
        r1 = RoverState(rover_id="rover-1", node_id="rover-1")
        r2 = RoverState(rover_id="rover-2", node_id="rover-2")
        a.add_rover(r1)
        b.add_rover(r2)
        merged = a.merge(b)
        assert merged.get_rover("rover-1") is not None
        assert merged.get_rover("rover-2") is not None
        assert len(merged.rover_ids()) == 2

    def test_serialization_round_trip(self) -> None:
        swarm = SwarmState(swarm_id="mission-1", node_id="gs-1")
        rover = RoverState(rover_id="rover-1", node_id="rover-1")
        rover.update_status(RoverStatus.ONLINE)
        swarm.add_rover(rover)
        data = CrdtSerializer.serialize(swarm)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, SwarmState)
        assert restored.swarm_id == "mission-1"
        assert restored.get_rover("rover-1") is not None


class TestMissionState:
    def test_set_phase(self) -> None:
        mission = MissionState(mission_id="mission-1", node_id="rover-1")
        mission.set_phase(MissionPhase.DEPLOYING)
        assert mission.phase.value() == "deploying"

    def test_add_task(self) -> None:
        mission = MissionState(mission_id="mission-1", node_id="rover-1")
        mission.add_task("task-1", "explore", {"area": "zone_a"})
        tasks = mission.tasks.value()
        assert "task-1" in tasks

    def test_progress(self) -> None:
        mission = MissionState(mission_id="mission-1", node_id="rover-1")
        mission.advance_progress(0.5)
        assert mission.progress.value() == 0.5

    def test_objectives(self) -> None:
        mission = MissionState(mission_id="mission-1", node_id="rover-1")
        mission.complete_objective()
        assert mission.completed_objectives.value() == 1

    def test_serialization_round_trip(self) -> None:
        mission = MissionState(mission_id="mission-1", node_id="rover-1")
        mission.set_phase(MissionPhase.EXPLORING)
        mission.advance_progress(0.3)
        data = CrdtSerializer.serialize(mission)
        restored = CrdtDeserializer.deserialize(data)
        assert isinstance(restored, MissionState)
        assert restored.mission_id == "mission-1"
        assert restored.phase.value() == "exploring"
        assert restored.progress.value() == 0.3
