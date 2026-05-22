from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class VectorDbConfig(BaseModel):
    host: str = Field(default="localhost")
    port: int = Field(default=8000, ge=1, le=65535)
    collection_name: str = Field(default="rover_swarm")
    embedding_dim: int = Field(default=384, ge=1)


class VectorDatabase(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def create_collection(self) -> None: ...

    @abstractmethod
    async def delete_collection(self) -> None: ...

    @abstractmethod
    async def insert(
        self,
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> list[str]: ...

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def delete(self, ids: list[str]) -> None: ...

    @abstractmethod
    async def health(self) -> dict[str, Any]: ...

    @abstractmethod
    async def stats(self) -> dict[str, Any]: ...
