from __future__ import annotations

from review_mcp.config import Settings
from review_mcp.repositories.base import ReviewRepository
from review_mcp.repositories.csv_repository import CsvReviewRepository


def create_repository(settings: Settings) -> ReviewRepository:
    if settings.data_backend == "csv":
        return CsvReviewRepository(settings.resolve_data_glob())

    if not settings.database_url:
        raise ValueError("DATABASE_URL is required when DATA_BACKEND=rds")

    from review_mcp.repositories.rds_repository import RdsReviewRepository

    return RdsReviewRepository(
        database_url=settings.database_url,
        table_name=settings.review_table,
    )
