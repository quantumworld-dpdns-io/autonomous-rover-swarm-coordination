from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel

from rover_swarm.api.dependencies import get_settings
from rover_swarm.config import Settings

router = APIRouter(prefix="/api/v1/data", tags=["data"])


class SqlQueryRequest(BaseModel):
    query: str
    params: list[Any] | None = None


class SqlQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int


class ExportRequest(BaseModel):
    query: str
    output_path: str | None = None
    partition_by: list[str] | None = None


class ExportResponse(BaseModel):
    path: str
    row_count: int
    file_size_bytes: int | None = None


@router.get("/query", response_model=SqlQueryResponse)
async def sql_query(
    query: Annotated[str, Query(min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SqlQueryResponse:
    try:
        import duckdb

        conn = duckdb.connect(settings.data.duckdb_path)
        result = conn.execute(query).fetchdf()
        conn.close()
        columns = list(result.columns)
        rows = [list(row) for row in result.itertuples(index=False)]
        logger.debug("SQL query returned {} rows from {} columns", len(rows), len(columns))
        return SqlQueryResponse(columns=columns, rows=rows, row_count=len(rows))
    except ImportError:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="DuckDB is not installed")
    except Exception as e:
        logger.error("SQL query failed: {}", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/export", response_model=ExportResponse)
async def export_data(
    body: ExportRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExportResponse:
    import os

    output_path = body.output_path or f"/tmp/export-{hash(body.query)}.parquet"

    try:
        import duckdb
        import pyarrow.parquet as pq

        conn = duckdb.connect(settings.data.duckdb_path)
        df = conn.execute(body.query).fetchdf()
        conn.close()

        df.to_parquet(output_path, index=False)
        file_size = os.path.getsize(output_path)

        logger.info("Exported {} rows to {}", len(df), output_path)
        return ExportResponse(
            path=output_path,
            row_count=len(df),
            file_size_bytes=file_size,
        )
    except ImportError:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="DuckDB or PyArrow is not installed")
    except Exception as e:
        logger.error("Export failed: {}", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
