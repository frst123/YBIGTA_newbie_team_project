"""MongoDB 기반 리뷰 전처리기.

``ReviewProcessor``의 변환 로직(정제·파생변수·벡터화)은 그대로 상속하고,
입출력만 CSV → MongoDB로 교체한다. 전처리 기준이 CSV 경로와 동일하므로
두 경로의 결과가 일치한다.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

import pandas as pd

from database.mongodb_connection import mongo_db
from review_analysis.preprocessing.common_processor import (
    ReviewProcessor,
    _CorpusVectorizer,
    _texts_to_corpus,
)

RAW_COLLECTION = "reviews_raw"
PROCESSED_COLLECTION = "reviews_processed"


class MongoReviewProcessor(ReviewProcessor):
    """MongoDB에서 읽고 MongoDB에 쓰는 전처리기."""

    EXTRA_STOPWORDS: Set[str] = set()

    def __init__(self, site_name: str) -> None:
        # 부모 __init__은 pd.read_csv를 호출하므로 의도적으로 우회한다.
        self.input_path = ""
        self.output_dir = ""
        self.site = site_name

        docs = list(
            mongo_db[RAW_COLLECTION].find({"site_name": site_name}, {"_id": 0})
        )
        self.df = pd.DataFrame(docs)
        self.stats: Dict[str, object] = {
            "site": self.site,
            "원본 건수": len(self.df),
        }
        self._log(f"[{self.site}] MongoDB에서 {len(self.df)}건 로드")

    # ------------------------------------------------------------------
    def _get_vectorizer(self) -> _CorpusVectorizer:
        """reviews_raw 전체를 공통 코퍼스로 사용한다."""
        return _CorpusVectorizer.get_or_create(
            key="mongo:reviews_raw",
            corpus_factory=lambda: self._build_corpus_from_mongo(),
        )

    def _build_corpus_from_mongo(self) -> List[str]:
        cursor = mongo_db[RAW_COLLECTION].find(
            {"content": {"$ne": None}}, {"_id": 0, "content": 1}
        )
        return _texts_to_corpus(
            (d.get("content") for d in cursor), self.EXTRA_STOPWORDS
        )

    # ------------------------------------------------------------------
    def save_to_database(self) -> int:
        """전처리 결과를 reviews_processed에 저장한다.

        API가 반복 호출될 수 있으므로 해당 사이트 문서를 먼저 삭제해
        멱등성을 보장한다.
        """
        self.df["site_name"] = self.site 
        col = mongo_db[PROCESSED_COLLECTION]
        records = self.df.to_dict("records")
        records = self.df.astype(object).where(pd.notna(self.df), None).to_dict("records")

        deleted = col.delete_many({"site_name": self.site}).deleted_count
        if records:
            col.insert_many(records)

        self._log(f"저장 완료: 기존 {deleted}건 삭제 → {len(records)}건 저장")
        return len(records)