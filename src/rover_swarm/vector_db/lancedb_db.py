from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from loguru import logger

from rover_swarm.exceptions import VectorDbConnectionError, VectorDbError
from rover_swarm.vector_db.base import VectorDatabase, VectorDbConfig

try:
    import lancedb
    import pyarrow as pa

    HAS_LANCEDB = True
except ImportError:  # pragma: no cover
    HAS_LANCEDB = False


class LanceDb(VectorDatabase):
    def __init__(self, config: VectorDbConfig | None = None) -> None:
        self.config = config or VectorDbConfig()
        self._db: lancedb.DBConnection | None = None
        self._uri: str = (
            f"file:///tmp/lancedb/{self.config.collection_name}"
        )

    async def connect(self) -> None:
        if not HAS_LANCEDB:
            raise VectorDbConnectionError("lancedb package is not installed")
        try:

            def _connect() -> lancedb.DBConnection:
                return lancedb.connect(self._uri)

            self._db = await asyncio.to_thread(_connect)
            logger.info("Connected to LanceDB", uri=self._uri)
        except Exception as e:
            raise VectorDbConnectionError(
                f"Failed to connect to LanceDB at {self._uri}: {e}"
            ) from e

    async def disconnect(self) -> None:
        self._db = None
        logger.info("Disconnected from LanceDB")

    async def create_collection(self) -> None:
        if not self._db:
            raise VectorDbError("Not connected to LanceDB")

        schema = pa.schema([
            pa.field("id", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.config.embedding_dim)),
            pa.field("metadata", pa.string()),
        ])

        def _create() -> None:
            if self.config.collection_name not in self._db.table_names():
                self._db.create_table(
                    self.config.collection_name,
                    schema=schema,
                )

        await asyncio.to_thread(_create)
        logger.info("Created LanceDB collection", collection=self.config.collection_name)

    async def delete_collection(self) -> None:
        if not self._db:
            raise VectorDbError("Not connected to LanceDB")

        def _drop() -> None:
            self._db.drop_table(self.config.collection_name)

        await asyncio.to_thread(_drop)
        logger.info("Deleted LanceDB collection", collection=self.config.collection_name)

    async def insert(
        self,
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        if not self._db:
            raise VectorDbError("Not connected to LanceDB")

        ids = [str(uuid4()) for _ in vectors]
        metadatas = metadata or [{}] * len(vectors)
        import orjson

        data = [
            {
                "id": ids[i],
                "vector": vectors[i],
                "metadata": orjson.dumps(metadatas[i]).decode(),
            }
            for i in range(len(vectors))
        ]

        def _insert() -> None:
            table = self._db.open_table(self.config.collection_name)
            table.add(data)

        await asyncio.to_thread(_insert)
        logger.info("Inserted vectors into LanceDB", count=len(vectors))
        return ids

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        if not self._db:
            raise VectorDbError("Not connected to LanceDB")

        def _search() -> list[dict[str, Any]]:
            table = self._db.open_table(self.config.collection_name)
            results = (
                table.search(query_vector)
                .limit(top_k)
                .to_list()
            )
            return results

        raw = await asyncio.to_thread(_search)
        import orjson

        output: list[dict[str, Any]] = []
        for row in raw:
            metadata = row.get("metadata", "{}")
            if isinstance(metadata, str):
                metadata = orjson.loads(metadata)
            output.append(
                {
                    "id": row.get("id", ""),
                    "score": row.get("_distance", 0.0),
                    "metadata": metadata,
                }
            )
        return output

    async def delete(self, ids: list[str]) -> None:
        if not self._db:
            raise VectorDbError("Not connected to LanceDB")

        def _delete() -> None:
            table = self._db.open_table(self.config.collection_name)
            table.delete(f'"id" IN ({",".join(repr(i) for i in ids)})')

        await asyncio.to_thread(_delete)
        logger.info("Deleted vectors from LanceDB", count=len(ids))

    async def health(self) -> dict[str, Any]:
        if not self._db:
            return {"status": "unhealthy", "backend": "lancedb", "error": "not connected"}
        try:

            def _check() -> list[str]:
                return self._db.table_names()

            await asyncio.to_thread(_check)
            return {"status": "healthy", "backend": "lancedb"}
        except Exception as e:
            return {"status": "unhealthy", "backend": "lancedb", "error": str(e)}

    async def stats(self) -> dict[str, Any]:
        if not self._db:
            raise VectorDbError("Not connected to LanceDB")

        def _count() -> int:
            table_names = self._db.table_names()
            if self.config.collection_name not in table_names:
                return 0
            table = self._db.open_table(self.config.collection_name)
            return table.count_rows()

        count = await asyncio.to_thread(_count)
        return {
            "backend": "lancedb",
            "collection": self.config.collection_name,
            "count": count,
            "dimension": self.config.embedding_dim,
        }
