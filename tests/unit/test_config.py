from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from rover_swarm.config import (
    ApiConfig,
    LogLevel,
    MqttConfig,
    Settings,
)


class TestLogLevel:
    def test_values(self) -> None:
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"


class TestMqttConfig:
    def test_defaults(self) -> None:
        config = MqttConfig()
        assert config.broker == "localhost"
        assert config.port == 1883
        assert config.tls_enabled is False
        assert config.username is None
        assert config.password is None
        assert config.keepalive == 60

    def test_port_validation(self) -> None:
        with pytest.raises(ValidationError):
            MqttConfig(port=0)
        with pytest.raises(ValidationError):
            MqttConfig(port=65536)


class TestApiConfig:
    def test_defaults(self) -> None:
        config = ApiConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.cors_origins == ["*"]

    def test_jwt_secret_min_length(self) -> None:
        with pytest.raises(ValidationError):
            ApiConfig(jwt_secret="short")


class TestSettings:
    def test_defaults(self) -> None:
        settings = Settings()
        assert settings.node_id == "rover-01"
        assert settings.mission_id == "demo-mission-001"
        assert settings.log_level == LogLevel.INFO
        assert settings.mqtt.broker == "localhost"

    def test_env_override(self) -> None:
        env_vars = {
            "ROVER_SWARM__NODE_ID": "test-rover",
            "ROVER_SWARM__MISSION_ID": "test-mission",
            "ROVER_SWARM__LOG_LEVEL": "DEBUG",
            "ROVER_SWARM__MQTT__BROKER": "mqtt.test.local",
            "ROVER_SWARM__MQTT__PORT": "1883",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings()
            assert settings.node_id == "test-rover"
            assert settings.mission_id == "test-mission"
            assert settings.log_level == LogLevel.DEBUG
            assert settings.mqtt.broker == "mqtt.test.local"

    def test_node_id_validation(self) -> None:
        with pytest.raises(ValidationError):
            Settings(node_id="invalid node!")

    def test_valid_node_id_pass(self) -> None:
        settings = Settings(node_id="rover-42")
        assert settings.node_id == "rover-42"

    def test_nested_configs(self) -> None:
        settings = Settings()
        assert settings.api.port == 8080
        assert settings.prometheus.port == 9090
        assert settings.grpc.port == 50051
