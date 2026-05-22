from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from loguru import logger

from rover_swarm.exceptions import VectorDbConnectionError, VectorDbError
from rover_swarm.vector_db.base import VectorDatabase, VectorDbConfig

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    HAS_CHROMADB = True
except ImportError:  # pragma: no cover
    HAS_CHROMADB = False


class ChromaDb(VectorDatabase):
    def __init__(self, config: VectorDbConfig | None = None) -> None:
        self.config = config or VectorDbConfig()
        self._client: chromadb.ClientAPI | None = None

    async def connect(self) -> None:
        if not HAS_CHROMADB:
            raise VectorDbConnectionError("chromadb package is not installed")
        try:

            def _connect() -> chromadb.ClientAPI:
                client = chromadb.HttpClient(
                    host=self.config.host,
                    port=self.config.port,
                    settings=ChromaSettings(
                        allow_reset=True,
                        anonymized_telemetry=False,
                    ),
                )
                client.heartbeat()
                return client

            self._client = await asyncio.to_thread(_connect)
            logger.info(
                "Connected to ChromaDB",
                host=self.config.host,
                port=self.config.port,
            )
        except Exception as e:
            raise VectorDbConnectionError(
                f"Failed to connect to ChromaDB at {self.config.host}:{self.config.port}: {e}"
            ) from e

    async def disconnect(self) -> None:
        self._client = None
        logger.info("Disconnected from ChromaDB")

    async def create_collection(self) -> None:
        if not self._client:
            raise VectorDbError("Not connected to ChromaDB")

        def _create() -> None:
            self._client.get_or_create_collection(
                name=self.config.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

        await asyncio.to_thread(_create)
        logger.info("Created ChromaDB collection", collection=self.config.collection_name)

    async def delete_collection(self) -> None:
        if not self._client:
            raise VectorDbError("Not connected to ChromaDB")

        def _delete() -> None:
            self._client.delete_collection(name=self.config.collection_name)

        await asyncio.to_thread(_delete)
        logger.info("Deleted ChromaDB collection", collection=self.config.collection_name)

    async def insert(
        self,
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        if not self._client:
            raise VectorDbError("Not connected to ChromaDB")

        ids = [str(uuid4()) for _ in vectors]
        metadatas = metadata or [{}] * len(vectors)

        def _insert() -> None:
            collection = self._client.get_or_create_collection(
                name=self.config.collection_name,
            )
            collection.add(
                embeddings=vectors,
                metadatas=metadatas,
                ids=ids,
            )

        await asyncio.to_thread(_insert)
        logger.info("Inserted vectors into ChromaDB", count=len(vectors))
        return ids

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        if not self._client:
            raise VectorDbError("Not connected to ChromaDB")

        def _search() -> dict[str, Any]:
            collection = self._client.get_or_create_collection(
                name=self.config.collection_name,
            )
            return collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                include=["metadatas", "distances"],
            )

        results = await asyncio.to_thread(_search)
        output: list[dict[str, Any]] = []
        for i in range(len(results["ids"][0])):
            output.append(
                {
                    "id": results["ids"][0][i],
                    "score": (
                        1.0 - results["distances"][0][i]
                        if results.get("distances")
                        else 0.0
                    ),
                    "metadata": (
                        results["metadatas"][0][i]
                        if results.get("metadatas")
                        else {}
                    ),
                }
            )
        return output

    async def delete(self, ids: list[str]) -> None:
        if not self._client:
            raise VectorDbError("Not connected to ChromaDB")

        def _delete() -> None:
            collection = self._client.get_collection(
                name=self.config.collection_name,
            )
            collection.delete(ids=ids)

        await asyncio.to_thread(_delete)
        logger.info("Deleted vectors from ChromaDB", count=len(ids))

    async def health(self) -> dict[str, Any]:
        if not self._client:
            return {"status": "unhealthy", "backend": "chroma", "error": "not connected"}
        try:

            def _hb() -> int:
                return self._client.heartbeat()

            await asyncio.to_thread(_hb)
            return {"status": "healthy", "backend": "chroma"}
        except Exception as e:
            return {"status": "unhealthy", "backend": "chroma", "error": str(e)}

    async def stats(self) -> dict[str, Any]:
        if not self._client:
            raise VectorDbError("Not connected to ChromaDB")

        def _count() -> int:
            return self._client.get_or_create_collection(
                name=self.config.collection_name,
            ).count()

        count = await asyncio.to_thread(_count)
        return {
            "backend": "chroma",
            "collection": self.config.collection_name,
            "count": count,
            "dimension": self.config.embedding_dim,
        }
