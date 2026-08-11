from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewSite(str, Enum):
    KAKAO = "kakao"
    TRIPADVISOR = "tripadvisor"
    TRIPDOTCOM = "tripdotcom"


class GroupBy(str, Enum):
    MONTH = "month"
    YEAR = "year"
    WEEKDAY = "weekday"


class DateRatingFilter(StrictModel):
    site: ReviewSite = ReviewSite.KAKAO
    start_date: date | None = None
    end_date: date | None = None
    min_rating: float | None = Field(default=None, ge=1, le=5)
    max_rating: float | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def validate_ranges(self) -> "DateRatingFilter":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if (
            self.min_rating is not None
            and self.max_rating is not None
            and self.min_rating > self.max_rating
        ):
            raise ValueError("min_rating must be less than or equal to max_rating")
        return self


class SearchReviewsInput(DateRatingFilter):
    keyword: str | None = Field(default=None, min_length=1, max_length=100)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10_000)


class LatestReviewsInput(StrictModel):
    site: ReviewSite = ReviewSite.KAKAO
    limit: int = Field(default=10, ge=1, le=50)


class AggregateReviewsInput(DateRatingFilter):
    group_by: GroupBy = GroupBy.MONTH


class TopKeywordsInput(DateRatingFilter):
    limit: int = Field(default=10, ge=1, le=30)


class ReviewRecord(StrictModel):
    id: str
    site: ReviewSite
    date: date
    rating: float
    content: str
    tokens: list[str] = Field(default_factory=list)
    text_len: int | None = None
    token_count: int | None = None
    emoji_count: int | None = None
    collected_at: datetime | None = None


class ResultMetadata(StrictModel):
    backend: str
    generated_at: datetime
    filters: dict[str, Any] = Field(default_factory=dict)
    returned_rows: int
    total_rows: int | None = None
    limit: int | None = None
    offset: int | None = None
    truncated: bool = False


class ReviewSearchResult(StrictModel):
    items: list[ReviewRecord]
    metadata: ResultMetadata


class SourceSummary(StrictModel):
    site: ReviewSite
    row_count: int
    earliest_date: date | None
    latest_date: date | None
    last_collected_at: datetime | None = None


class SourceListResult(StrictModel):
    sources: list[SourceSummary]
    metadata: ResultMetadata


class AggregateBucket(StrictModel):
    period: str
    review_count: int
    average_rating: float
    average_text_len: float | None
    positive_count: int
    neutral_count: int
    negative_count: int


class AggregateResult(StrictModel):
    group_by: GroupBy
    buckets: list[AggregateBucket]
    metadata: ResultMetadata


class KeywordCount(StrictModel):
    keyword: str
    count: int
    document_ratio: float


class KeywordResult(StrictModel):
    keywords: list[KeywordCount]
    metadata: ResultMetadata
