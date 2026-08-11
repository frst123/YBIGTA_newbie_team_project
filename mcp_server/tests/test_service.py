from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from review_mcp.repositories.csv_repository import CsvReviewRepository
from review_mcp.schemas import (
    AggregateReviewsInput,
    GroupBy,
    ReviewSite,
    SearchReviewsInput,
    TopKeywordsInput,
)
from review_mcp.services import ReviewService


CSV = """site,date,rating,content,tokens,text_len,token_count,emoji_count
kakao,2025-06-09,5,좋은 경험,좋다 경험,5,2,0
kakao,2025-05-01,1,너무 불편,불편,5,1,0
kakao,2024-05-01,4,좋은 설명,좋다 설명,5,2,0
"""


class ReviewServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        path = Path(self.temp_dir.name) / "preprocessed_reviews_kakao.csv"
        path.write_text(CSV, encoding="utf-8-sig")
        repository = CsvReviewRepository(str(path))
        self.service = ReviewService(repository, max_analysis_rows=100)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_is_filtered_and_paginated(self) -> None:
        result = self.service.search(
            SearchReviewsInput(
                site=ReviewSite.KAKAO,
                keyword="좋",
                min_rating=4,
                limit=1,
            )
        )
        self.assertEqual(result.metadata.total_rows, 2)
        self.assertEqual(len(result.items), 1)

    def test_aggregate_month(self) -> None:
        result = self.service.aggregate(
            AggregateReviewsInput(
                site=ReviewSite.KAKAO,
                group_by=GroupBy.MONTH,
            )
        )
        self.assertEqual([bucket.period for bucket in result.buckets], [
            "2024-05",
            "2025-05",
            "2025-06",
        ])

    def test_top_keywords(self) -> None:
        result = self.service.top_keywords(
            TopKeywordsInput(site=ReviewSite.KAKAO, limit=2)
        )
        self.assertEqual(result.keywords[0].keyword, "좋다")
        self.assertEqual(result.keywords[0].count, 2)


if __name__ == "__main__":
    unittest.main()
