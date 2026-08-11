from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import fmean
from typing import Any

from review_mcp.repositories.base import ReviewRepository
from review_mcp.schemas import (
    AggregateBucket,
    AggregateResult,
    AggregateReviewsInput,
    DateRatingFilter,
    GroupBy,
    KeywordCount,
    KeywordResult,
    LatestReviewsInput,
    ResultMetadata,
    ReviewRecord,
    ReviewSearchResult,
    SearchReviewsInput,
    SourceListResult,
    TopKeywordsInput,
)


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class ReviewService:
    def __init__(self, repository: ReviewRepository, max_analysis_rows: int) -> None:
        self._repository = repository
        self._max_analysis_rows = max_analysis_rows

    def _metadata(
        self,
        *,
        filters: dict[str, Any],
        returned_rows: int,
        total_rows: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
        truncated: bool = False,
    ) -> ResultMetadata:
        return ResultMetadata(
            backend=self._repository.backend_name,
            generated_at=datetime.now(timezone.utc),
            filters=filters,
            returned_rows=returned_rows,
            total_rows=total_rows,
            limit=limit,
            offset=offset,
            truncated=truncated,
        )

    @staticmethod
    def _filters(query: DateRatingFilter) -> dict[str, Any]:
        return query.model_dump(mode="json", exclude_none=True)

    def list_sources(self) -> SourceListResult:
        sources = self._repository.list_sources()
        return SourceListResult(
            sources=sources,
            metadata=self._metadata(
                filters={},
                returned_rows=len(sources),
                total_rows=len(sources),
            ),
        )

    def latest(self, query: LatestReviewsInput) -> ReviewSearchResult:
        items = self._repository.latest(query.site, query.limit)
        return ReviewSearchResult(
            items=items,
            metadata=self._metadata(
                filters={"site": query.site.value},
                returned_rows=len(items),
                limit=query.limit,
            ),
        )

    def search(self, query: SearchReviewsInput) -> ReviewSearchResult:
        page = self._repository.search(query)
        return ReviewSearchResult(
            items=page.items,
            metadata=self._metadata(
                filters=self._filters(query),
                returned_rows=len(page.items),
                total_rows=page.total,
                limit=query.limit,
                offset=query.offset,
            ),
        )

    @staticmethod
    def _period(record: ReviewRecord, group_by: GroupBy) -> str:
        if group_by == GroupBy.YEAR:
            return f"{record.date.year:04d}"
        if group_by == GroupBy.MONTH:
            return f"{record.date.year:04d}-{record.date.month:02d}"
        return _WEEKDAYS[record.date.weekday()]

    def aggregate(self, query: AggregateReviewsInput) -> AggregateResult:
        batch = self._repository.fetch_for_analysis(
            query, self._max_analysis_rows
        )
        grouped: dict[str, list[ReviewRecord]] = defaultdict(list)
        for item in batch.items:
            grouped[self._period(item, query.group_by)].append(item)

        keys = list(grouped)
        if query.group_by == GroupBy.WEEKDAY:
            keys.sort(key=_WEEKDAYS.index)
        else:
            keys.sort()

        buckets: list[AggregateBucket] = []
        for key in keys:
            rows = grouped[key]
            text_lengths = [
                item.text_len for item in rows if item.text_len is not None
            ]
            buckets.append(
                AggregateBucket(
                    period=key,
                    review_count=len(rows),
                    average_rating=round(fmean(item.rating for item in rows), 3),
                    average_text_len=(
                        round(fmean(text_lengths), 2) if text_lengths else None
                    ),
                    positive_count=sum(item.rating >= 4 for item in rows),
                    neutral_count=sum(2 < item.rating < 4 for item in rows),
                    negative_count=sum(item.rating <= 2 for item in rows),
                )
            )

        return AggregateResult(
            group_by=query.group_by,
            buckets=buckets,
            metadata=self._metadata(
                filters=self._filters(query),
                returned_rows=len(buckets),
                total_rows=batch.total,
                truncated=batch.truncated,
            ),
        )

    def top_keywords(self, query: TopKeywordsInput) -> KeywordResult:
        batch = self._repository.fetch_for_analysis(
            query, self._max_analysis_rows
        )
        counts: Counter[str] = Counter()
        document_counts: Counter[str] = Counter()
        for item in batch.items:
            usable = [token for token in item.tokens if len(token) >= 2]
            counts.update(usable)
            document_counts.update(set(usable))

        document_total = len(batch.items)
        keywords = [
            KeywordCount(
                keyword=keyword,
                count=count,
                document_ratio=round(
                    document_counts[keyword] / document_total, 4
                )
                if document_total
                else 0.0,
            )
            for keyword, count in counts.most_common(query.limit)
        ]
        return KeywordResult(
            keywords=keywords,
            metadata=self._metadata(
                filters=self._filters(query),
                returned_rows=len(keywords),
                total_rows=batch.total,
                limit=query.limit,
                truncated=batch.truncated,
            ),
        )
