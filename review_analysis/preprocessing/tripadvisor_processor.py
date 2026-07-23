"""트립어드바이저 리뷰 전처리기."""

from __future__ import annotations

from review_analysis.preprocessing.common_processor import ReviewProcessor


class TripadvisorProcessor(ReviewProcessor):
    """트립어드바이저 리뷰 전처리기.

    컬럼 구조와 날짜 형식이 공통 스키마와 동일하다.

    특징: 본문이 가장 길고(평균 약 130자, 최대 1,441자) 장문 리뷰 비중이
    높다. 다만 수집 시기가 2016~2017년에 약 87% 집중되어 있는데, 이는
    리스트 페이지의 기본 정렬 방식에 따른 결과이며 실제 방문 추이가
    아니므로 시계열 해석 시 주의가 필요하다.
    """

    EXTRA_STOPWORDS: set = set()