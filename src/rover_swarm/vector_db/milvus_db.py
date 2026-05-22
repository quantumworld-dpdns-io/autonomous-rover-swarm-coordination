from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from loguru import logger

from rover_swarm.exceptions import VectorDbConnectionError, VectorDbError
from rover_swarm.vector_db.base import VectorDatabase, VectorDbConfig

try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )

    HAS_MILVUS = True
except ImportError:  # pragma: no cover
    HAS_MILVUS = False


class MilvusDb(VectorDatabase):
    def __init__(self, config: VectorDbConfig | None = None) -> None:
        self.config = config or VectorDbConfig()
        self._connected = False

    async def connect(self) -> None:
        if not HAS_MILVUS:
            raise VectorDbConnectionError("pymilvus package is not installed")
        try:

            def _connect() -> None:
                connections.connect(
                    host=self.config.host,
                    port=self.config.port,
                )

            await asyncio.to_thread(_connect)
            self._connected = True
            logger.info(
                "Connected to Milvus",
                host=self.config.host,
                port=self.config.port,
            )
        except Exception as e:
            raise VectorDbConnectionError(
                f"Failed to connect to Milvus at {self.config.host}:{self.config.port}: {e}"
            ) from e

    async def disconnect(self) -> None:
        if self._connected:

            def _disconnect() -> None:
                connections.disconnect("default")

            await asyncio.to_thread(_disconnect)
            self._connected = False
            logger.info("Disconnected from Milvus")

    async def create_collection(self) -> None:
        if not self._connected:
            raise VectorDbError("Not connected to Milvus")

        def _create() -> None:
            if utility.has_collection(self.config.collection_name):
                return

            fields = [
                FieldSchema(
                    name="id",
                    dtype=DataType.VARCHAR,
                    max_length=36,
                    is_primary=True,
                ),
                FieldSchema(
                    name="vector",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=self.config.embedding_dim,
                ),
                FieldSchema(name="metadata", dtype=DataType.JSON),
            ]
            schema = CollectionSchema(fields)
            collection = Collection(
                name=self.config.collection_name,
                schema=schema,
            )
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024},
            }
            collection.create_index(
                field_name="vector",
                index_params=index_params,
            )
            collection.load()

        await asyncio.to_thread(_create)
        logger.info("Created Milvus collection", collection=self.config.collection_name)

    async def delete_collection(self) -> None:
        if not self._connected:
            raise VectorDbError("Not connected to Milvus")

        def _drop() -> None:
            if utility.has_collection(self.config.collection_name):
                utility.drop_collection(self.config.collection_name)

        await asyncio.to_thread(_drop)
        logger.info("Deleted Milvus collection", collection=self.config.collection_name)

    async def insert(
        self,
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        if not self._connected:
            raise VectorDbError("Not connected to Milvus")

        ids = [str(uuid4()) for _ in vectors]
        metadatas = metadata or [{}] * len(vectors)

        def _insert() -> None:
            collection = Collection(self.config.collection_name)
            collection.load()
            entities = [
                [ids[i] for i in range(len(vectors))],
                vectors,
                metadatas,
            ]
            collection.insert(entities)

        await asyncio.to_thread(_insert)
        logger.info("Inserted vectors into Milvus", count=len(vectors))
        return ids

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        if not self._connected:
            raise VectorDbError("Not connected to Milvus")

        def _search() -> list[dict[str, Any]]:
            collection = Collection(self.config.collection_name)
            collection.load()
            search_params = {
                "metric_type": "COSINE",
                "params": {"nprobe": 10},
            }
            results = collection.search(
                data=[query_vector],
                anns_field="vector",
                param=search_params,
                limit=top_k,
                output_fields=["id", "metadata"],
            )
            output: list[dict[str, Any]] = []
            for hits in results:
                for hit in hits:
                    output.append(
                        {
                            "id": hit.entity.get("id"),
                            "score": hit.score,
                            "metadata": hit.entity.get("metadata", {}),
                        }
                    )
            return output

        return await asyncio.to_thread(_search)

    async def delete(self, ids: list[str]) -> None:
        if not self._connected:
            raise VectorDbError("Not connected to Milvus")

        expr = f'id in [{",".join(repr(i) for i in ids)}]'

        def _delete() -> None:
            collection = Collection(self.config.collection_name)
            collection.load()
            collection.delete(expr)

        await asyncio.to_thread(_delete)
        logger.info("Deleted vectors from Milvus", count=len(ids))

    async def health(self) -> dict[str, Any]:
        try:

            def _check() -> bool:
                return utility.ping()

            await asyncio.to_thread(_check)
            return {"status": "healthy", "backend": "milvus"}
        except Exception as e:
            return {"status": "unhealthy", "backend": "milvus", "error": str(e)}

    async def stats(self) -> dict[str, Any]:
        if not self._connected:
            raise VectorDbError("Not connected to Milvus")

        def _stats() -> dict[str, Any]:
            if not utility.has_collection(self.config.collection_name):
                return {"count": 0}
            collection = Collection(self.config.collection_name)
            collection.load()
            count = collection.num_entities
            return {"count": count}

        info = await asyncio.to_thread(_stats)
        return {
            "backend": "milvus",
            "collection": self.config.collection_name,
            "count": info["count"],
            "dimension": self.config.embedding_dim,
        }
