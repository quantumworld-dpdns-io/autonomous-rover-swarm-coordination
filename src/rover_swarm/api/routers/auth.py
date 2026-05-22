from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from rover_swarm.api.dependencies import (
    get_current_user,
    get_jwt_provider,
    get_rbac_provider,
)
from rover_swarm.exceptions import AuthenticationError
from rover_swarm.security.auth import JwtAuthProvider, RbacProvider, Role, UserIdentity

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfoResponse(BaseModel):
    user_id: str
    username: str
    role: str
    permissions: list[str]


_DEMO_USERS: dict[str, dict[str, Any]] = {
    "admin": {"password": "admin", "role": Role.ADMIN},
    "operator": {"password": "operator", "role": Role.OPERATOR},
    "observer": {"password": "observer", "role": Role.OBSERVER},
}


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    jwt_provider: Annotated[JwtAuthProvider, Depends(get_jwt_provider)],
    rbac: Annotated[RbacProvider, Depends(get_rbac_provider)],
) -> TokenResponse:
    user_info = _DEMO_USERS.get(body.username)
    if user_info is None or user_info["password"] != body.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    role = user_info["role"]
    user_id = body.username
    permissions = list(rbac._role_permissions.get(role, set()))  # type: ignore[attr-defined]

    access_token = jwt_provider.create_access_token(
        user_id=user_id,
        role=role,
        permissions=permissions,
    )
    refresh_token = jwt_provider.create_refresh_token(user_id=user_id)

    logger.info("User logged in: {} ({})", user_id, role.value)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    jwt_provider: Annotated[JwtAuthProvider, Depends(get_jwt_provider)],
    rbac: Annotated[RbacProvider, Depends(get_rbac_provider)],
) -> TokenResponse:
    try:
        payload = jwt_provider.validate_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token type")

        user_id = payload.get("sub", "")
        role = rbac.get_role(user_id)
        permissions = list(rbac._role_permissions.get(role, set()))  # type: ignore[attr-defined]

        new_access = jwt_provider.create_access_token(
            user_id=user_id,
            role=role,
            permissions=permissions,
        )
        new_refresh = jwt_provider.create_refresh_token(user_id=user_id)

        logger.info("Tokens refreshed for user: {}", user_id)
        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.get("/me", response_model=UserInfoResponse)
async def me(
    current_user: Annotated[UserIdentity, Depends(get_current_user)],
) -> UserInfoResponse:
    return UserInfoResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        role=current_user.role.value,
        permissions=[p.value for p in current_user.permissions],
    )
