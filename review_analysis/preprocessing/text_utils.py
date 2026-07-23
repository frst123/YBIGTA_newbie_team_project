"""리뷰 텍스트 전처리 공통 유틸리티.

세 사이트(kakao / tripadvisor / tripdotcom)에 **동일한 기준**을 적용하기 위해
정제·토큰화·날짜 파싱 로직을 이 모듈에 모아둔다. 사이트별로 다른 기준을 쓰면
이후 비교분석에서 나타나는 차이가 '플랫폼 차이'가 아니라 '전처리 차이'가
되어버리므로, 공통 로직의 단일화가 중요하다.
"""

from __future__ import annotations

import re
from typing import List, Optional, Set

import pandas as pd

# ------------------------------------------------------------------
# 정규식 패턴
# ------------------------------------------------------------------
# 이모지(감정 표현, 기호, 교통, 국기, 이모티콘 보충 영역 등)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA70-\U0001FAFF"  # extended-A
    "\U00002600-\U000027BF"  # misc symbols & dingbats
    "\U00002190-\U000021FF"  # arrows
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U00002B00-\U00002BFF"  # misc symbols and arrows
    "]+",
    flags=re.UNICODE,
)

# 자음/모음만 남은 표현 (ㅋㅋ, ㅎㅎ, ㅠㅠ 등)
JAMO_PATTERN = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]+")

# 한글/영문/숫자/공백/기본 문장부호 외 제거
SPECIAL_PATTERN = re.compile(r"[^가-힣a-zA-Z0-9\s.,!?]")

# 연속 공백
MULTISPACE_PATTERN = re.compile(r"\s+")

# 반복 문자 3회 이상 (좋아요!!!!! -> 좋아요!!)
REPEAT_PATTERN = re.compile(r"(.)\1{2,}")

DATE_FORMAT = "%Y년 %m월 %d일"

# ------------------------------------------------------------------
# 불용어
# ------------------------------------------------------------------
# 일반 불용어: 의미 전달이 거의 없는 고빈도어
STOPWORDS: Set[str] = {
    "것", "수", "등", "및", "곳", "때", "번", "점", "분", "듯", "게", "거",
    "저희", "우리", "제가", "정말", "너무", "진짜", "조금", "매우", "아주",
    "그냥", "다시", "많이", "가장", "역시", "그리고", "하지만", "그래서",
    "이번", "저번", "다음", "이런", "저런", "그런", "어떤", "무슨",
    "하다", "있다", "없다", "되다", "이다", "아니다", "같다", "보다",
    "말다", "들다", "가다", "오다", "주다", "받다", "나다", "지다",
    "리뷰", "방문", "이용", "생각", "느낌", "정도",
    # 주의: "사람"(혼잡도), "시간"(대기시간)은 리뷰 분석에서 의미가 있어 제외하지 않음
}

# 영문 불용어: 카카오맵·트립어드바이저에 영어 리뷰가 일부 섞여 있어
# (kakao 약 8%) 최소한의 기능어만 제거한다.
EN_STOPWORDS: Set[str] = {
    "the", "and", "is", "are", "was", "were", "be", "been", "to", "of",
    "in", "on", "at", "for", "with", "you", "your", "it", "its", "this",
    "that", "there", "here", "we", "our", "us", "they", "them", "he",
    "she", "his", "her", "but", "or", "if", "so", "as", "an", "not",
    "can", "will", "would", "have", "has", "had", "do", "does", "did",
    "from", "by", "about", "when", "where", "what", "which", "who",
    "all", "some", "more", "most", "very", "just", "also", "too",
    "am", "im", "ive", "get", "got", "go", "going", "went", "one",
}

# 도메인 불용어: 모든 리뷰에 등장해 변별력이 없는 단어.
DOMAIN_STOPWORDS: Set[str] = {"경복궁", "궁", "고궁", "궁궐"}

# 형태소 태그: 명사·동사·형용사·어근 + 외국어(SL) 사용.
KEEP_TAGS = {"NNG", "NNP", "VV", "VA", "XR", "VV-R", "VV-I", "VA-R", "VA-I", "SL"}
VERB_TAGS = {"VV", "VA", "VV-R", "VV-I", "VA-R", "VA-I"}


# ------------------------------------------------------------------
# 토크나이저 (모듈 단위 싱글턴 - Kiwi 초기화 비용이 크므로 1회만 생성)
# ------------------------------------------------------------------
_kiwi = None


def _get_kiwi():  # type: ignore[no-untyped-def]
    """Kiwi 인스턴스를 lazy 초기화하여 반환한다.

    kiwipiepy 미설치 시 None을 반환하고, 호출 측에서 정규식 기반
    fallback 토크나이저를 사용한다.
    """
    global _kiwi
    if _kiwi is None:
        try:
            from kiwipiepy import Kiwi  # type: ignore[import-untyped]

            _kiwi = Kiwi()
        except ImportError:
            _kiwi = False  # 재시도 방지용 sentinel
    return _kiwi if _kiwi is not False else None


# ------------------------------------------------------------------
# 텍스트 정제
# ------------------------------------------------------------------
def count_emoji(text: str) -> int:
    """텍스트에 포함된 이모지 문자 수를 센다.

    이모지는 감성 신호를 담고 있어 단순 제거 시 정보가 손실된다.
    제거 전에 개수를 파생변수로 남겨두기 위한 함수.
    """
    return sum(len(m) for m in EMOJI_PATTERN.findall(str(text)))


def clean_text(text: str) -> str:
    """리뷰 본문을 정제한다.

    처리 순서:
      1. 이모지 제거
      2. 자음/모음만 남은 표현(ㅋㅋ, ㅠㅠ) 제거
      3. 한글/영문/숫자/기본 문장부호 외 특수문자 제거
      4. 3회 이상 반복 문자를 2회로 축약
      5. 연속 공백 정리

    Args:
        text: 원본 리뷰 본문.

    Returns:
        정제된 문자열. 입력이 결측이면 빈 문자열.
    """
    if pd.isna(text):
        return ""
    s = str(text)
    s = EMOJI_PATTERN.sub(" ", s)
    s = JAMO_PATTERN.sub(" ", s)
    s = SPECIAL_PATTERN.sub(" ", s)
    s = REPEAT_PATTERN.sub(r"\1\1", s)
    s = MULTISPACE_PATTERN.sub(" ", s)
    return s.strip()


# 조사·어미 후보 (긴 것부터 매칭해야 '에서는'이 '는'보다 먼저 잡힌다)
_JOSA = sorted(
    [
        "에서는", "에서도", "으로는", "이라고", "라고는", "에게서", "께서는",
        "에서", "에게", "으로", "라고", "이나", "이란", "부터", "까지",
        "마다", "처럼", "보다", "밖에", "조차", "커녕", "한테", "께서",
        "이다", "입니", "습니", "하고", "이고", "이며",
        "은", "는", "이", "가", "을", "를", "의", "에", "도", "와", "과",
        "만", "로", "랑", "야", "여", "요",
    ],
    key=len,
    reverse=True,
)
_TRAIL_PUNCT = re.compile(r"^[.,!?]+|[.,!?]+$")


def _fallback_tokenize(text: str, stop: Set[str]) -> List[str]:
    """kiwipiepy 미설치 환경용 간이 토크나이저.

    형태소 분석 없이 공백으로 나눈 뒤, 문장부호와 흔한 조사·어미를 규칙으로
    떼어낸다. 형태소 분석기만큼 정확하지는 않지만, 조사를 제거하지 않으면
    '경복궁이'·'경복궁을'·'경복궁은'이 모두 다른 토큰이 되어 TF-IDF가
    무의미해지므로 최소한의 정규화를 수행한다.

    정확한 분석 결과가 필요하면 ``pip install kiwipiepy``를 권장한다.
    """
    tokens: List[str] = []
    for raw in text.split():
        w = _TRAIL_PUNCT.sub("", raw)
        if not w:
            continue
        if re.fullmatch(r"[a-zA-Z]+", w):  # 영어는 소문자 통일 후 그대로 사용
            w = w.lower()
        else:
            for josa in _JOSA:  # 한글은 어미·조사 후보를 1회 절단
                if len(w) > len(josa) + 1 and w.endswith(josa):
                    w = w[: -len(josa)]
                    break
        if len(w) >= 2 and w not in stop:
            tokens.append(w)
    return tokens


def tokenize(text: str, extra_stopwords: Optional[Set[str]] = None) -> List[str]:
    """정제된 텍스트를 형태소 분석하여 토큰 리스트를 반환한다.

    명사(NNG/NNP), 동사(VV), 형용사(VA), 어근(XR)만 남기고 조사·어미·기호는
    제거한다. 동사·형용사는 원형('보' -> '보다') 형태로 복원해 가독성을 높인다.
    kiwipiepy 미설치 환경에서는 공백/길이 기반 fallback으로 동작한다.

    Args:
        text: 정제된 리뷰 본문.
        extra_stopwords: 기본 불용어에 추가로 제거할 단어 집합.

    Returns:
        불용어가 제거된 토큰 리스트.
    """
    stop = STOPWORDS | EN_STOPWORDS | (extra_stopwords or set())
    if not text:
        return []

    kiwi = _get_kiwi()
    if kiwi is None:
        return _fallback_tokenize(text, stop)

    tokens: List[str] = []
    for tok in kiwi.tokenize(text):
        if tok.tag not in KEEP_TAGS:
            continue
        form = tok.form
        if tok.tag in VERB_TAGS:
            form = form + "다"  # 원형 복원
        elif tok.tag == "SL":
            form = form.lower()  # 영어는 소문자로 통일해 표기 흔들림 제거
        if len(form) < 2:
            continue
        if form in stop:
            continue
        tokens.append(form)
    return tokens


# ------------------------------------------------------------------
# 날짜 파싱
# ------------------------------------------------------------------
def parse_dates(s: pd.Series, ref_date: Optional[pd.Timestamp] = None) -> pd.Series:
    """다양한 형태의 날짜 문자열을 datetime으로 통일한다.

    처리 대상:
      - "2025년 11월 1일" : 표준 형태 (세 사이트 공통)
      - "6월 5일"         : 연도 누락 → 기준일의 연도로 보정.
                            보정 결과가 미래면 전년도로 처리
      - "3일 전"          : 상대 표현 → 기준일에서 역산
                            ("3주 전", "2개월 전", "1년 전" 동일)

    Args:
        s: 날짜 문자열 시리즈.
        ref_date: 상대 표현의 기준일. 기본값은 오늘.

    Returns:
        datetime64 시리즈. 파싱 불가한 값은 NaT.
    """
    ref = ref_date if ref_date is not None else pd.Timestamp.today().normalize()
    out = pd.to_datetime(s, format=DATE_FORMAT, errors="coerce")

    unit_days = {"일": 1, "주": 7, "개월": 30, "달": 30, "년": 365}

    for idx in out[out.isna()].index:
        raw = str(s.loc[idx]).strip()

        m = re.match(r"(\d+)\s*(일|주|개월|달|년)\s*전", raw)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            out.loc[idx] = ref - pd.Timedelta(days=n * unit_days[unit])
            continue

        m = re.match(r"(\d{1,2})월\s*(\d{1,2})일", raw)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            try:
                cand = pd.Timestamp(year=ref.year, month=month, day=day)
            except ValueError:
                continue
            if cand > ref:
                cand = cand.replace(year=ref.year - 1)
            out.loc[idx] = cand

    return out