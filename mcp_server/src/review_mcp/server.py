from __future__ import annotations

from datetime import date
from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from review_mcp.config import Settings
from review_mcp.repositories import create_repository
from review_mcp.schemas import (
    AggregateResult,
    AggregateReviewsInput,
    GroupBy,
    KeywordResult,
    LatestReviewsInput,
    ReviewSearchResult,
    ReviewSite,
    SearchReviewsInput,
    SourceListResult,
    TopKeywordsInput,
)
from review_mcp.services import ReviewService


def build_service(settings: Settings | None = None) -> ReviewService:
    selected = settings or Settings.from_env()
    return ReviewService(
        repository=create_repository(selected),
        max_analysis_rows=selected.max_analysis_rows,
    )


def build_mcp_server(service: ReviewService | None = None) -> MCPServer:
    review_service = service or build_service()
    server = MCPServer(
        "YBIGTA Review Analysis",
        instructions=(
            "Use these read-only tools to answer questions from the collected "
            "and preprocessed Gyeongbokgung review dataset. Never invent rows "
            "or claim a result came from the DB when a tool was not called."
        ),
    )

    @server.tool()
    def list_review_sources() -> SourceListResult:
        """List review sources, row counts, date coverage, and collection time."""
        return review_service.list_sources()

    @server.tool()
    def get_latest_reviews(
        site: ReviewSite = ReviewSite.KAKAO,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> ReviewSearchResult:
        """Return the newest reviews for one allowed source (maximum 50)."""
        query = LatestReviewsInput(site=site, limit=limit)
        return review_service.latest(query)

    @server.tool()
    def search_reviews(
        site: ReviewSite = ReviewSite.KAKAO,
        keyword: Annotated[
            str | None, Field(min_length=1, max_length=100)
        ] = None,
        start_date: date | None = None,
        end_date: date | None = None,
        min_rating: Annotated[float | None, Field(ge=1, le=5)] = None,
        max_rating: Annotated[float | None, Field(ge=1, le=5)] = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        offset: Annotated[int, Field(ge=0, le=10_000)] = 0,
    ) -> ReviewSearchResult:
        """Search reviews with bounded, validated filters; no raw SQL is accepted."""
        query = SearchReviewsInput(
            site=site,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            min_rating=min_rating,
            max_rating=max_rating,
            limit=limit,
            offset=offset,
        )
        return review_service.search(query)

    @server.tool()
    def aggregate_review_stats(
        site: ReviewSite = ReviewSite.KAKAO,
        start_date: date | None = None,
        end_date: date | None = None,
        min_rating: Annotated[float | None, Field(ge=1, le=5)] = None,
        max_rating: Annotated[float | None, Field(ge=1, le=5)] = None,
        group_by: GroupBy = GroupBy.MONTH,
    ) -> AggregateResult:
        """Aggregate counts, ratings, lengths, and sentiment by month/year/weekday."""
        query = AggregateReviewsInput(
            site=site,
            start_date=start_date,
            end_date=end_date,
            min_rating=min_rating,
            max_rating=max_rating,
            group_by=group_by,
        )
        return review_service.aggregate(query)

    @server.tool()
    def get_top_review_keywords(
        site: ReviewSite = ReviewSite.KAKAO,
        start_date: date | None = None,
        end_date: date | None = None,
        min_rating: Annotated[float | None, Field(ge=1, le=5)] = None,
        max_rating: Annotated[float | None, Field(ge=1, le=5)] = None,
        limit: Annotated[int, Field(ge=1, le=30)] = 10,
    ) -> KeywordResult:
        """Return frequent preprocessed tokens for the selected review slice."""
        query = TopKeywordsInput(
            site=site,
            start_date=start_date,
            end_date=end_date,
            min_rating=min_rating,
            max_rating=max_rating,
            limit=limit,
        )
        return review_service.top_keywords(query)

    return server


def __getattr__(name: str) -> MCPServer:
    # Lazy build (PEP 562): importing this module never touches .env, so a
    # placeholder or missing configuration cannot break imports or tests.
    # `from review_mcp.server import mcp` and `mcp dev` still work unchanged.
    if name == "mcp":
        return build_mcp_server()
    raise AttributeError(name)


if __name__ == "__main__":
    build_mcp_server().run(transport="stdio")
