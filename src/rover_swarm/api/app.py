from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from rover_swarm.api.dependencies import get_settings
from rover_swarm.api.routers import auth, commands, data, missions, search, swarm, tasks, telemetry
from rover_swarm.api.websocket import websocket_alerts, websocket_endpoint, websocket_rover
from rover_swarm.config import Settings
from rover_swarm.exceptions import AuthenticationError, AuthorizationError, RateLimitError

try:
    from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

    def generate_latest(*args: Any, **kwargs: Any) -> bytes:
        return b""

    REGISTRY = None  # type: ignore[assignment]


REQUEST_COUNT = (
    Counter("rover_swarm_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
    if PROMETHEUS_AVAILABLE else None
)
REQUEST_LATENCY = (
    Histogram("rover_swarm_http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"])
    if PROMETHEUS_AVAILABLE else None
)
ACTIVE_CONNECTIONS = (
    Gauge("rover_swarm_http_active_connections", "Active HTTP connections")
    if PROMETHEUS_AVAILABLE else None
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("Starting API server on {}:{}", settings.api.host, settings.api.port)
    yield
    logger.info("API server shutting down")


app = FastAPI(
    title="Rover Swarm Coordination API",
    description="Autonomous rover swarm coordination platform using CRDTs for decentralized coordination in hostile environments.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next: Any) -> Response:
    start = time.time()
    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
        except Exception:
            body = None

    response = await call_next(request)

    duration = time.time() - start
    logger.info(
        "{} {} -> {} ({}ms)",
        request.method,
        request.url.path,
        response.status_code,
        int(duration * 1000),
    )

    if PROMETHEUS_AVAILABLE and REQUEST_COUNT and REQUEST_LATENCY:
        REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path, status=response.status_code).inc()
        REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)

    return response


@app.middleware("http")
async def active_connections_middleware(request: Request, call_next: Any) -> Response:
    if PROMETHEUS_AVAILABLE and ACTIVE_CONNECTIONS:
        ACTIVE_CONNECTIONS.inc()
    response = await call_next(request)
    if PROMETHEUS_AVAILABLE and ACTIVE_CONNECTIONS:
        ACTIVE_CONNECTIONS.dec()
    return response


def _configure_cors(app: FastAPI, settings: Settings) -> None:
    origins = settings.api.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.debug("CORS configured with origins: {}", origins)


def _register_routers(app: FastAPI) -> None:
    app.include_router(swarm.router)
    app.include_router(missions.router)
    app.include_router(commands.router)
    app.include_router(telemetry.router)
    app.include_router(tasks.router)
    app.include_router(search.router)
    app.include_router(data.router)
    app.include_router(auth.router)
    logger.debug("All API routers registered")


def _register_websockets(app: FastAPI) -> None:
    app.add_websocket_route("/ws/swarm", websocket_endpoint)
    app.add_websocket_route("/ws/rovers/{rover_id}", websocket_rover)
    app.add_websocket_route("/ws/alerts", websocket_alerts)
    logger.debug("WebSocket routes registered")


_INSTANCE_START_TIME = time.time()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "rover-swarm-api",
        "timestamp": time.time(),
        "uptime_seconds": int(time.time() - _INSTANCE_START_TIME),
    }


@app.get("/ready")
async def readiness() -> dict[str, Any]:
    return {
        "status": "ready",
        "service": "rover-swarm-api",
        "timestamp": time.time(),
    }


@app.get("/metrics")
async def metrics() -> Response:
    if not PROMETHEUS_AVAILABLE:
        return Response(
            content="# Prometheus client not installed\n",
            media_type="text/plain",
            status_code=501,
        )
    return Response(
        content=generate_latest(REGISTRY).decode("utf-8"),
        media_type="text/plain; charset=utf-8",
    )


@app.exception_handler(AuthenticationError)
async def auth_error_handler(request: Request, exc: AuthenticationError) -> Response:
    return Response(status_code=401, content=str(exc))


@app.exception_handler(AuthorizationError)
async def authz_error_handler(request: Request, exc: AuthorizationError) -> Response:
    return Response(status_code=403, content=str(exc))


@app.exception_handler(RateLimitError)
async def ratelimit_error_handler(request: Request, exc: RateLimitError) -> Response:
    return Response(status_code=429, content=str(exc))


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_cors(app, settings)
    _register_routers(app)
    _register_websockets(app)
    logger.info("FastAPI application created with settings")
    return app


app = create_app()
