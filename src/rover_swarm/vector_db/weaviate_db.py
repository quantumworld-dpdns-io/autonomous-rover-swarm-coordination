from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from loguru import logger

from rover_swarm.exceptions import VectorDbConnectionError, VectorDbError
from rover_swarm.vector_db.base import VectorDatabase, VectorDbConfig

try:
    import weaviate
    from weaviate.classes.config import Configure, Property
    from weaviate.classes.config import DataType as WDataType
    from weaviate.classes.data import DataObject

    HAS_WEAVIATE = True
except ImportError:  # pragma: no cover
    HAS_WEAVIATE = False


class WeaviateDb(VectorDatabase):
    def __init__(self, config: VectorDbConfig | None = None) -> None:
        self.config = config or VectorDbConfig()
        self._client: weaviate.Client | None = None

    async def connect(self) -> None:
        if not HAS_WEAVIATE:
            raise VectorDbConnectionError("weaviate-client package is not installed")
        try:

            def _connect() -> weaviate.Client:
                client = weaviate.connect_to_local(
                    host=self.config.host,
                    port=self.config.port,
                )
                return client

            self._client = await asyncio.to_thread(_connect)
            logger.info(
                "Connected to Weaviate",
                host=self.config.host,
                port=self.config.port,
            )
        except Exception as e:
            raise VectorDbConnectionError(
                f"Failed to connect to Weaviate at {self.config.host}:{self.config.port}: {e}"
            ) from e

    async def disconnect(self) -> None:
        if self._client:

            def _close() -> None:
                self._client.close()

            await asyncio.to_thread(_close)
            self._client = None
            logger.info("Disconnected from Weaviate")

    async def create_collection(self) -> None:
        if not self._client:
            raise VectorDbError("Not connected to Weaviate")

        def _create() -> None:
            if self._client.collections.exists(self.config.collection_name):
                return
            self._client.collections.create(
                name=self.config.collection_name,
                properties=[
                    Property(name="metadata", data_type=WDataType.TEXT),
                ],
                vectorizer_config=Configure.Vectorizer.none(),
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric="cosine",
                ),
            )

        await asyncio.to_thread(_create)
        logger.info("Created Weaviate collection", collection=self.config.collection_name)

    async def delete_collection(self) -> None:
        if not self._client:
            raise VectorDbError("Not connected to Weaviate")

        def _delete() -> None:
            if self._client.collections.exists(self.config.collection_name):
                self._client.collections.delete(self.config.collection_name)

        await asyncio.to_thread(_delete)
        logger.info("Deleted Weaviate collection", collection=self.config.collection_name)

    async def insert(
        self,
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        if not self._client:
            raise VectorDbError("Not connected to Weaviate")

        ids = [str(uuid4()) for _ in vectors]
        metadatas = metadata or [{}] * len(vectors)
        import orjson

        objects = [
            DataObject(
                uuid=ids[i],
                vector=vectors[i],
                properties={
                    "metadata": orjson.dumps(metadatas[i]).decode(),
                },
            )
            for i in range(len(vectors))
        ]

        def _insert() -> None:
            collection = self._client.collections.get(self.config.collection_name)
            collection.data.insert_many(objects)

        await asyncio.to_thread(_insert)
        logger.info("Inserted vectors into Weaviate", count=len(vectors))
        return ids

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        if not self._client:
            raise VectorDbError("Not connected to Weaviate")
        import orjson

        def _search() -> list[dict[str, Any]]:
            collection = self._client.collections.get(self.config.collection_name)
            results = collection.query.near_vector(
                near_vector=query_vector,
                limit=top_k,
                return_metadata=["distance"],
            )
            output: list[dict[str, Any]] = []
            for obj in results.objects:
                metadata_raw = obj.properties.get("metadata", "{}")
                if isinstance(metadata_raw, str):
                    metadata = orjson.loads(metadata_raw)
                else:
                    metadata = metadata_raw or {}
                output.append(
                    {
                        "id": str(obj.uuid),
                        "score": (
                            1.0 - obj.metadata.distance
                            if obj.metadata and obj.metadata.distance is not None
                            else 0.0
                        ),
                        "metadata": metadata,
                    }
                )
            return output

        return await asyncio.to_thread(_search)

    async def delete(self, ids: list[str]) -> None:
        if not self._client:
            raise VectorDbError("Not connected to Weaviate")

        def _delete() -> None:
            collection = self._client.collections.get(self.config.collection_name)
            for obj_id in ids:
                collection.data.delete_by_id(obj_id)

        await asyncio.to_thread(_delete)
        logger.info("Deleted vectors from Weaviate", count=len(ids))

    async def health(self) -> dict[str, Any]:
        if not self._client:
            return {"status": "unhealthy", "backend": "weaviate", "error": "not connected"}
        try:

            def _check() -> bool:
                return self._client.is_ready()

            ready = await asyncio.to_thread(_check)
            if ready:
                return {"status": "healthy", "backend": "weaviate"}
            return {"status": "unhealthy", "backend": "weaviate", "error": "not ready"}
        except Exception as e:
            return {"status": "unhealthy", "backend": "weaviate", "error": str(e)}

    async def stats(self) -> dict[str, Any]:
        if not self._client:
            raise VectorDbError("Not connected to Weaviate")

        def _collection_info() -> dict[str, Any]:
            collection = self._client.collections.get(self.config.collection_name)
            aggregate = collection.aggregate.over_all(total_count=True)
            return {
                "count": aggregate.total_count,
            }

        info = await asyncio.to_thread(_collection_info)
        return {
            "backend": "weaviate",
            "collection": self.config.collection_name,
            "count": info["count"],
            "dimension": self.config.embedding_dim,
        }
