"""트립어드바이저 경복궁 리뷰 크롤러.

트립어드바이저는 리뷰가 정적 HTML로 렌더되므로 Selenium 없이
``requests`` + ``BeautifulSoup``로 수집한다. 페이지네이션은 리뷰 URL에
``-or{offset}-`` 오프셋을 끼우는 방식을 사용한다.

BaseCrawler 추상 클래스를 상속하며, main.py의 실행 흐름
(``scrape_reviews()`` -> ``save_to_database()``)에 맞춰
``scrape_reviews()`` 내부에서 ``start_browser()``(세션 초기화)를 호출한다.
"""

from __future__ import annotations

import csv
import os
import random
import re
import time
from functools import wraps
from logging import Logger
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

import requests
from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.common.exceptions import TimeoutException, WebDriverException

from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger

# ------------------------------------------------------------------
# 설정 상수
# ------------------------------------------------------------------
# 경복궁: g294197(서울) / d324888(경복궁). offset 자리에 0,10,20... 삽입.
REVIEW_URL_TEMPLATE: str = (
    "https://www.tripadvisor.co.kr/"
    "Attraction_Review-g294197-d324888-Reviews-or{offset}-"
    "Gyeongbokgung_Palace-Seoul.html"
)

PAGE_SIZE: int = 10            # 트립어드바이저 리스트 페이지당 리뷰 수(오프셋 증가폭)
TARGET_REVIEWS: int = 1500     # 목표 수집 개수
SAVE_INTERVAL: int = 100       # N개마다 중간 저장(flush)
REQUEST_PAUSE_RANGE: tuple[float, float] = (1.5, 3.0)  # 페이지 요청 간 랜덤 딜레이(초)
MAX_EMPTY_PAGES: int = 3       # 리뷰 0건 페이지가 연속 이 횟수면 종료
REQUEST_TIMEOUT: int = 15      # HTTP 타임아웃(초)

# 최신 크롬 UA. 미전송 시 트립어드바이저가 구형 브라우저로 취급하므로 필수.
USER_AGENT: str = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


F = TypeVar("F", bound=Callable[..., Any])


def retry(max_attempts: int = 3, delay: float = 2.0) -> Callable[[F], F]:
    """지정 예외 발생 시 함수를 재시도하는 데코레이터.

    네트워크 흔들림/일시적 HTTP 오류를 흡수한다. ``max_attempts`` 초과 시
    마지막 예외를 다시 raise 한다.

    Args:
        max_attempts: 최대 시도 횟수.
        delay: 재시도 사이 대기 시간(초). 시도마다 선형 증가.

    Returns:
        원본 함수를 감싼 데코레이터.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (
                    requests.RequestException,
                    TimeoutException,
                    WebDriverException,
                ) as exc:
                    last_exc = exc
                    time.sleep(delay * attempt)
            assert last_exc is not None
            raise last_exc

        return cast(F, wrapper)

    return decorator


class TripadvisorCrawler(BaseCrawler):
    """트립어드바이저 경복궁 리뷰 크롤러(정적 HTML 파싱).

    Attributes:
        output_dir: CSV가 저장될 디렉토리.
        logger: 로깅 핸들러.
        session: requests 세션(start_browser에서 초기화).
        reviews: 수집한 리뷰 딕셔너리 리스트.
    """

    SITE_NAME: str = "tripadvisor"

    def __init__(self, output_dir: str) -> None:
        super().__init__(output_dir)
        self.logger: Logger = setup_logger(
            log_file=os.path.join(output_dir, f"crawl_{self.SITE_NAME}.log")
        )
        self.driver: Optional[WebDriver] = None
        self.reviews: List[Dict[str, str]] = []
        self._flushed: int = 0

    # --------------------------------------------------------------
    # BaseCrawler 필수 구현 3종
    # --------------------------------------------------------------
    def start_browser(self) -> None:
        """Chrome WebDriver를 기동한다.

        트립어드바이저는 순수 HTTP 클라이언트(requests)를 403으로 막지만
        실제 브라우저는 통과시키므로 Selenium으로 페이지를 연다. 정적 파싱
        전략은 유지하고, 가져오는 수단만 driver.get + page_source로 바꾼다.
        """
        options = Options()
        # 필요 시 headless 사용. 디버깅 중엔 주석 처리 권장.
        # options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--lang=ko-KR")
        options.add_argument(f"user-agent={USER_AGENT}")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)
        self.logger.info("브라우저 기동 완료")

    def scrape_reviews(self) -> None:
        """오프셋을 늘려가며 리뷰 페이지를 순회·파싱한다.

        main.py가 start_browser를 호출하지 않으므로 여기서 직접 초기화한다.
        목표 개수를 채우거나 빈 페이지가 연속되면 종료하고, 수집 중
        SAVE_INTERVAL마다 중간 저장한다.
        """
        self.start_browser()

        offset = 0
        empty_streak = 0

        try:
            while len(self.reviews) < TARGET_REVIEWS and empty_streak < MAX_EMPTY_PAGES:
                url = REVIEW_URL_TEMPLATE.format(offset=offset)
                html = self._fetch_page(url)
                added = self._parse_page(html)

                self.logger.info(
                    "offset=%d 파싱: +%d건 (누적 %d)",
                    offset, added, len(self.reviews),
                )

                if added == 0:
                    empty_streak += 1
                else:
                    empty_streak = 0

                if len(self.reviews) - self._flushed >= SAVE_INTERVAL:
                    self._flush_checkpoint()

                offset += PAGE_SIZE
                time.sleep(random.uniform(*REQUEST_PAUSE_RANGE))

            self.logger.info("수집 종료: 총 %d건", len(self.reviews))
        except Exception:  # noqa: BLE001 - 최종 안전망: 유실 방지 후 재raise
            self.logger.exception("크롤링 중 예외 발생 - 중간 저장 시도")
            self._flush_checkpoint()
            raise
        finally:
            if self.driver is not None:
                self.driver.quit()
                self.logger.info("브라우저 종료")

    def save_to_database(self) -> None:
        """수집한 리뷰를 ``reviews_tripadvisor.csv``로 저장한다."""
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"reviews_{self.SITE_NAME}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["rating", "date", "content"])
            writer.writeheader()
            writer.writerows(self.reviews)
        self.logger.info("저장 완료: %s (%d건)", path, len(self.reviews))

    # --------------------------------------------------------------
    # 내부 헬퍼
    # --------------------------------------------------------------
    def _require_driver(self) -> WebDriver:
        """드라이버가 초기화됐음을 보장하고 반환한다."""
        if self.driver is None:
            raise RuntimeError("start_browser()가 먼저 호출되어야 합니다.")
        return self.driver

    @retry(max_attempts=3, delay=2.0)
    def _fetch_page(self, url: str) -> str:
        """리뷰 페이지를 브라우저로 열고 렌더된 HTML을 반환한다."""
        driver = self._require_driver()
        driver.get(url)
        return driver.page_source

    def _parse_page(self, html: str) -> int:
        """한 페이지의 리뷰를 파싱해 self.reviews에 누적하고, 추가 건수를 반환.

        트립어드바이저 리스트 페이지(신형 React 구조) 기준:
          - 별점: svg[data-automation="bubbleRatingImage"]의 <title>
                  "풍선 5개 중 4.5" -> 4.5
          - 본문: span.yCeTE 중 <a>(제목 링크) 밖에 있는 가장 긴 텍스트
          - 날짜: "YYYY년 M월 D일 작성"(작성일) 우선, 없으면 div.jXCrq(방문월)
        중복은 (date, content) 조합으로 제거한다.
        """
        soup = BeautifulSoup(html, "html.parser")
        seen = {(r["date"], r["content"]) for r in self.reviews}
        before = len(self.reviews)

        # 별점 SVG를 앵커로 각 리뷰 카드를 순회. data-automation 속성은
        # 해시 클래스(UctUV 등)와 달리 잘 바뀌지 않아 기준점으로 안정적이다.
        for svg in soup.select('svg[data-automation="bubbleRatingImage"]'):
            rating = self._extract_rating(svg)
            if not rating:
                continue

            container = self._review_container(svg)
            if container is None:
                continue

            content = self._extract_content(container)
            if not content:
                continue

            date = self._extract_date(container)

            key = (date, content)
            if key in seen:
                continue
            seen.add(key)
            self.reviews.append(
                {"rating": rating, "date": date, "content": content}
            )

        return len(self.reviews) - before

    @staticmethod
    def _review_container(svg: Tag) -> Optional[Tag]:
        """별점 SVG에서 리뷰 카드 컨테이너로 거슬러 올라간다.

        본문(span.yCeTE)과 작성일("YYYY년 M월 D일 작성")을 함께 포함하는
        가장 가까운 조상을 리뷰 카드로 본다. 못 찾으면 None.
        """
        node: Tag = svg
        for _ in range(10):  # 카드 계층이 깊어 여유를 둠
            parent = node.parent
            if not isinstance(parent, Tag):
                return None
            node = parent
            has_body = node.find("span", class_="yCeTE") is not None
            has_written = re.search(
                r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일\s*작성", node.get_text()
            )
            if has_body and has_written:
                return node
        return None

    @staticmethod
    def _extract_rating(svg: Tag) -> str:
        """svg <title> '풍선 5개 중 4.5'에서 별점(4.5)을 추출."""
        title = svg.find("title")
        text = title.get_text() if isinstance(title, Tag) else ""
        m = re.search(r"중\s*(\d+(?:\.\d+)?)", text)
        return m.group(1) if m else ""

    @staticmethod
    def _extract_date(container: Tag) -> str:
        """작성일('YYYY년 M월 D일 작성') 우선, 없으면 방문월(div.jXCrq)."""
        text = container.get_text(" ", strip=True)
        m = re.search(r"(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)\s*작성", text)
        if m:
            return m.group(1)
        el = container.find("div", class_="jXCrq")
        if isinstance(el, Tag):
            return el.get_text(strip=True)
        return ""

    @staticmethod
    def _extract_content(container: Tag) -> str:
        """본문을 추출한다.

        제목과 본문 모두 span.yCeTE를 쓰지만, 제목은 <a>(상세 링크) 안에
        있으므로 링크 밖 yCeTE만 본문 후보로 삼고 그중 가장 긴 텍스트를 쓴다.
        """
        candidates: List[str] = []
        for span in container.find_all("span", class_="yCeTE"):
            if not isinstance(span, Tag):
                continue
            if span.find_parent("a") is not None:  # 제목(링크 안) 제외
                continue
            text = re.sub(r"\s+", " ", span.get_text(" ", strip=True)).strip()
            if text:
                candidates.append(text)
        return max(candidates, key=len) if candidates else ""

    def _flush_checkpoint(self) -> None:
        """지금까지 수집분을 체크포인트 CSV에 저장(크래시 대비)."""
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(
            self.output_dir, f"reviews_{self.SITE_NAME}.checkpoint.csv"
        )
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["rating", "date", "content"])
            writer.writeheader()
            writer.writerows(self.reviews)
        self._flushed = len(self.reviews)
        self.logger.info("중간 저장: %d건 -> %s", self._flushed, path)