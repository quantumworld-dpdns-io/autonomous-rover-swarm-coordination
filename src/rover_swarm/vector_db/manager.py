from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from rover_swarm.exceptions import VectorDbError
from rover_swarm.vector_db.base import VectorDatabase


class ManagerConfig(BaseModel):
    active_backend: str = Field(default="chroma")
    fallback_enabled: bool = Field(default=True)


class VectorDbManager:
    def __init__(
        self,
        backends: dict[str, VectorDatabase],
        config: ManagerConfig | None = None,
    ) -> None:
        self.backends = backends
        self.config = config or ManagerConfig()

    async def search_all(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> dict[str, list[dict[str, Any]]]:
        results: dict[str, list[dict[str, Any]]] = {}
        for name, backend in self.backends.items():
            try:
                results[name] = await backend.search(query_vector, top_k=top_k)
            except Exception as e:
                logger.error("Search failed on backend", backend=name, error=str(e))
                results[name] = []
        return results

    async def route_search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        backend_name: str | None = None,
    ) -> list[dict[str, Any]]:
        target = backend_name or self.config.active_backend
        backend = self.backends.get(target)
        if not backend:
            raise VectorDbError(f"Backend '{target}' is not registered")

        try:
            return await backend.search(query_vector, top_k=top_k)
        except Exception as e:
            if self.config.fallback_enabled:
                logger.warning(
                    "Primary backend failed, falling back",
                    backend=target,
                    error=str(e),
                )
                for name, fallback in self.backends.items():
                    if name == target:
                        continue
                    try:
                        return await fallback.search(query_vector, top_k=top_k)
                    except Exception as fallback_e:
                        logger.error(
                            "Fallback backend also failed",
                            backend=name,
                            error=str(fallback_e),
                        )
            raise VectorDbError(
                f"Search failed on backend '{target}': {e}"
            ) from e

    async def health_all(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for name, backend in self.backends.items():
            try:
                results[name] = await backend.health()
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
        return results
