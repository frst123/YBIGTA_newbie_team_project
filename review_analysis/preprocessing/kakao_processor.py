"""카카오맵 리뷰 전처리기."""

from __future__ import annotations

from review_analysis.preprocessing.common_processor import ReviewProcessor


class KakaoProcessor(ReviewProcessor):
    """카카오맵 리뷰 전처리기.

    컬럼 구조(rating/date/content)와 날짜 형식('YYYY년 M월 D일')이 공통
    스키마와 동일하므로 별도 오버라이드 없이 공통 로직을 그대로 사용한다.

    특징: 세 사이트 중 본문이 가장 짧고(평균 약 37자) 별점이 5점에 가장
    크게 쏠려 있다(약 85%). 또한 content 결측이 다수 존재하는데, 이는
    별점만 남기고 텍스트를 작성하지 않은 리뷰로 보인다.
    """

    EXTRA_STOPWORDS: set = set()