from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional, Protocol, Sequence

from loguru import logger

from rover_swarm.exceptions import AuthenticationError, AuthorizationError

try:
    import jwt
    from jwt import ExpiredSignatureError, InvalidTokenError, PyJWTError

    HAS_JWT = True
except ImportError:
    HAS_JWT = False
    logger.warning("PyJWT not installed. JWT auth will be unavailable.")


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    OBSERVER = "observer"
    ROVER = "rover"


class Permission(str, Enum):
    ROVER_READ = "rover:read"
    ROVER_WRITE = "rover:write"
    ROVER_DELETE = "rover:delete"
    ROVER_COMMAND = "rover:command"
    MISSION_READ = "mission:read"
    MISSION_WRITE = "mission:write"
    MISSION_DELETE = "mission:delete"
    MISSION_START = "mission:start"
    MISSION_STOP = "mission:stop"
    SWARM_CONFIG_READ = "swarm:config:read"
    SWARM_CONFIG_WRITE = "swarm:config:write"
    SWARM_UPGRADE = "swarm:upgrade"
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    SYSTEM_ADMIN = "system:admin"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        Permission.ROVER_READ,
        Permission.ROVER_WRITE,
        Permission.ROVER_DELETE,
        Permission.ROVER_COMMAND,
        Permission.MISSION_READ,
        Permission.MISSION_WRITE,
        Permission.MISSION_DELETE,
        Permission.MISSION_START,
        Permission.MISSION_STOP,
        Permission.SWARM_CONFIG_READ,
        Permission.SWARM_CONFIG_WRITE,
        Permission.SWARM_UPGRADE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
        Permission.AUDIT_READ,
        Permission.AUDIT_EXPORT,
        Permission.SYSTEM_ADMIN,
    },
    Role.OPERATOR: {
        Permission.ROVER_READ,
        Permission.ROVER_WRITE,
        Permission.ROVER_COMMAND,
        Permission.MISSION_READ,
        Permission.MISSION_WRITE,
        Permission.MISSION_START,
        Permission.MISSION_STOP,
        Permission.SWARM_CONFIG_READ,
        Permission.AUDIT_READ,
    },
    Role.OBSERVER: {
        Permission.ROVER_READ,
        Permission.MISSION_READ,
        Permission.SWARM_CONFIG_READ,
        Permission.AUDIT_READ,
    },
    Role.ROVER: {
        Permission.ROVER_READ,
        Permission.MISSION_READ,
    },
}


@dataclass
class UserIdentity:
    user_id: str
    username: str
    role: Role
    permissions: set[Permission] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


@dataclass
class JwtConfig:
    secret: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    issuer: str = "rover-swarm"
    audience: Optional[str] = None


class JwtAuthProvider:
    def __init__(self, config: JwtConfig) -> None:
        if not HAS_JWT:
            raise ImportError("PyJWT is required for JwtAuthProvider. Install with 'pip install pyjwt'.")
        self.config = config
        self._secret_bytes = config.secret.encode("utf-8")
        logger.info("JwtAuthProvider initialized with algorithm: {}", config.algorithm)

    def create_access_token(
        self,
        user_id: str,
        role: Role,
        permissions: Optional[Sequence[Permission]] = None,
        custom_claims: Optional[dict[str, Any]] = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.config.access_token_expire_minutes)

        perms_list = [str(p) for p in (permissions or [])]
        claims: dict[str, Any] = {
            "sub": user_id,
            "role": str(role),
            "permissions": perms_list,
            "type": "access",
            "iat": now,
            "exp": expire,
            "iss": self.config.issuer,
        }

        if self.config.audience:
            claims["aud"] = self.config.audience

        if custom_claims:
            claims.update(custom_claims)

        token = jwt.encode(claims, self._secret_bytes, algorithm=self.config.algorithm)
        logger.debug("Created access token for user: {}", user_id)
        return token

    def create_refresh_token(self, user_id: str, custom_claims: Optional[dict[str, Any]] = None) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=self.config.refresh_token_expire_days)

        claims: dict[str, Any] = {
            "sub": user_id,
            "type": "refresh",
            "iat": now,
            "exp": expire,
            "iss": self.config.issuer,
        }

        if custom_claims:
            claims.update(custom_claims)

        token = jwt.encode(claims, self._secret_bytes, algorithm=self.config.algorithm)
        logger.debug("Created refresh token for user: {}", user_id)
        return token

    def validate_token(self, token: str) -> dict[str, Any]:
        try:
            options = {"verify_aud": bool(self.config.audience)}
            payload = jwt.decode(
                token,
                self._secret_bytes,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer,
                audience=self.config.audience,
                options=options,
            )
            return payload
        except ExpiredSignatureError:
            logger.debug("Token has expired")
            raise AuthenticationError("Token has expired")
        except InvalidTokenError as e:
            logger.debug("Invalid token: {}", str(e))
            raise AuthenticationError(f"Invalid token: {str(e)}")

    def refresh_access_token(
        self,
        refresh_token: str,
        role: Role,
        permissions: Optional[Sequence[Permission]] = None,
    ) -> tuple[str, str]:
        payload = self.validate_token(refresh_token)

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type for refresh")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token: missing subject")

        new_access = self.create_access_token(user_id, role, permissions)
        new_refresh = self.create_refresh_token(user_id)

        logger.info("Refreshed tokens for user: {}", user_id)
        return new_access, new_refresh

    def get_user_from_token(self, token: str) -> UserIdentity:
        payload = self.validate_token(token)

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Token missing subject claim")

        role_str = payload.get("role")
        if role_str:
            try:
                role = Role(role_str)
            except ValueError:
                logger.warning("Unknown role in token: {}", role_str)
                role = Role.OBSERVER
        else:
            role = Role.OBSERVER

        perms_str = payload.get("permissions", [])
        permissions = set()
        for p in perms_str:
            try:
                permissions.add(Permission(p))
            except ValueError:
                pass

        if not permissions:
            permissions = ROLE_PERMISSIONS.get(role, set())

        return UserIdentity(
            user_id=user_id,
            username=payload.get("username", user_id),
            role=role,
            permissions=permissions,
            metadata={
                "token_type": payload.get("type"),
                "issued_at": payload.get("iat"),
                "expires_at": payload.get("exp"),
            },
        )


class RbacProvider:
    def __init__(self, role_permissions: Optional[dict[Role, set[Permission]]] = None) -> None:
        self._role_permissions = role_permissions or ROLE_PERMISSIONS.copy()
        self._user_roles: dict[str, Role] = {}
        self._user_permissions: dict[str, set[Permission]] = {}
        logger.info("RbacProvider initialized with {} roles", len(self._role_permissions))

    def assign_role(self, user_id: str, role: Role) -> None:
        self._user_roles[user_id] = role
        base_permissions = self._role_permissions.get(role, set())
        self._user_permissions[user_id] = base_permissions.copy()
        logger.info("Assigned role {} to user {}", role, user_id)

    def get_role(self, user_id: str) -> Role:
        return self._user_roles.get(user_id, Role.OBSERVER)

    def add_permission(self, user_id: str, permission: Permission) -> None:
        if user_id not in self._user_permissions:
            self._user_permissions[user_id] = set()
        self._user_permissions[user_id].add(permission)
        logger.debug("Added permission {} to user {}", permission, user_id)

    def remove_permission(self, user_id: str, permission: Permission) -> None:
        if user_id in self._user_permissions:
            self._user_permissions[user_id].discard(permission)
            logger.debug("Removed permission {} from user {}", permission, user_id)

    def has_permission(self, user_id: str, permission: Permission) -> bool:
        user_perms = self._user_permissions.get(user_id, set())
        if Permission.SYSTEM_ADMIN in user_perms:
            return True
        return permission in user_perms

    def has_role(self, user_id: str, role: Role) -> bool:
        return self._user_roles.get(user_id) == role

    def require_permission(self, user_id: str, permission: Permission) -> None:
        if not self.has_permission(user_id, permission):
            raise AuthorizationError(f"User {user_id} lacks permission: {permission}")

    def require_role(self, user_id: str, role: Role) -> None:
        if not self.has_role(user_id, role):
            raise AuthorizationError(f"User {user_id} requires role: {role}")

    def get_user_permissions(self, user_id: str) -> set[Permission]:
        return self._user_permissions.get(user_id, set()).copy()


@dataclass
class ApiKeyHash:
    hash_bytes: bytes
    salt: bytes
    created_at: float
    last_used_at: Optional[float] = None
    user_id: Optional[str] = None
    is_active: bool = True


class ApiKeyProvider:
    API_KEY_PREFIX = "rv"
    API_KEY_LENGTH = 48
    SALT_LENGTH = 16
    HASH_ITERATIONS = 100000

    def __init__(self) -> None:
        self._keys: dict[str, ApiKeyHash] = {}
        logger.info("ApiKeyProvider initialized")

    def generate_key(self, user_id: Optional[str] = None) -> tuple[str, str]:
        raw_key = secrets.token_bytes(self.API_KEY_LENGTH)
        key_encoded = base64.urlsafe_b64encode(raw_key).decode("ascii").rstrip("=")
        full_key = f"{self.API_KEY_PREFIX}_{key_encoded}"

        key_id = secrets.token_hex(8)
        salt = secrets.token_bytes(self.SALT_LENGTH)
        key_hash = self._hash_key(full_key, salt)

        self._keys[key_id] = ApiKeyHash(
            hash_bytes=key_hash,
            salt=salt,
            created_at=datetime.now(timezone.utc).timestamp(),
            user_id=user_id,
        )

        logger.info("Generated API key ID {} for user {}", key_id, user_id or "anonymous")
        return key_id, full_key

    def validate_key(self, key: str) -> tuple[bool, Optional[str]]:
        if not key or not key.startswith(f"{self.API_KEY_PREFIX}_"):
            return False, None

        for key_id, stored in self._keys.items():
            if not stored.is_active:
                continue

            computed_hash = self._hash_key(key, stored.salt)
            if hmac.compare_digest(computed_hash, stored.hash_bytes):
                stored.last_used_at = datetime.now(timezone.utc).timestamp()
                logger.debug("Validated API key: {}", key_id)
                return True, stored.user_id

        logger.debug("Invalid API key provided")
        return False, None

    def revoke_key(self, key_id: str) -> bool:
        if key_id in self._keys:
            self._keys[key_id].is_active = False
            logger.info("Revoked API key: {}", key_id)
            return True
        return False

    def _hash_key(self, key: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            key.encode("utf-8"),
            salt,
            self.HASH_ITERATIONS,
            dklen=32,
        )


class AuthMiddleware:
    def __init__(
        self,
        jwt_provider: JwtAuthProvider,
        rbac_provider: Optional[RbacProvider] = None,
        api_key_provider: Optional[ApiKeyProvider] = None,
        exclude_paths: Optional[Sequence[str]] = None,
    ) -> None:
        self.jwt_provider = jwt_provider
        self.rbac_provider = rbac_provider or RbacProvider()
        self.api_key_provider = api_key_provider
        self.exclude_paths = set(exclude_paths or ["/health", "/openapi.json", "/docs"])
        logger.info("AuthMiddleware initialized")

    def _is_excluded(self, path: str) -> bool:
        for excluded in self.exclude_paths:
            if path == excluded or path.startswith(excluded + "/"):
                return True
        return False

    def extract_bearer_token(self, authorization: Optional[str]) -> Optional[str]:
        if authorization and authorization.startswith("Bearer "):
            return authorization[7:]
        return None

    def extract_api_key(self, authorization: Optional[str], x_api_key: Optional[str]) -> Optional[str]:
        if x_api_key:
            return x_api_key
        if authorization and authorization.startswith("ApiKey "):
            return authorization[7:]
        return None

    async def authenticate_request(
        self,
        path: str,
        authorization_header: Optional[str] = None,
        x_api_key_header: Optional[str] = None,
    ) -> Optional[UserIdentity]:
        if self._is_excluded(path):
            return None

        jwt_token = self.extract_bearer_token(authorization_header)
        if jwt_token:
            try:
                user = self.jwt_provider.get_user_from_token(jwt_token)
                logger.debug("Authenticated via JWT: {}", user.user_id)
                return user
            except AuthenticationError:
                pass

        if self.api_key_provider:
            api_key = self.extract_api_key(authorization_header, x_api_key_header)
            if api_key:
                valid, user_id = self.api_key_provider.validate_key(api_key)
                if valid:
                    role = self.rbac_provider.get_role(user_id) if user_id else Role.OBSERVER
                    perms = self.rbac_provider.get_user_permissions(user_id) if user_id else set()
                    user = UserIdentity(
                        user_id=user_id or "api-key-user",
                        username=user_id or "api-key-user",
                        role=role,
                        permissions=perms,
                    )
                    logger.debug("Authenticated via API key: {}", user.user_id)
                    return user

        raise AuthenticationError("No valid authentication credentials provided")
