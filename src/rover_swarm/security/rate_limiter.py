from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional, Protocol

from loguru import logger

from rover_swarm.constants import RATE_LIMIT_DEFAULT, RATE_LIMIT_WINDOW
from rover_swarm.exceptions import RateLimitError


class RateLimitScope(str, Enum):
    GLOBAL = "global"
    IP = "ip"
    USER = "user"
    ENDPOINT = "endpoint"


@dataclass
class RateLimitConfig:
    requests_per_window: int = RATE_LIMIT_DEFAULT
    window_seconds: int = RATE_LIMIT_WINDOW
    scope: RateLimitScope = RateLimitScope.IP
    burst_multiplier: float = 1.0


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float
    tokens: float
    last_refill: float

    def __post_init__(self) -> None:
        if self.tokens < 0:
            self.tokens = 0
        if self.tokens > self.capacity:
            self.tokens = self.capacity


class RateLimiter:
    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        self.config = config or RateLimitConfig()
        self._buckets: dict[str, TokenBucket] = {}
        self._endpoint_configs: dict[str, RateLimitConfig] = {}
        logger.info(
            "RateLimiter initialized: {}/{}s scope={}",
            self.config.requests_per_window,
            self.config.window_seconds,
            self.config.scope,
        )

    def configure_endpoint(self, endpoint: str, config: RateLimitConfig) -> None:
        self._endpoint_configs[endpoint] = config
        logger.debug("Configured rate limit for endpoint {}: {}", endpoint, config)

    def _get_bucket_key(self, identifier: str, endpoint: Optional[str] = None) -> str:
        if endpoint and endpoint in self._endpoint_configs:
            return f"{endpoint}:{identifier}"
        return identifier

    def _get_config(self, endpoint: Optional[str] = None) -> RateLimitConfig:
        if endpoint and endpoint in self._endpoint_configs:
            return self._endpoint_configs[endpoint]
        return self.config

    def _get_or_create_bucket(
        self,
        key: str,
        config: RateLimitConfig,
    ) -> TokenBucket:
        if key not in self._buckets:
            capacity = config.requests_per_window * config.burst_multiplier
            refill_rate = config.requests_per_window / config.window_seconds
            self._buckets[key] = TokenBucket(
                capacity=capacity,
                refill_rate=refill_rate,
                tokens=capacity,
                last_refill=time.monotonic(),
            )
        return self._buckets[key]

    def _refill_bucket(self, bucket: TokenBucket, now: float) -> None:
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            new_tokens = elapsed * bucket.refill_rate
            bucket.tokens = min(bucket.capacity, bucket.tokens + new_tokens)
            bucket.last_refill = now

    def try_acquire(
        self,
        identifier: str,
        tokens: int = 1,
        endpoint: Optional[str] = None,
    ) -> bool:
        config = self._get_config(endpoint)
        key = self._get_bucket_key(identifier, endpoint)
        bucket = self._get_or_create_bucket(key, config)

        now = time.monotonic()
        self._refill_bucket(bucket, now)

        if bucket.tokens >= tokens:
            bucket.tokens -= tokens
            logger.debug("Acquired {} tokens for {}, remaining: {}", tokens, key, bucket.tokens)
            return True

        logger.debug("Rate limit exceeded for {}", key)
        return False

    def acquire(
        self,
        identifier: str,
        tokens: int = 1,
        endpoint: Optional[str] = None,
    ) -> None:
        if not self.try_acquire(identifier, tokens, endpoint):
            config = self._get_config(endpoint)
            raise RateLimitError(
                f"Rate limit exceeded. Max {config.requests_per_window} requests "
                f"per {config.window_seconds} seconds."
            )

    def get_remaining(
        self,
        identifier: str,
        endpoint: Optional[str] = None,
    ) -> float:
        config = self._get_config(endpoint)
        key = self._get_bucket_key(identifier, endpoint)

        if key not in self._buckets:
            return config.requests_per_window * config.burst_multiplier

        bucket = self._buckets[key]
        now = time.monotonic()
        self._refill_bucket(bucket, now)
        return bucket.tokens

    def get_reset_time(
        self,
        identifier: str,
        endpoint: Optional[str] = None,
    ) -> int:
        config = self._get_config(endpoint)
        key = self._get_bucket_key(identifier, endpoint)

        if key not in self._buckets:
            return int(time.time())

        bucket = self._buckets[key]
        now = time.monotonic()
        self._refill_bucket(bucket, now)

        tokens_needed = bucket.capacity - bucket.tokens
        if tokens_needed <= 0:
            return int(time.time())

        seconds_needed = tokens_needed / bucket.refill_rate
        return int(time.time() + seconds_needed)

    def get_rate_limit_headers(
        self,
        identifier: str,
        endpoint: Optional[str] = None,
    ) -> dict[str, str]:
        config = self._get_config(endpoint)
        remaining = self.get_remaining(identifier, endpoint)
        reset_time = self.get_reset_time(identifier, endpoint)

        return {
            "X-RateLimit-Limit": str(config.requests_per_window),
            "X-RateLimit-Remaining": str(int(remaining)),
            "X-RateLimit-Reset": str(reset_time),
            "Retry-After": str(max(1, reset_time - int(time.time()))),
        }

    def cleanup_stale_buckets(self, max_age_seconds: float = 3600) -> int:
        now = time.monotonic()
        stale_keys = [
            key
            for key, bucket in self._buckets.items()
            if (now - bucket.last_refill) > max_age_seconds
        ]

        for key in stale_keys:
            del self._buckets[key]

        if stale_keys:
            logger.debug("Cleaned up {} stale rate limit buckets", len(stale_keys))

        return len(stale_keys)


@dataclass
class RateLimitRule:
    endpoint: str
    config: RateLimitConfig
    methods: set[str] = field(default_factory=lambda: {"GET", "POST", "PUT", "DELETE", "PATCH"})


class RateLimitMiddleware:
    def __init__(
        self,
        limiter: Optional[RateLimiter] = None,
        config: Optional[RateLimitConfig] = None,
        rules: Optional[list[RateLimitRule]] = None,
        exclude_paths: Optional[list[str]] = None,
        identifier_callback: Optional[Callable[[Any], str]] = None,
    ) -> None:
        self.limiter = limiter or RateLimiter(config)
        self.exclude_paths = set(exclude_paths or ["/health", "/metrics"])
        self.identifier_callback = identifier_callback or self._default_identifier
        self.rules: dict[str, RateLimitRule] = {}

        if rules:
            for rule in rules:
                self.rules[rule.endpoint] = rule
                self.limiter.configure_endpoint(rule.endpoint, rule.config)

        logger.info("RateLimitMiddleware initialized with {} rules", len(self.rules))

    @staticmethod
    def _default_identifier(request: Any) -> str:
        client_host = getattr(getattr(request, "client", None), "host", None)
        if client_host:
            return client_host

        forwarded = getattr(request, "headers", {}).get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()

        return "unknown"

    def _get_identifier(self, request: Any, scope: RateLimitScope) -> str:
        base_id = self.identifier_callback(request)

        if scope == RateLimitScope.GLOBAL:
            return "global"
        elif scope == RateLimitScope.IP:
            return base_id
        elif scope == RateLimitScope.USER:
            user = getattr(request, "state", None)
            if user and hasattr(user, "user"):
                user_id = getattr(user.user, "user_id", None)
                if user_id:
                    return f"user:{user_id}"
            return f"ip:{base_id}"
        elif scope == RateLimitScope.ENDPOINT:
            path = getattr(getattr(request, "scope", {}), "path", None) or getattr(request, "url", None)
            return f"endpoint:{path or 'unknown'}"

        return base_id

    def _is_excluded(self, path: str) -> bool:
        for excluded in self.exclude_paths:
            if path == excluded or path.startswith(excluded + "/"):
                return True
        return False

    def _match_rule(self, path: str, method: str) -> Optional[RateLimitRule]:
        for endpoint, rule in self.rules.items():
            if method not in rule.methods:
                continue

            if endpoint == path or path.startswith(endpoint + "/"):
                return rule

            import fnmatch
            if fnmatch.fnmatch(path, endpoint):
                return rule

        return None

    async def check_rate_limit(
        self,
        request: Any,
        path: str,
        method: str,
    ) -> tuple[bool, dict[str, str]]:
        if self._is_excluded(path):
            return True, {}

        rule = self._match_rule(path, method)

        if rule:
            config = rule.config
            endpoint = rule.endpoint
        else:
            config = self.limiter.config
            endpoint = None

        identifier = self._get_identifier(request, config.scope)

        if self.limiter.try_acquire(identifier, endpoint=endpoint):
            headers = self.limiter.get_rate_limit_headers(identifier, endpoint)
            return True, headers

        headers = self.limiter.get_rate_limit_headers(identifier, endpoint)
        return False, headers
