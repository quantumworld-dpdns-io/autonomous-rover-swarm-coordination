from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request, status
from loguru import logger

from rover_swarm.config import Settings, settings as global_settings
from rover_swarm.crdt.swarm_state import SwarmState
from rover_swarm.exceptions import AuthenticationError, AuthorizationError
from rover_swarm.security import AuthMiddleware, JwtAuthProvider, Permission, RbacProvider
from rover_swarm.security.auth import JwtConfig, UserIdentity
from rover_swarm.vector_db import VectorDbManager


_settings = global_settings


def get_settings() -> Settings:
    return _settings


_jwt_provider = JwtAuthProvider(
    JwtConfig(
        secret=_settings.api.jwt_secret,
        algorithm=_settings.api.jwt_algorithm,
        access_token_expire_minutes=_settings.api.access_token_expire_minutes,
    )
)

_rbac_provider = RbacProvider()

_auth_middleware = AuthMiddleware(
    jwt_provider=_jwt_provider,
    rbac_provider=_rbac_provider,
)

_rover_state: SwarmState | None = None
_vector_db_manager: VectorDbManager | None = None


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> UserIdentity:
    try:
        user = await _auth_middleware.authenticate_request(
            path="",
            authorization_header=authorization,
            x_api_key_header=x_api_key,
        )
        if user is None:
            raise AuthenticationError("Authentication required")
        logger.debug("Authenticated user: {}", user.user_id)
        return user
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> UserIdentity | None:
    try:
        return await _auth_middleware.authenticate_request(
            path="",
            authorization_header=authorization,
            x_api_key_header=x_api_key,
        )
    except AuthenticationError:
        return None


def require_permission(*permissions: Permission):
    async def permission_dependency(current_user: Annotated[UserIdentity, Depends(get_current_user)]) -> UserIdentity:
        for permission in permissions:
            if not _rbac_provider.has_permission(current_user.user_id, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing permission: {permission.value}",
                )
        return current_user

    return permission_dependency


async def get_vector_db() -> AsyncGenerator[VectorDbManager, None]:
    global _vector_db_manager
    if _vector_db_manager is None:
        from rover_swarm.vector_db import ChromaDb, LanceDb, MilvusDb, QdrantDb, WeaviateDb
        from rover_swarm.vector_db.base import VectorDbConfig
        from rover_swarm.vector_db.manager import ManagerConfig

        backend_map: dict[str, Any] = {}
        config = _settings.vector_db

        backends_to_init: list[tuple[str, type, object]] = [
            ("chroma", ChromaDb, config.chroma),
            ("milvus", MilvusDb, config.milvus),
            ("qdrant", QdrantDb, config.qdrant),
            ("weaviate", WeaviateDb, config.weaviate),
            ("lancedb", LanceDb, VectorDbConfig()),
        ]

        for name, cls, backend_config in backends_to_init:
            try:
                instance = cls(backend_config)
                await instance.connect()
                backend_map[name] = instance
                logger.info("Connected vector DB backend: {}", name)
            except Exception as e:
                logger.warning("Failed to initialize vector DB backend {}: {}", name, e)

        _vector_db_manager = VectorDbManager(
            backends=backend_map,
            config=ManagerConfig(active_backend=config.active_backend),
        )

    yield _vector_db_manager


async def get_rover_state() -> SwarmState:
    global _rover_state
    if _rover_state is None:
        _rover_state = SwarmState(swarm_id=_settings.mission_id)
        logger.info("SwarmState initialized: {}", _settings.mission_id)
    return _rover_state


def get_jwt_provider() -> JwtAuthProvider:
    return _jwt_provider


def get_rbac_provider() -> RbacProvider:
    return _rbac_provider
