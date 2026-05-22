from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class MqttConfig(BaseSettings):
    broker: str = Field(default="localhost", description="MQTT broker hostname")
    port: int = Field(default=1883, ge=1, le=65535)
    tls_enabled: bool = Field(default=False)
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)
    client_id: str = Field(default="rover-swarm")
    keepalive: int = Field(default=60, ge=10)


class GrpcConfig(BaseSettings):
    port: int = Field(default=50051, ge=1, le=65535)
    tls_enabled: bool = Field(default=False)
    max_message_size: int = Field(default=4 * 1024 * 1024, ge=1024)


class ChromaConfig(BaseSettings):
    host: str = Field(default="localhost")
    port: int = Field(default=8000, ge=1, le=65535)


class MilvusConfig(BaseSettings):
    host: str = Field(default="localhost")
    port: int = Field(default=19530, ge=1, le=65535)


class QdrantConfig(BaseSettings):
    host: str = Field(default="localhost")
    port: int = Field(default=6333, ge=1, le=65535)


class WeaviateConfig(BaseSettings):
    host: str = Field(default="localhost")
    port: int = Field(default=8080, ge=1, le=65535)


class VectorDbConfig(BaseSettings):
    chroma: ChromaConfig = ChromaConfig()
    milvus: MilvusConfig = MilvusConfig()
    qdrant: QdrantConfig = QdrantConfig()
    weaviate: WeaviateConfig = WeaviateConfig()

    active_backend: str = Field(default="chroma", description="Primary vector DB backend")


class OllamaConfig(BaseSettings):
    host: str = Field(default="localhost")
    port: int = Field(default=11434, ge=1, le=65535)


class VllmConfig(BaseSettings):
    host: str = Field(default="localhost")
    port: int = Field(default=8001, ge=1, le=65535)


class LlamacppConfig(BaseSettings):
    model_path: str = Field(default="/app/models/rover-7b.gguf")


class AiConfig(BaseSettings):
    ollama: OllamaConfig = OllamaConfig()
    vllm: VllmConfig = VllmConfig()
    llamacpp: LlamacppConfig = LlamacppConfig()
    sglang_host: str = Field(default="localhost")
    sglang_port: int = Field(default=30000, ge=1, le=65535)
    active_engine: str = Field(default="ollama", description="Primary AI inference engine")


class DataConfig(BaseSettings):
    duckdb_path: str = Field(default="/app/data/telemetry.duckdb")
    iceberg_warehouse: str = Field(default="/app/data/iceberg")
    iceberg_catalog_uri: str = Field(default="http://localhost:8181")


class OtelConfig(BaseSettings):
    service_name: str = Field(default="rover-swarm")
    exporter_otlp_endpoint: str = Field(default="http://localhost:4317")


class PrometheusConfig(BaseSettings):
    port: int = Field(default=9090, ge=1, le=65535)


class ApiConfig(BaseSettings):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080, ge=1, le=65535)
    cors_origins: list[str] = Field(default=["*"])
    jwt_secret: str = Field(default="change-me-in-production", min_length=16)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30, ge=1)


class TlsConfig(BaseSettings):
    enabled: bool = Field(default=True)
    cert_path: str = Field(default="/app/certs/rover.crt")
    key_path: str = Field(default="/app/certs/rover.key")
    ca_path: str = Field(default="/app/certs/ca.crt")


class RateLimitConfig(BaseSettings):
    requests_per_minute: int = Field(default=60, ge=1)


class SecurityConfig(BaseSettings):
    tls: TlsConfig = TlsConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ROVER_SWARM__",
        env_nested_delimiter="__",
        case_sensitive=False,
        env_file=".env",
        secrets_dir="/run/secrets",
        extra="ignore",
    )

    node_id: str = Field(default="rover-01")
    mission_id: str = Field(default="demo-mission-001")
    log_level: LogLevel = Field(default=LogLevel.INFO)

    mqtt: MqttConfig = MqttConfig()
    grpc: GrpcConfig = GrpcConfig()
    vector_db: VectorDbConfig = VectorDbConfig()
    ai: AiConfig = AiConfig()
    data: DataConfig = DataConfig()
    otel: OtelConfig = OtelConfig()
    prometheus: PrometheusConfig = PrometheusConfig()
    api: ApiConfig = ApiConfig()
    security: SecurityConfig = SecurityConfig()

    @field_validator("node_id")
    @classmethod
    def validate_node_id(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Invalid node_id: {v}")
        return v


settings = Settings()
