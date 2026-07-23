"""사이트 공통 리뷰 전처리 클래스.

``BaseDataProcessor``를 상속하여 세 사이트에 공통으로 적용되는 전처리·FE
로직을 구현한다. 사이트별 처리(컬럼명 차이, 추가 컬럼 등)는 이 클래스를
상속한 각 사이트 processor에서 훅 메서드를 오버라이드해 처리한다.

전처리 기준을 사이트마다 다르게 두면 이후 비교분석에서 관측되는 차이가
'플랫폼 차이'인지 '전처리 차이'인지 구분할 수 없게 되므로, 공통 기준을
한 곳에서 관리한다.
"""

from __future__ import annotations

import glob
import os
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD  # type: ignore[import-untyped]
from sklearn.feature_extraction.text import (  # type: ignore[import-untyped]
    TfidfVectorizer,
)

from review_analysis.preprocessing.base_processor import BaseDataProcessor
from review_analysis.preprocessing.text_utils import (
    clean_text,
    count_emoji,
    parse_dates,
    tokenize,
)

# ------------------------------------------------------------------
# 전처리 기준 상수
# ------------------------------------------------------------------
RATING_MIN, RATING_MAX = 1.0, 5.0
MIN_TEXT_LEN = 2          # 정제 후 이 길이 미만이면 분석 불가로 판단해 제거
MIN_TOKEN_COUNT = 1       # 토큰이 하나도 없으면 TF-IDF에서 0벡터가 되므로 제거
MAX_PAST_YEARS = 20       # 이보다 오래된 날짜는 파싱 오류로 간주
SVD_COMPONENTS = 16       # CSV에 저장할 TF-IDF 축약 차원 수
TFIDF_MAX_FEATURES = 3000
TFIDF_MIN_DF = 2          # 2개 미만 문서에만 등장하는 단어는 제외(오탈자 노이즈)


# ==================================================================
# 코퍼스 통합 벡터라이저
# ==================================================================
class _CorpusVectorizer:
    """세 사이트 리뷰를 합쳐 한 번만 fit하는 TF-IDF 벡터라이저.

    사이트별로 각자 ``fit``하면 vocabulary와 컬럼 인덱스가 달라져
    "A의 3번 컬럼"과 "B의 3번 컬럼"이 서로 다른 단어를 가리키게 된다.
    그 상태로는 사이트간 비교가 성립하지 않으므로, database 폴더의 모든
    ``reviews_*.csv``를 읽어 공통 코퍼스로 fit한 뒤 각 사이트를 transform한다.

    ``--all`` 실행 시 processor가 순차 실행되므로, 첫 processor 시점에는
    다른 사이트의 전처리 결과가 아직 없다. 따라서 원본 CSV에 동일한
    정제·토큰화 함수를 적용해 코퍼스를 구성한다. 결과는 클래스 변수에
    캐시되어 이후 processor는 재계산 없이 재사용한다.
    """

    _cache: Dict[str, "_CorpusVectorizer"] = {}

    def __init__(self, database_dir: str, extra_stopwords: Optional[Set[str]] = None):
        self.database_dir = database_dir
        corpus = self._build_corpus(database_dir, extra_stopwords)

        self.vectorizer = TfidfVectorizer(
            max_features=TFIDF_MAX_FEATURES,
            min_df=TFIDF_MIN_DF,
            token_pattern=r"\S+",  # 이미 토큰화된 문자열이므로 공백 기준 분리
        )
        matrix = self.vectorizer.fit_transform(corpus)

        n_comp = min(SVD_COMPONENTS, matrix.shape[1] - 1)
        self.svd = TruncatedSVD(n_components=max(n_comp, 1), random_state=42)
        self.svd.fit(matrix)

        self.vocab_size = len(self.vectorizer.vocabulary_)
        self.corpus_size = len(corpus)

    @staticmethod
    def _build_corpus(
        database_dir: str, extra_stopwords: Optional[Set[str]]
    ) -> List[str]:
        """database 폴더의 모든 원본 리뷰 CSV로 공통 코퍼스를 구성한다."""
        corpus: List[str] = []
        pattern = os.path.join(database_dir, "reviews_*.csv")
        for path in sorted(glob.glob(pattern)):
            if "checkpoint" in os.path.basename(path):
                continue
            try:
                df = pd.read_csv(path)
            except (OSError, pd.errors.ParserError):
                continue
            if "content" not in df.columns:
                continue
            for raw in df["content"].dropna():
                toks = tokenize(clean_text(raw), extra_stopwords)
                if toks:
                    corpus.append(" ".join(toks))
        return corpus

    @classmethod
    def get(
        cls, database_dir: str, extra_stopwords: Optional[Set[str]] = None
    ) -> "_CorpusVectorizer":
        """디렉토리 단위로 캐시된 인스턴스를 반환한다."""
        key = os.path.abspath(database_dir)
        if key not in cls._cache:
            cls._cache[key] = cls(database_dir, extra_stopwords)
        return cls._cache[key]

    def transform(self, token_texts: List[str]) -> np.ndarray:
        """토큰 문자열 리스트를 SVD 축약된 밀집 벡터로 변환한다."""
        matrix = self.vectorizer.transform(token_texts)
        return self.svd.transform(matrix)


# ==================================================================
# 공통 Processor
# ==================================================================
class ReviewProcessor(BaseDataProcessor):
    """리뷰 CSV 전처리·FE 공통 구현.

    Attributes:
        input_path: 원본 리뷰 CSV 경로.
        output_dir: 결과 CSV 저장 디렉토리.
        site: 사이트 이름 (입력 파일명에서 자동 추출).
        df: 처리 중인 데이터프레임.
        stats: 단계별 제거 건수 등 EDA 리포트용 통계.
    """

    #: 사이트별로 추가 제거할 불용어 (하위 클래스에서 오버라이드)
    EXTRA_STOPWORDS: Set[str] = set()

    def __init__(self, input_path: str, output_dir: str) -> None:
        super().__init__(input_path, output_dir)
        base = os.path.splitext(os.path.basename(input_path))[0]
        self.site: str = base.replace("reviews_", "")
        self.df: pd.DataFrame = pd.read_csv(input_path)
        self.stats: Dict[str, object] = {"site": self.site, "원본 건수": len(self.df)}
        self._log(f"[{self.site}] 원본 {len(self.df)}건 로드")

    # --------------------------------------------------------------
    # 로깅
    # --------------------------------------------------------------
    def _log(self, msg: str) -> None:
        print(f"  {msg}")

    def _drop(self, mask: pd.Series, reason: str) -> None:
        """조건에 해당하는 행을 제거하고 건수를 기록한다.

        Args:
            mask: 제거 대상이 True인 불리언 마스크.
            reason: 통계·로그에 남길 사유.
        """
        n = int(mask.sum())
        if n:
            self.df = self.df[~mask].copy()
        self.stats[f"제거:{reason}"] = n
        self._log(f"{reason}: {n}건 제거 (잔여 {len(self.df)})")

    # --------------------------------------------------------------
    # 사이트별 훅
    # --------------------------------------------------------------
    def normalize_columns(self) -> None:
        """사이트별 컬럼 차이를 표준 스키마로 맞춘다.

        기본 구현은 rating/date/content 외 컬럼을 제거한다. 추가 컬럼을
        살리거나 컬럼명이 다른 사이트는 하위 클래스에서 오버라이드한다.
        """
        keep = [c for c in ("rating", "date", "content") if c in self.df.columns]
        self.df = self.df[keep].copy()

    # --------------------------------------------------------------
    # 1) 전처리
    # --------------------------------------------------------------
    def preprocess(self) -> None:
        """결측치·이상치 제거 및 텍스트 정제를 수행한다.

        처리 순서에 의도가 있다. 결측치와 범위 이상치를 먼저 제거해야
        이후 통계(길이 분포 등)가 오염되지 않고, 텍스트 정제를 길이 필터
        **앞에** 두어야 이모지·특수문자만으로 이루어진 리뷰를 걸러낼 수 있다.
        """
        self._log(f"--- [{self.site}] preprocess ---")
        self.normalize_columns()

        # (1) 결측치
        self._drop(self.df["content"].isna(), "content 결측")
        self._drop(self.df["rating"].isna(), "rating 결측")
        self._drop(self.df["date"].isna(), "date 결측")

        # (2) 중복 (같은 사람이 같은 내용을 중복 등록한 경우)
        self._drop(self.df.duplicated(subset=["date", "content"]), "중복")

        # (3) 별점 범위
        self.df["rating"] = pd.to_numeric(self.df["rating"], errors="coerce")
        self._drop(self.df["rating"].isna(), "rating 숫자변환 실패")
        self._drop(
            (self.df["rating"] < RATING_MIN) | (self.df["rating"] > RATING_MAX),
            f"별점 범위({RATING_MIN}~{RATING_MAX}) 밖",
        )

        # (4) 날짜 파싱 및 기간 이상치
        ref = pd.Timestamp.today().normalize()
        self.df["date"] = parse_dates(self.df["date"], ref_date=ref)
        self._drop(self.df["date"].isna(), "날짜 파싱 실패")
        self._drop(self.df["date"] > ref, "미래 날짜")
        self._drop(
            self.df["date"] < ref - pd.DateOffset(years=MAX_PAST_YEARS),
            f"{MAX_PAST_YEARS}년 초과 과거",
        )

        # (5) 텍스트 정제 (이모지는 제거 전 개수를 파생변수로 보존)
        self.df["emoji_count"] = self.df["content"].map(count_emoji)
        self.df["content"] = self.df["content"].map(clean_text)

        # (6) 길이 하한
        #     상한은 두지 않는다. 리뷰 길이는 우편향 분포라 IQR 상한 적용 시 tripadvisor 기준 102건(6.8%)이 제거됨
        #     해당 실제 리뷰들을 확인한 결과 파싱 오류가 아닌 정상 장문 리뷰였다. 정보량이 많은 데이터이므로 보존한다. (근거: EDA 텍스트 길이 분포 그래프)
        self._drop(
            self.df["content"].str.len() < MIN_TEXT_LEN,
            f"{MIN_TEXT_LEN}자 미만",
        )

        self.df = self.df.reset_index(drop=True)
        self.stats["전처리 후 건수"] = len(self.df)

    # --------------------------------------------------------------
    # 2) 피처 엔지니어링
    # --------------------------------------------------------------
    def feature_engineering(self) -> None:
        """파생변수 생성 및 텍스트 벡터화를 수행한다.

        생성 변수:
          - site               : 사이트 구분자 (세 CSV 통합 비교 시 필수)
          - year/month/weekday : 시간 파생변수 (weekday: '작성일 요일')
          - text_len           : 정제 후 본문 길이
          - token_count        : 토큰 개수
          - emoji_count        : 이모지 개수 (preprocess에서 생성)
          - tokens             : 형태소 분석 + 불용어 제거된 공백 구분 문자열
          - tfidf_svd_XX       : 공통 코퍼스 TF-IDF의 SVD 축약 벡터

        ``tokens``는 후속 분석(LDA 기반 토픽분석, 키워드 빈도, 기타등등)에서 형태소 분석기 설치 없이 ``TfidfVectorizer``에 바로 투입할 수 있도록 제공한다.
        """
        self._log(f"--- [{self.site}] feature_engineering ---")

        # (1) 메타 · 시간 파생변수
        self.df["site"] = self.site
        self.df["year"] = self.df["date"].dt.year
        self.df["month"] = self.df["date"].dt.month
        self.df["weekday"] = self.df["date"].dt.dayofweek  # 0=월, 1=화, 2=수, ...,  6=일
        self.df["text_len"] = self.df["content"].str.len()

        # (2) 형태소 토큰화
        token_lists = self.df["content"].map(
            lambda t: tokenize(t, self.EXTRA_STOPWORDS)
        )
        self.df["tokens"] = token_lists.map(lambda ts: " ".join(ts))
        self.df["token_count"] = token_lists.map(len)

        # 토큰이 없으면 TF-IDF에서 0벡터가 되어 유사도·토픽모델링이 깨진다.
        self._drop(self.df["token_count"] < MIN_TOKEN_COUNT, "토큰 0개")
        self.df = self.df.reset_index(drop=True)

        # (3) 공통 코퍼스 기반 TF-IDF → SVD 축약
        database_dir = os.path.dirname(os.path.abspath(self.input_path))
        cv = _CorpusVectorizer.get(database_dir, self.EXTRA_STOPWORDS)
        self._log(
            f"공통 코퍼스: {cv.corpus_size}건 / 어휘 {cv.vocab_size}개"
        )
        vectors = cv.transform(self.df["tokens"].tolist())
        for i in range(vectors.shape[1]):
            self.df[f"tfidf_svd_{i:02d}"] = vectors[:, i]

        # (4) 날짜를 문자열로 통일 (CSV 저장 포맷 고정)
        self.df["date"] = self.df["date"].dt.strftime("%Y-%m-%d")

        self.stats["최종 건수"] = len(self.df)
        self.stats["TF-IDF 어휘 수"] = cv.vocab_size

    # --------------------------------------------------------------
    # 3) 저장
    # --------------------------------------------------------------
    def save_to_database(self) -> None:
        """``preprocessed_reviews_{site}.csv``로 저장한다."""
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"preprocessed_reviews_{self.site}.csv")

        front = [
            "site", "date", "rating", "content", "tokens",
            "text_len", "token_count", "emoji_count",
            "year", "month", "weekday",
        ]
        cols = [c for c in front if c in self.df.columns]
        cols += [c for c in self.df.columns if c not in cols]

        self.df[cols].to_csv(path, index=False, encoding="utf-8-sig")
        self._log(f"저장 완료: {path} ({len(self.df)}건, {len(cols)}컬럼)")

    # --------------------------------------------------------------
    def summary(self) -> Dict[str, object]:
        """단계별 처리 통계를 반환한다(README·EDA 리포트용)."""
        return self.stats