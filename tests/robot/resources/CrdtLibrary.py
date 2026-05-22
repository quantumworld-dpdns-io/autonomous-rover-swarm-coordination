from typing import Any

from rover_swarm.crdt import (
    GCounter,
    LwwReg,
    OrSet,
    VectorClock,
    CrdtSerializer,
    CrdtDeserializer,
)


class CrdtLibrary:
    def create_lww_reg(self, value: Any = None, node_id: str = "rover-test"):
        return LwwReg(value=value, node_id=node_id)

    def lww_reg_set(self, reg: LwwReg, value: Any):
        import time

        reg.set(value, timestamp=time.time())
        return reg

    def lww_reg_get(self, reg: LwwReg):
        return reg.value()

    def lww_reg_merge(self, reg_a: LwwReg, reg_b: LwwReg):
        return reg_a.merge(reg_b)

    def create_gcounter(self, node_id: str = "rover-test"):
        return GCounter(node_id=node_id)

    def gcounter_increment(self, counter: GCounter, amount: int = 1):
        counter.increment(amount)
        return counter

    def gcounter_value(self, counter: GCounter):
        return counter.value()

    def gcounter_merge(self, counter_a: GCounter, counter_b: GCounter):
        return counter_a.merge(counter_b)

    def create_orset(self, node_id: str = "rover-test"):
        return OrSet(node_id=node_id)

    def orset_add(self, orset: OrSet, element: str):
        orset.add(element)
        return orset

    def orset_remove(self, orset: OrSet, element: str):
        orset.remove(element)
        return orset

    def orset_contains(self, orset: OrSet, element: str):
        return orset.contains(element)

    def orset_value(self, orset: OrSet):
        return orset.value()

    def orset_merge(self, orset_a: OrSet, orset_b: OrSet):
        return orset_a.merge(orset_b)

    def create_vector_clock(self, node_id: str = "rover-test"):
        return VectorClock(node_id=node_id)

    def vector_clock_tick(self, clock: VectorClock):
        clock.tick()
        return clock

    def vector_clock_happens_before(self, clock_a: VectorClock, clock_b: VectorClock):
        return clock_a.happens_before(clock_b)

    def crdt_serialize(self, crdt):
        return CrdtSerializer.serialize(crdt)

    def crdt_deserialize(self, data: bytes):
        return CrdtDeserializer.deserialize(data)

    def values_should_be_equal(self, actual: Any, expected: Any):
        assert actual == expected, f"Expected {expected}, got {actual}"

    def values_should_not_be_equal(self, actual: Any, expected: Any):
        assert actual != expected, f"Expected {actual} to differ from {expected}"
