from __future__ import annotations

import re
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    func,
    select,
)
from sqlalchemy.engine import Engine, RowMapping

from review_mcp.repositories.base import AnalysisBatch, SearchPage
from review_mcp.schemas import (
    DateRatingFilter,
    ReviewRecord,
    ReviewSite,
    SearchReviewsInput,
    SourceSummary,
)


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RdsReviewRepository:
    """RDS adapter.

    Only this file should need adjustment after the AWS/DB owner freezes the
    physical table and column names. Tool and service contracts stay unchanged.
    """

    def __init__(self, database_url: str, table_name: str) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(table_name):
            raise ValueError("REVIEW_TABLE is not a safe SQL identifier")
        connect_args: dict[str, int] = {}
        if database_url.startswith("mysql"):
            # PyMySQL-level timeouts so one slow query cannot hang the server.
            connect_args = {
                "connect_timeout": 5,
                "read_timeout": 15,
                "write_timeout": 15,
            }
        self._engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args=connect_args,
        )
        metadata = MetaData()
        self._table = Table(
            table_name,
            metadata,
            # Physical schema of review_pipeline.reviews (frozen 2026-08-12).
            Column("id", BigInteger, primary_key=True),
            Column("source_site", String(32), nullable=False),
            Column("review_date", Date, nullable=False),
            Column("rating", Float, nullable=False),
            Column("content", Text, nullable=False),
            Column("tokens", Text),
            Column("text_len", Integer),
            Column("token_count", Integer),
            Column("emoji_count", Integer),
            Column("collected_at", DateTime(timezone=True)),
        )

    @property
    def backend_name(self) -> str:
        return "rds"

    def _conditions(self, query: DateRatingFilter) -> list:
        table = self._table
        conditions = [table.c.source_site == query.site.value]
        if query.start_date:
            conditions.append(table.c.review_date >= query.start_date)
        if query.end_date:
            conditions.append(table.c.review_date <= query.end_date)
        if query.min_rating is not None:
            conditions.append(table.c.rating >= query.min_rating)
        if query.max_rating is not None:
            conditions.append(table.c.rating <= query.max_rating)
        return conditions

    @staticmethod
    def _to_record(row: RowMapping) -> ReviewRecord:
        raw_date = row["review_date"]
        if isinstance(raw_date, datetime):
            raw_date = raw_date.date()
        return ReviewRecord(
            id=str(row["id"]),
            site=ReviewSite(row["source_site"]),
            date=raw_date,
            rating=float(row["rating"]),
            content=row["content"],
            tokens=(row.get("tokens") or "").split(),
            text_len=row.get("text_len"),
            token_count=row.get("token_count"),
            emoji_count=row.get("emoji_count"),
            collected_at=row.get("collected_at"),
        )

    def list_sources(self) -> list[SourceSummary]:
        table = self._table
        statement = (
            select(
                table.c.source_site,
                func.count().label("row_count"),
                func.min(table.c.review_date).label("earliest_date"),
                func.max(table.c.review_date).label("latest_date"),
                func.max(table.c.collected_at).label("last_collected_at"),
            )
            .group_by(table.c.source_site)
            .order_by(table.c.source_site)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            SourceSummary(
                site=ReviewSite(row["source_site"]),
                row_count=row["row_count"],
                earliest_date=row["earliest_date"],
                latest_date=row["latest_date"],
                last_collected_at=row["last_collected_at"],
            )
            for row in rows
        ]

    def latest(self, site: ReviewSite, limit: int) -> list[ReviewRecord]:
        table = self._table
        statement = (
            select(table)
            .where(table.c.source_site == site.value)
            .order_by(table.c.review_date.desc(), table.c.id.desc())
            .limit(limit)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [self._to_record(row) for row in rows]

    def search(self, query: SearchReviewsInput) -> SearchPage:
        table = self._table
        conditions = self._conditions(query)
        if query.keyword:
            escaped = (
                query.keyword.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append(
                table.c.content.ilike(f"%{escaped}%", escape="\\")
            )

        count_statement = select(func.count()).select_from(table).where(and_(*conditions))
        data_statement = (
            select(table)
            .where(and_(*conditions))
            .order_by(table.c.review_date.desc(), table.c.id.desc())
            .limit(query.limit)
            .offset(query.offset)
        )
        with self._engine.connect() as connection:
            total = int(connection.scalar(count_statement) or 0)
            rows = connection.execute(data_statement).mappings().all()
        return SearchPage(
            items=[self._to_record(row) for row in rows],
            total=total,
        )

    def fetch_for_analysis(
        self, query: DateRatingFilter, max_rows: int
    ) -> AnalysisBatch:
        table = self._table
        conditions = self._conditions(query)
        count_statement = select(func.count()).select_from(table).where(and_(*conditions))
        data_statement = (
            select(table)
            .where(and_(*conditions))
            .order_by(table.c.review_date.desc(), table.c.id.desc())
            .limit(max_rows)
        )
        with self._engine.connect() as connection:
            total = int(connection.scalar(count_statement) or 0)
            rows = connection.execute(data_statement).mappings().all()
        return AnalysisBatch(
            items=[self._to_record(row) for row in rows],
            truncated=total > max_rows,
            total=total,
        )
