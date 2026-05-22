from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from loguru import logger

from rover_swarm.exceptions import ValidationError
from rover_swarm.types import RoverId


class InputValidator:
    ROVER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")
    MISSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
    USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9._-]{0,31}$")
    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        re.IGNORECASE,
    )
    SQL_KEYWORDS = {
        "SELECT",
        "INSERT",
        "DELETE",
        "UPDATE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "UNION",
        "JOIN",
        "WHERE",
        "OR",
        "AND",
        "EXEC",
        "EXECUTE",
        "SP_",
        "XP_",
        "--",
        ";",
        "'",
        "\"",
        "\\",
        "/*",
        "*/",
    }
    SHELL_DANGEROUS = {
        ";",
        "&",
        "|",
        "`",
        "$",
        "(",
        ")",
        "<",
        ">",
        "\n",
        "\r",
        "!",
        "{",
        "}",
        "[",
        "]",
    }

    def __init__(self) -> None:
        self._sql_keywords_lower = {k.lower() for k in self.SQL_KEYWORDS}
        logger.info("InputValidator initialized")

    def validate_rover_id(self, rover_id: RoverId) -> bool:
        if not rover_id:
            logger.debug("Invalid rover_id: empty")
            return False

        if len(rover_id) > 64:
            logger.debug("Invalid rover_id: too long ({})", len(rover_id))
            return False

        if not self.ROVER_ID_PATTERN.match(rover_id):
            logger.debug("Invalid rover_id format: {}", rover_id)
            return False

        return True

    def require_valid_rover_id(self, rover_id: RoverId) -> None:
        if not self.validate_rover_id(rover_id):
            raise ValidationError(f"Invalid rover_id: {rover_id}")

    def validate_mission_id(self, mission_id: str) -> bool:
        if not mission_id:
            return False

        if len(mission_id) > 128:
            return False

        return bool(self.MISSION_ID_PATTERN.match(mission_id))

    def require_valid_mission_id(self, mission_id: str) -> None:
        if not self.validate_mission_id(mission_id):
            raise ValidationError(f"Invalid mission_id: {mission_id}")

    def validate_username(self, username: str) -> bool:
        if not username or len(username) < 2 or len(username) > 32:
            return False

        return bool(self.USERNAME_PATTERN.match(username))

    def validate_email(self, email: str) -> bool:
        if not email or len(email) > 254:
            return False

        return bool(self.EMAIL_PATTERN.match(email))

    def validate_url(self, url: str, allowed_schemes: Optional[set[str]] = None) -> bool:
        if not url or len(url) > 2048:
            return False

        try:
            parsed = urlparse(url)
        except ValueError:
            logger.debug("Invalid URL: parse failed")
            return False

        if not parsed.scheme or not parsed.netloc:
            return False

        if allowed_schemes and parsed.scheme.lower() not in allowed_schemes:
            return False

        try:
            if ":" in parsed.netloc:
                host_part = parsed.netloc.rsplit(":", 1)[0]
            else:
                host_part = parsed.netloc

            if host_part.startswith("[") and host_part.endswith("]"):
                ipaddress.ip_address(host_part[1:-1])
            else:
                if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", host_part):
                    return False
        except ValueError:
            pass

        return True

    def require_valid_url(
        self,
        url: str,
        allowed_schemes: Optional[set[str]] = None,
    ) -> None:
        if not self.validate_url(url, allowed_schemes):
            raise ValidationError(f"Invalid URL: {url}")

    def validate_ip_address(self, ip: str, allow_private: bool = True) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
            if not allow_private and (addr.is_private or addr.is_loopback or addr.is_link_local):
                return False
            return True
        except ValueError:
            return False

    def validate_port(self, port: int) -> bool:
        return 1 <= port <= 65535

    def sanitize_sql(self, value: str) -> str:
        if not value:
            return ""

        sanitized = str(value)

        for keyword in self.SQL_KEYWORDS:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            sanitized = pattern.sub("", sanitized)

        sanitized = sanitized.replace("'", "''")
        sanitized = sanitized.replace('"', '""')
        sanitized = sanitized.replace("\\", "\\\\")
        sanitized = sanitized.replace(";", "")
        sanitized = sanitized.replace("--", "")

        return sanitized

    def sanitize_command(self, value: str) -> str:
        if not value:
            return ""

        sanitized = str(value)

        for dangerous in self.SHELL_DANGEROUS:
            sanitized = sanitized.replace(dangerous, "")

        control_chars = "".join(chr(c) for c in range(32) if chr(c) not in "\t ")
        for char in control_chars:
            sanitized = sanitized.replace(char, "")

        return sanitized

    def sanitize_path(self, path: str, base_dir: Optional[Path] = None) -> Path:
        if not path:
            raise ValidationError("Empty path provided")

        path_str = str(path)

        path_str = path_str.replace("..", "")
        path_str = path_str.replace("~", "")
        path_str = re.sub(r"[<>|\"?*]", "", path_str)

        cleaned = Path(path_str).resolve()

        if base_dir:
            base_resolved = base_dir.resolve()
            try:
                cleaned.relative_to(base_resolved)
            except ValueError:
                raise ValidationError(f"Path traversal attempt detected: {path}")

        return cleaned

    def sanitize_filename(self, filename: str) -> str:
        if not filename:
            return ""

        filename = str(filename)

        filename = filename.replace("..", "")
        filename = filename.replace("/", "")
        filename = filename.replace("\\", "")
        filename = re.sub(r'[<>|:"?*]', "", filename)
        filename = filename.strip()

        if not filename:
            raise ValidationError("Invalid filename")

        return filename

    def validate_string(
        self,
        value: Any,
        min_length: int = 0,
        max_length: int = 1024,
        allow_empty: bool = False,
        allowed_chars: Optional[set[str]] = None,
        forbidden_chars: Optional[set[str]] = None,
    ) -> bool:
        if not isinstance(value, str):
            return False

        if not allow_empty and len(value.strip()) == 0:
            return False

        if len(value) < min_length or len(value) > max_length:
            return False

        if allowed_chars:
            for char in value:
                if char not in allowed_chars:
                    return False

        if forbidden_chars:
            for char in value:
                if char in forbidden_chars:
                    return False

        return True

    def validate_json_payload(
        self,
        payload: dict[str, Any],
        max_depth: int = 5,
        max_size_bytes: int = 1048576,
    ) -> bool:
        import json

        try:
            serialized = json.dumps(payload)
            if len(serialized) > max_size_bytes:
                return False
        except (TypeError, ValueError):
            return False

        def _check_depth(obj: Any, current_depth: int) -> bool:
            if current_depth > max_depth:
                return False

            if isinstance(obj, dict):
                for key, value in obj.items():
                    if not isinstance(key, str):
                        return False
                    if len(key) > 256:
                        return False
                    if not _check_depth(value, current_depth + 1):
                        return False
            elif isinstance(obj, list):
                for item in obj:
                    if not _check_depth(item, current_depth + 1):
                        return False
            elif isinstance(obj, (str, int, float, bool, type(None))):
                if isinstance(obj, str) and len(obj) > 65536:
                    return False
            else:
                return False

            return True

        return _check_depth(payload, 0)

    def safe_subprocess_args(self, args: list[str]) -> list[str]:
        return [self.sanitize_command(arg) for arg in args]
