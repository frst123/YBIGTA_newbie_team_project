from __future__ import annotations

import csv
import glob
from datetime import date, datetime, timezone
from pathlib import Path

from review_mcp.repositories.base import AnalysisBatch, SearchPage
from review_mcp.schemas import (
    DateRatingFilter,
    ReviewRecord,
    ReviewSite,
    SearchReviewsInput,
    SourceSummary,
)


def _optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


class CsvReviewRepository:
    """Local development adapter for the preprocessed CSV output."""

    def __init__(self, data_glob: str) -> None:
        self._paths = [Path(path) for path in sorted(glob.glob(data_glob))]
        if not self._paths:
            raise FileNotFoundError(f"No preprocessed review CSV matched: {data_glob}")
        self._records = self._load()

    @property
    def backend_name(self) -> str:
        return "csv"

    def _load(self) -> list[ReviewRecord]:
        records: list[ReviewRecord] = []
        for path in self._paths:
            collected_at = datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            )
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                for line_number, row in enumerate(reader, start=2):
                    site = ReviewSite(row.get("site") or self._site_from_name(path))
                    records.append(
                        ReviewRecord(
                            id=f"{site.value}:{path.stem}:{line_number}",
                            site=site,
                            date=date.fromisoformat(row["date"]),
                            rating=float(row["rating"]),
                            content=row["content"],
                            tokens=(row.get("tokens") or "").split(),
                            text_len=_optional_int(row.get("text_len")),
                            token_count=_optional_int(row.get("token_count")),
                            emoji_count=_optional_int(row.get("emoji_count")),
                            collected_at=collected_at,
                        )
                    )
        return sorted(records, key=lambda item: (item.date, item.id), reverse=True)

    @staticmethod
    def _site_from_name(path: Path) -> str:
        return path.stem.removeprefix("preprocessed_reviews_")

    @staticmethod
    def _matches(record: ReviewRecord, query: DateRatingFilter) -> bool:
        return (
            record.site == query.site
            and (query.start_date is None or record.date >= query.start_date)
            and (query.end_date is None or record.date <= query.end_date)
            and (query.min_rating is None or record.rating >= query.min_rating)
            and (query.max_rating is None or record.rating <= query.max_rating)
        )

    def list_sources(self) -> list[SourceSummary]:
        output: list[SourceSummary] = []
        for site in ReviewSite:
            rows = [row for row in self._records if row.site == site]
            if not rows:
                continue
            output.append(
                SourceSummary(
                    site=site,
                    row_count=len(rows),
                    earliest_date=min(row.date for row in rows),
                    latest_date=max(row.date for row in rows),
                    last_collected_at=max(
                        (
                            row.collected_at
                            for row in rows
                            if row.collected_at is not None
                        ),
                        default=None,
                    ),
                )
            )
        return output

    def latest(self, site: ReviewSite, limit: int) -> list[ReviewRecord]:
        return [row for row in self._records if row.site == site][:limit]

    def search(self, query: SearchReviewsInput) -> SearchPage:
        keyword = query.keyword.casefold() if query.keyword else None
        matches = [
            row
            for row in self._records
            if self._matches(row, query)
            and (
                keyword is None
                or keyword in row.content.casefold()
                or any(keyword in token.casefold() for token in row.tokens)
            )
        ]
        return SearchPage(
            items=matches[query.offset : query.offset + query.limit],
            total=len(matches),
        )

    def fetch_for_analysis(
        self, query: DateRatingFilter, max_rows: int
    ) -> AnalysisBatch:
        matches = [row for row in self._records if self._matches(row, query)]
        return AnalysisBatch(
            items=matches[:max_rows],
            truncated=len(matches) > max_rows,
            total=len(matches),
        )
