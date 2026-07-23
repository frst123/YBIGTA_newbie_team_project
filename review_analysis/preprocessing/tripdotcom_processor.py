"""트립닷컴 리뷰 전처리기."""

from __future__ import annotations

import pandas as pd

from review_analysis.preprocessing.common_processor import ReviewProcessor


class TripdotcomProcessor(ReviewProcessor):
    """트립닷컴 리뷰 전처리기.

    다른 두 사이트와 달리 ``reviewId``·``language`` 컬럼이 추가로 존재하고,
    날짜에 연도가 누락된 형태('6월 5일')와 상대 표현('3일 전')이 섞여 있다.
    날짜 보정은 공통 ``parse_dates``가 처리하며, 여기서는 고유 ID 기반
    중복 제거만 추가로 수행한다.
    """

    EXTRA_STOPWORDS: set = set()

    def normalize_columns(self) -> None:
        """reviewId 기반 중복을 먼저 제거한 뒤 표준 스키마로 정리한다.

        본문이 같아도 서로 다른 리뷰일 수 있으므로, 고유 ID가 제공되는
        경우 이를 우선 기준으로 삼는 편이 안전하다.
        """
        if "reviewId" in self.df.columns:
            before = len(self.df)
            self.df = self.df.drop_duplicates(subset=["reviewId"]).copy()
            removed = before - len(self.df)
            self.stats["제거:reviewId 중복"] = removed
            self._log(f"reviewId 중복: {removed}건 제거 (잔여 {len(self.df)})")

        super().normalize_columns()