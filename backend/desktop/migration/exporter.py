from __future__ import annotations

import heapq
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    AnalysisJob,
    Artifact,
    JobProduct,
    ProductSnapshot,
    ProviderConfiguration,
    ProviderModelValidation,
)

# Parents precede children. In particular, provider configurations must be copied
# before model validations because provider_slug is a foreign key.
TABLE_ORDER = (
    "analysis_jobs",
    "product_snapshots",
    "job_products",
    "artifacts",
    "provider_configurations",
    "provider_model_validations",
)

TABLES = {
    table.name: table
    for table in (
        AnalysisJob.__table__,
        ProductSnapshot.__table__,
        JobProduct.__table__,
        Artifact.__table__,
        ProviderConfiguration.__table__,
        ProviderModelValidation.__table__,
    )
}


def install_source_read_only_guard(connection: Any) -> None:
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )


async def read_table(session: AsyncSession, table_name: str) -> list[dict[str, Any]]:
    result = await session.execute(select(TABLES[table_name]))
    rows = [dict(row) for row in result.mappings()]
    if table_name == "analysis_jobs":
        return order_analysis_jobs(rows)
    return rows


def order_analysis_jobs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed: dict[Any, tuple[int, dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        if row["id"] in indexed:
            raise ValueError("duplicate analysis job id")
        indexed[row["id"]] = (index, row)

    children: dict[Any, list[Any]] = defaultdict(list)
    indegree = {job_id: 0 for job_id in indexed}
    for job_id, (_, row) in indexed.items():
        parent = row["retry_of_id"]
        if parent is None:
            continue
        if parent not in indexed:
            raise ValueError(f"missing retry parent: {parent}")
        children[parent].append(job_id)
        indegree[job_id] = 1

    ready = [(index, job_id) for job_id, (index, _) in indexed.items() if not indegree[job_id]]
    heapq.heapify(ready)
    ordered: list[dict[str, Any]] = []
    while ready:
        _, job_id = heapq.heappop(ready)
        ordered.append(indexed[job_id][1])
        for child in children[job_id]:
            indegree[child] -= 1
            if not indegree[child]:
                heapq.heappush(ready, (indexed[child][0], child))
    if len(ordered) != len(rows):
        raise ValueError("analysis job retry relationship contains a cycle")
    return ordered


__all__ = [
    "TABLES",
    "TABLE_ORDER",
    "install_source_read_only_guard",
    "order_analysis_jobs",
    "read_table",
]
