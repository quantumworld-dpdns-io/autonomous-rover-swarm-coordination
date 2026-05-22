from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from rover_swarm.api.dependencies import get_vector_db
from rover_swarm.vector_db.manager import VectorDbManager

router = APIRouter(prefix="/api/v1/search", tags=["search"])


class VectorSearchRequest(BaseModel):
    query_vector: list[float]
    top_k: int = 10
    backend: str | None = None


class HybridSearchRequest(BaseModel):
    query_vector: list[float]
    top_k: int = 10
    backends: list[str] | None = None


class SearchResult(BaseModel):
    id: str
    score: float
    metadata: dict[str, Any] | None = None


class VectorSearchResponse(BaseModel):
    backend: str
    results: list[SearchResult]


class HybridSearchResponse(BaseModel):
    results: dict[str, list[SearchResult]]


@router.post("/vector", response_model=VectorSearchResponse)
async def vector_search(
    body: VectorSearchRequest,
    db: Annotated[VectorDbManager, Depends(get_vector_db)],
) -> VectorSearchResponse:
    if not body.query_vector:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="query_vector is required"
        )
    if len(body.backends) == 0 and body.backend is not None:
        body.backend = body.backend or None

    try:
        raw = await db.route_search(
            query_vector=body.query_vector,
            top_k=body.top_k,
            backend_name=body.backend,
        )
        results = [
            SearchResult(
                id=r.get("id", ""),
                score=r.get("score", 0.0),
                metadata=r.get("metadata"),
            )
            for r in raw
        ]
        backend_used = body.backend or db.config.active_backend
        logger.debug("Vector search on {} returned {} results", backend_used, len(results))
        return VectorSearchResponse(backend=backend_used, results=results)
    except Exception as e:
        logger.error("Vector search failed: {}", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.post("/hybrid", response_model=HybridSearchResponse)
async def hybrid_search(
    body: HybridSearchRequest,
    db: Annotated[VectorDbManager, Depends(get_vector_db)],
) -> HybridSearchResponse:
    if not body.query_vector:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="query_vector is required")

    try:
        targets = body.backends or list(db.backends.keys())
        all_results: dict[str, list[SearchResult]] = {}

        for backend_name in targets:
            try:
                raw = await db.route_search(
                    query_vector=body.query_vector,
                    top_k=body.top_k,
                    backend_name=backend_name,
                )
                all_results[backend_name] = [
                    SearchResult(
                        id=r.get("id", ""),
                        score=r.get("score", 0.0),
                        metadata=r.get("metadata"),
                    )
                    for r in raw
                ]
            except Exception as e:
                logger.warning("Hybrid search backend {} failed: {}", backend_name, e)
                all_results[backend_name] = []

        logger.debug("Hybrid search across {} backends", len(targets))
        return HybridSearchResponse(results=all_results)
    except Exception as e:
        logger.error("Hybrid search failed: {}", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
