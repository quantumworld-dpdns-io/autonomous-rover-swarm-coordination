from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from loguru import logger

from rover_swarm.constants import (
    LEADER_ELECTION_TIMEOUT_MAX,
    LEADER_ELECTION_TIMEOUT_MIN,
    LEADER_HEARTBEAT_INTERVAL,
    NODE_ID,
)


class RaftRole(Enum):
    FOLLOWER = auto()
    CANDIDATE = auto()
    LEADER = auto()


@dataclass
class RaftState:
    current_term: int = 0
    voted_for: str | None = None
    leader_id: str | None = None
    role: RaftRole = RaftRole.FOLLOWER
    commit_index: int = 0
    last_applied: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_term": self.current_term,
            "voted_for": self.voted_for,
            "leader_id": self.leader_id,
            "role": self.role.name,
            "commit_index": self.commit_index,
            "last_applied": self.last_applied,
        }


class ConsensusModule:
    """Raft-inspired consensus for leader election and log replication."""

    def __init__(self, node_id: str = NODE_ID) -> None:
        self._node_id = node_id
        self._state = RaftState()
        self._election_timeout = self._random_timeout()
        self._last_heartbeat = time.time()
        self._running = False
        self._votes_received: set[str] = set()

    def _random_timeout(self) -> float:
        return time.time() + (
            LEADER_ELECTION_TIMEOUT_MIN
            + (LEADER_ELECTION_TIMEOUT_MAX - LEADER_ELECTION_TIMEOUT_MIN) * __import__("random").random()
        )

    async def start(self) -> None:
        self._running = True
        logger.info("Consensus module started for {}", self._node_id)

    async def step(self) -> str | None:
        if not self._running:
            return None
        now = time.time()
        result = None
        if self._state.role == RaftRole.LEADER:
            result = await self._send_heartbeats()
        elif self._state.role == RaftRole.FOLLOWER:
            if now > self._election_timeout:
                result = await self._start_election()
        elif self._state.role == RaftRole.CANDIDATE:
            if now > self._election_timeout:
                result = await self._start_election()
        return result

    async def _send_heartbeats(self) -> str | None:
        self._last_heartbeat = time.time()
        return f"heartbeat:term={self._state.current_term}"

    async def _start_election(self) -> str | None:
        self._state.current_term += 1
        self._state.role = RaftRole.CANDIDATE
        self._state.voted_for = self._node_id
        self._votes_received = {self._node_id}
        self._election_timeout = self._random_timeout()
        logger.info("Starting election for term {}", self._state.current_term)
        return f"vote_request:term={self._state.current_term},candidate={self._node_id}"

    def receive_heartbeat(self, leader_id: str, term: int) -> bool:
        if term >= self._state.current_term:
            self._state.current_term = term
            self._state.leader_id = leader_id
            self._state.role = RaftRole.FOLLOWER
            self._last_heartbeat = time.time()
            self._election_timeout = self._random_timeout()
            return True
        return False

    def handle_vote_request(self, candidate_id: str, term: int) -> bool:
        if term > self._state.current_term:
            self._state.current_term = term
            self._state.voted_for = None
            self._state.role = RaftRole.FOLLOWER
        if self._state.voted_for is None or self._state.voted_for == candidate_id:
            self._state.voted_for = candidate_id
            self._last_heartbeat = time.time()
            logger.info("Voting for {} in term {}", candidate_id, term)
            return True
        return False

    def handle_vote_response(self, voter_id: str) -> int:
        self._votes_received.add(voter_id)
        majority = len(self._votes_received) > 1
        if majority and self._state.role == RaftRole.CANDIDATE:
            self._state.role = RaftRole.LEADER
            self._state.leader_id = self._node_id
            logger.info("Elected leader for term {}", self._state.current_term)
        return len(self._votes_received)

    def is_leader(self) -> bool:
        return self._state.role == RaftRole.LEADER

    def leader(self) -> str | None:
        return self._state.leader_id

    def state(self) -> dict[str, Any]:
        return self._state.to_dict()

    async def stop(self) -> None:
        self._running = False
        self._state.role = RaftRole.FOLLOWER
        logger.info("Consensus module stopped")

    def reset_election_timer(self) -> None:
        self._election_timeout = self._random_timeout()
