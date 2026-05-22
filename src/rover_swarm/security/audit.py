from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from loguru import logger

from rover_swarm.exceptions import SecurityError


class AuditAction(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    AUTHENTICATE = "authenticate"
    AUTHORIZE = "authorize"
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    CONFIGURE = "configure"
    DEPLOY = "deploy"
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    UPGRADE = "upgrade"
    ROLLBACK = "rollback"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    RATE_LIMIT_HIT = "rate_limit_hit"
    CERT_EXPIRED = "cert_expired"
    KEY_ROTATED = "key_rotated"
    AUDIT_LOG_READ = "audit_log_read"


class AuditResult(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class AuditEvent:
    timestamp: float
    event_id: str
    actor: str
    action: AuditAction
    resource: str
    result: AuditResult
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    previous_hash: Optional[str] = None
    hash: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if isinstance(self.action, Enum):
            data["action"] = self.action.value
        if isinstance(self.result, Enum):
            data["result"] = self.result.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEvent":
        data = data.copy()
        if isinstance(data.get("action"), str):
            data["action"] = AuditAction(data["action"])
        if isinstance(data.get("result"), str):
            data["result"] = AuditResult(data["result"])
        return cls(**data)

    def calculate_hash(self, secret_key: bytes, previous_hash: Optional[str] = None) -> str:
        hash_input = {
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "actor": self.actor,
            "action": str(self.action),
            "resource": self.resource,
            "result": str(self.result),
            "source_ip": self.source_ip,
            "details": self.details,
        }
        if previous_hash:
            hash_input["previous_hash"] = previous_hash

        json_str = json.dumps(hash_input, sort_keys=True, default=str)
        h = hmac.new(secret_key, json_str.encode("utf-8"), hashlib.sha256)
        return h.hexdigest()


class AuditLogger:
    MAX_BUFFER_SIZE = 1000

    def __init__(
        self,
        secret_key: bytes,
        log_file: Optional[Path] = None,
        max_buffer_size: int = MAX_BUFFER_SIZE,
        callback: Optional[Callable[[AuditEvent], None]] = None,
    ) -> None:
        if len(secret_key) < 32:
            raise SecurityError("AuditLogger secret key must be at least 32 bytes")

        self._secret_key = secret_key
        self._log_file = log_file
        self._max_buffer_size = max_buffer_size
        self._callback = callback

        self._events: list[AuditEvent] = []
        self._last_hash: Optional[str] = None
        self._events_by_actor: dict[str, list[int]] = {}
        self._events_by_action: dict[AuditAction, list[int]] = {}
        self._events_by_resource: dict[str, list[int]] = {}

        if log_file and log_file.exists():
            self._load_from_file(log_file)

        logger.info(
            "AuditLogger initialized: log_file={}, buffered_events={}",
            log_file,
            len(self._events),
        )

    def _load_from_file(self, path: Path) -> None:
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)
                    event = AuditEvent.from_dict(data)

                    self._events.append(event)
                    self._last_hash = event.hash

                    idx = len(self._events) - 1
                    self._index_event(idx, event)

            logger.debug("Loaded {} audit events from {}", len(self._events), path)
        except Exception as e:
            logger.error("Failed to load audit log: {}", e)

    def _index_event(self, idx: int, event: AuditEvent) -> None:
        if event.actor not in self._events_by_actor:
            self._events_by_actor[event.actor] = []
        self._events_by_actor[event.actor].append(idx)

        if event.action not in self._events_by_action:
            self._events_by_action[event.action] = []
        self._events_by_action[event.action].append(idx)

        if event.resource not in self._events_by_resource:
            self._events_by_resource[event.resource] = []
        self._events_by_resource[event.resource].append(idx)

    def _write_event(self, event: AuditEvent) -> None:
        if not self._log_file:
            return

        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_file, "a") as f:
                f.write(json.dumps(event.to_dict(), default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write audit event: {}", e)

    def log_event(
        self,
        actor: str,
        action: AuditAction,
        resource: str,
        result: AuditResult,
        source_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        import secrets

        timestamp = datetime.now(timezone.utc).timestamp()
        event_id = secrets.token_hex(8)

        event = AuditEvent(
            timestamp=timestamp,
            event_id=event_id,
            actor=actor,
            action=action,
            resource=resource,
            result=result,
            source_ip=source_ip,
            user_agent=user_agent,
            session_id=session_id,
            request_id=request_id,
            details=details or {},
            previous_hash=self._last_hash,
        )

        event.hash = event.calculate_hash(self._secret_key, self._last_hash)
        self._last_hash = event.hash

        self._events.append(event)
        idx = len(self._events) - 1
        self._index_event(idx, event)

        self._write_event(event)

        if self._callback:
            try:
                self._callback(event)
            except Exception as e:
                logger.error("Audit callback failed: {}", e)

        if len(self._events) > self._max_buffer_size * 2:
            self._trim_buffer()

        logger.debug(
            "Audit event: actor={}, action={}, resource={}, result={}",
            actor,
            action,
            resource,
            result,
        )
        return event

    def _trim_buffer(self) -> None:
        target_size = self._max_buffer_size
        if len(self._events) <= target_size:
            return

        remove_count = len(self._events) - target_size
        removed_hashes = self._events[:remove_count]
        self._events = self._events[remove_count:]

        self._events_by_actor.clear()
        self._events_by_action.clear()
        self._events_by_resource.clear()

        for idx, event in enumerate(self._events):
            self._index_event(idx, event)

        logger.debug("Trimmed {} events from audit buffer", remove_count)

    def verify_integrity(self) -> tuple[bool, list[str]]:
        errors: list[str] = []

        if len(self._events) < 2:
            return True, []

        first_event = self._events[0]
        expected_hash = first_event.calculate_hash(self._secret_key, first_event.previous_hash)
        if first_event.hash != expected_hash:
            errors.append(f"Event 0 (id={first_event.event_id}): hash mismatch")

        for i in range(1, len(self._events)):
            prev_event = self._events[i - 1]
            curr_event = self._events[i]

            if curr_event.previous_hash != prev_event.hash:
                errors.append(
                    f"Event {i} (id={curr_event.event_id}): "
                    f"previous_hash mismatch (expected {prev_event.hash}, got {curr_event.previous_hash})"
                )

            expected_hash = curr_event.calculate_hash(self._secret_key, curr_event.previous_hash)
            if curr_event.hash != expected_hash:
                errors.append(f"Event {i} (id={curr_event.event_id}): hash mismatch")

        return len(errors) == 0, errors

    def query_events(
        self,
        actor: Optional[str] = None,
        action: Optional[AuditAction] = None,
        resource: Optional[str] = None,
        result: Optional[AuditResult] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        candidate_indices: Optional[set[int]] = None

        if actor is not None:
            actor_indices = set(self._events_by_actor.get(actor, []))
            candidate_indices = (
                actor_indices if candidate_indices is None else candidate_indices & actor_indices
            )

        if action is not None:
            action_indices = set(self._events_by_action.get(action, []))
            candidate_indices = (
                action_indices if candidate_indices is None else candidate_indices & action_indices
            )

        if resource is not None:
            resource_indices = set(self._events_by_resource.get(resource, []))
            candidate_indices = (
                resource_indices if candidate_indices is None else candidate_indices & resource_indices
            )

        if candidate_indices is None:
            candidate_indices = set(range(len(self._events)))

        matching: list[AuditEvent] = []

        for idx in sorted(candidate_indices):
            event = self._events[idx]

            if result is not None and event.result != result:
                continue

            if start_time is not None and event.timestamp < start_time:
                continue

            if end_time is not None and event.timestamp > end_time:
                continue

            matching.append(event)

        matching.sort(key=lambda e: e.timestamp, reverse=True)
        return matching[offset : offset + limit]

    def export_events(
        self,
        output_path: Path,
        events: Optional[Sequence[AuditEvent]] = None,
        format: str = "jsonl",
    ) -> int:
        if events is None:
            events = self._events

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "jsonl":
            with open(output_path, "w") as f:
                for event in events:
                    f.write(json.dumps(event.to_dict(), default=str) + "\n")
        elif format == "json":
            data = [event.to_dict() for event in events]
            with open(output_path, "w") as f:
                json.dump(data, f, default=str, indent=2)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info("Exported {} audit events to {}", len(events), output_path)
        return len(events)

    def get_statistics(self) -> dict[str, Any]:
        if not self._events:
            return {
                "total_events": 0,
                "oldest_event": None,
                "newest_event": None,
                "by_actor": {},
                "by_action": {},
                "by_result": {},
                "integrity_verified": None,
            }

        by_result: dict[str, int] = {}
        for event in self._events:
            result_val = str(event.result)
            by_result[result_val] = by_result.get(result_val, 0) + 1

        integrity_ok, _ = self.verify_integrity()

        return {
            "total_events": len(self._events),
            "oldest_event": self._events[0].timestamp,
            "newest_event": self._events[-1].timestamp,
            "by_actor": {actor: len(indices) for actor, indices in self._events_by_actor.items()},
            "by_action": {str(action): len(indices) for action, indices in self._events_by_action.items()},
            "by_result": by_result,
            "integrity_verified": integrity_ok,
        }

    def login_success(self, actor: str, source_ip: Optional[str] = None, **details: Any) -> AuditEvent:
        return self.log_event(
            actor=actor,
            action=AuditAction.LOGIN,
            resource="session",
            result=AuditResult.SUCCESS,
            source_ip=source_ip,
            details=details,
        )

    def login_failure(self, actor: str, source_ip: Optional[str] = None, **details: Any) -> AuditEvent:
        return self.log_event(
            actor=actor or "unknown",
            action=AuditAction.LOGIN,
            resource="session",
            result=AuditResult.UNAUTHORIZED,
            source_ip=source_ip,
            details=details,
        )

    def access_denied(
        self,
        actor: str,
        action: AuditAction,
        resource: str,
        source_ip: Optional[str] = None,
        **details: Any,
    ) -> AuditEvent:
        return self.log_event(
            actor=actor,
            action=action,
            resource=resource,
            result=AuditResult.FORBIDDEN,
            source_ip=source_ip,
            details=details,
        )

    def resource_create(
        self,
        actor: str,
        resource: str,
        source_ip: Optional[str] = None,
        **details: Any,
    ) -> AuditEvent:
        return self.log_event(
            actor=actor,
            action=AuditAction.CREATE,
            resource=resource,
            result=AuditResult.SUCCESS,
            source_ip=source_ip,
            details=details,
        )

    def resource_delete(
        self,
        actor: str,
        resource: str,
        source_ip: Optional[str] = None,
        **details: Any,
    ) -> AuditEvent:
        return self.log_event(
            actor=actor,
            action=AuditAction.DELETE,
            resource=resource,
            result=AuditResult.SUCCESS,
            source_ip=source_ip,
            details=details,
        )
