from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from loguru import logger

from rover_swarm.exceptions import VectorDbConnectionError, VectorDbError
from rover_swarm.vector_db.base import VectorDatabase, VectorDbConfig

try:
    from qdrant_client import QdrantClient as _QdrantClient
    from qdrant_client.http import models

    HAS_QDRANT = True
except ImportError:  # pragma: no cover
    HAS_QDRANT = False


class QdrantDb(VectorDatabase):
    def __init__(self, config: VectorDbConfig | None = None) -> None:
        self.config = config or VectorDbConfig()
        self._client: _QdrantClient | None = None

    async def connect(self) -> None:
        if not HAS_QDRANT:
            raise VectorDbConnectionError("qdrant-client package is not installed")
        try:

            def _connect() -> _QdrantClient:
                client = _QdrantClient(
                    host=self.config.host,
                    port=self.config.port,
                )
                return client

            self._client = await asyncio.to_thread(_connect)
            logger.info(
                "Connected to Qdrant",
                host=self.config.host,
                port=self.config.port,
            )
        except Exception as e:
            raise VectorDbConnectionError(
                f"Failed to connect to Qdrant at {self.config.host}:{self.config.port}: {e}"
            ) from e

    async def disconnect(self) -> None:
        self._client = None
        logger.info("Disconnected from Qdrant")

    async def create_collection(self) -> None:
        if not self._client:
            raise VectorDbError("Not connected to Qdrant")

        def _create() -> None:
            self._client.recreate_collection(
                collection_name=self.config.collection_name,
                vectors_config=models.VectorParams(
                    size=self.config.embedding_dim,
                    distance=models.Distance.COSINE,
                ),
            )

        await asyncio.to_thread(_create)
        logger.info("Created Qdrant collection", collection=self.config.collection_name)

    async def delete_collection(self) -> None:
        if not self._client:
            raise VectorDbError("Not connected to Qdrant")

        def _delete() -> None:
            self._client.delete_collection(
                collection_name=self.config.collection_name,
            )

        await asyncio.to_thread(_delete)
        logger.info("Deleted Qdrant collection", collection=self.config.collection_name)

    async def insert(
        self,
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        if not self._client:
            raise VectorDbError("Not connected to Qdrant")

        ids = [str(uuid4()) for _ in vectors]
        metadatas = metadata or [{}] * len(vectors)
        points = [
            models.PointStruct(
                id=ids[i],
                vector=vectors[i],
                payload=metadatas[i],
            )
            for i in range(len(vectors))
        ]

        def _upsert() -> None:
            self._client.upsert(
                collection_name=self.config.collection_name,
                points=points,
            )

        await asyncio.to_thread(_upsert)
        logger.info("Inserted vectors into Qdrant", count=len(vectors))
        return ids

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        if not self._client:
            raise VectorDbError("Not connected to Qdrant")

        def _search() -> list[dict[str, Any]]:
            results = self._client.search(
                collection_name=self.config.collection_name,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True,
            )
            output: list[dict[str, Any]] = []
            for point in results:
                output.append(
                    {
                        "id": str(point.id),
                        "score": point.score,
                        "metadata": point.payload or {},
                    }
                )
            return output

        return await asyncio.to_thread(_search)

    async def delete(self, ids: list[str]) -> None:
        if not self._client:
            raise VectorDbError("Not connected to Qdrant")

        def _delete() -> None:
            self._client.delete(
                collection_name=self.config.collection_name,
                points_selector=models.PointIdsList(
                    points=ids,
                ),
            )

        await asyncio.to_thread(_delete)
        logger.info("Deleted vectors from Qdrant", count=len(ids))

    async def health(self) -> dict[str, Any]:
        if not self._client:
            return {"status": "unhealthy", "backend": "qdrant", "error": "not connected"}
        try:

            def _check() -> bool:
                return self._client.health_check()

            await asyncio.to_thread(_check)
            return {"status": "healthy", "backend": "qdrant"}
        except Exception as e:
            return {"status": "unhealthy", "backend": "qdrant", "error": str(e)}

    async def stats(self) -> dict[str, Any]:
        if not self._client:
            raise VectorDbError("Not connected to Qdrant")

        def _info() -> dict[str, Any]:
            collection_info = self._client.get_collection(
                collection_name=self.config.collection_name,
            )
            return {
                "count": collection_info.points_count,
                "status": collection_info.status,
            }

        info = await asyncio.to_thread(_info)
        return {
            "backend": "qdrant",
            "collection": self.config.collection_name,
            "count": info["count"],
            "dimension": self.config.embedding_dim,
            "status": info["status"],
        }
