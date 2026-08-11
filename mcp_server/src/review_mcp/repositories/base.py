from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from review_mcp.schemas import (
    DateRatingFilter,
    ReviewRecord,
    ReviewSite,
    SearchReviewsInput,
    SourceSummary,
)


@dataclass(frozen=True)
class SearchPage:
    items: list[ReviewRecord]
    total: int


@dataclass(frozen=True)
class AnalysisBatch:
    items: list[ReviewRecord]
    truncated: bool
    total: int | None = None


class ReviewRepository(Protocol):
    @property
    def backend_name(self) -> str: ...

    def list_sources(self) -> list[SourceSummary]: ...

    def latest(self, site: ReviewSite, limit: int) -> list[ReviewRecord]: ...

    def search(self, query: SearchReviewsInput) -> SearchPage: ...

    def fetch_for_analysis(
        self, query: DateRatingFilter, max_rows: int
    ) -> AnalysisBatch: ...
