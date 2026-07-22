"""카카오맵 리뷰 크롤러.

Selenium과 BeautifulSoup을 활용하여 카카오맵 PC 버전의 리뷰 데이터를 수집한다.
지정된 URL에 접속 후 '후기' 탭을 클릭하고, 무한 스크롤을 통해 리뷰를 수집하며
수집된 데이터는 결측치를 포함하여 규격화된 형식으로 정제 후 CSV 파일로 저장한다.
"""

from __future__ import annotations

import csv
import os
import random
import re
import time
from logging import Logger
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import InvalidSessionIdException

from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger

KAKAO_PLACE_URL: str = "https://place.map.kakao.com/18619553"

TARGET_REVIEWS: int = 500
SAVE_INTERVAL: int = 100
REQUEST_PAUSE_RANGE: tuple[float, float] = (1.5, 2.5)

USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

class KakaomapCrawler(BaseCrawler):
    """카카오맵 리뷰 수집을 담당하는 크롤러 클래스"""

    SITE_NAME: str = "kakao"

    def __init__(self, output_dir: str) -> None:
        super().__init__(output_dir)
        self.logger: Logger = setup_logger(
            log_file=os.path.join(output_dir, f"crawl_{self.SITE_NAME}.log")
        )
        self.driver: Optional[WebDriver] = None
        self.reviews: List[Dict[str, str]] = []
        self._flushed: int = 0

    def start_browser(self) -> None:
        """Chrome WebDriver를 초기화하고 실행한다."""
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--lang=ko-KR")
        options.add_argument(f"user-agent={USER_AGENT}")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(30)
        self.logger.info("카카오맵 크롤러 브라우저 기동 완료")

    def scrape_reviews(self) -> None:
        """무한 스크롤을 통해 리뷰 데이터를 수집한다."""
        self.start_browser()
        driver = self._require_driver()

        try:
            driver.get(KAKAO_PLACE_URL)
            time.sleep(5.0)

            self._click_review_tab()

            retry_count = 0
            max_retry = 10
            last_review_count = 0

            while len(self.reviews) < TARGET_REVIEWS and retry_count < max_retry:
                try:
                    html = driver.page_source
                except InvalidSessionIdException:
                    self.logger.error("브라우저 창이 닫혀 수집을 중단합니다.")
                    break
                    
                added = self._parse_page(html)

                self.logger.info(
                    "리뷰 파싱: +%d건 (누적 %d / 목표 %d)",
                    added, len(self.reviews), TARGET_REVIEWS
                )

                if len(self.reviews) >= TARGET_REVIEWS:
                    break

                self._scroll_to_load_more()
                
                if len(self.reviews) == last_review_count:
                    retry_count += 1
                    self.logger.warning("새로운 리뷰가 로드되지 않았습니다. 스크롤 재시도 (%d/%d)", retry_count, max_retry)
                else:
                    retry_count = 0  
                    last_review_count = len(self.reviews)

                if len(self.reviews) - self._flushed >= SAVE_INTERVAL:
                    self._flush_checkpoint()

                time.sleep(random.uniform(*REQUEST_PAUSE_RANGE))

            self.logger.info("수집 완료: 총 %d건", len(self.reviews))

        except Exception:
            self.logger.exception("크롤링 중 예외 발생 - 중간 저장 시도")
            self._flush_checkpoint()
            raise
        finally:
            if self.driver is not None:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.logger.info("브라우저 종료")

    def save_to_database(self) -> None:
        """수집된 리뷰 데이터를 CSV 파일로 저장한다."""
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"reviews_{self.SITE_NAME}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, 
                fieldnames=["rating", "date", "content"],
                extrasaction='ignore'
            )
            writer.writeheader()
            writer.writerows(self.reviews)
        self.logger.info("저장 완료: %s (%d건)", path, len(self.reviews))

    def _require_driver(self) -> WebDriver:
        if self.driver is None:
            raise RuntimeError("start_browser()가 먼저 호출되어야 합니다.")
        return self.driver

    def _click_review_tab(self) -> None:
        """페이지 내 '후기' 탭을 탐색하여 클릭한다."""
        driver = self._require_driver()
        
        try:
            wait = WebDriverWait(driver, 5)
            elements = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//*[contains(text(), '후기')]")))
            
            for elem in elements:
                try:
                    tag = elem.tag_name.lower()
                    parent_tag = elem.find_element(By.XPATH, "..").tag_name.lower()
                    
                    if tag in ['a', 'span'] or parent_tag in ['a']:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                        time.sleep(1.0) 
                        driver.execute_script("arguments[0].click();", elem)
                        self.logger.info("후기 탭 클릭 성공: %s", elem.text)
                        time.sleep(3.0) 
                        return
                except Exception:
                    continue
                    
        except Exception as e:
            self.logger.error("후기 탭 탐색 중 에러 발생: %s", e)
            
        self.logger.warning("후기 탭을 누르지 못했습니다. 현재 화면에서 진행합니다.")

    def _scroll_to_load_more(self) -> None:
        """현재 렌더링된 마지막 리뷰 요소로 스크롤하여 추가 로딩을 유도한다."""
        driver = self._require_driver()
        try:
            items = driver.find_elements(By.CSS_SELECTOR, "li:has(div.inner_review), ul.list_evaluation > li, div.area_review")
            
            if items:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'end'});", items[-1])
                time.sleep(1.0)
                
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
        except Exception:
            pass

    def _parse_page(self, html: str) -> int:
        """HTML 소스에서 리뷰 항목(작성자, 별점, 날짜, 본문)을 추출한다."""
        soup = BeautifulSoup(html, "html.parser")
        before = len(self.reviews)
        
        seen = {(r["date"], r.get("_user_name", ""), r["content"]) for r in self.reviews}

        review_containers = soup.select("li:has(div.inner_review)") or soup.select("ul.list_evaluation > li")

        for container in review_containers:
            user_el = container.select_one(".name_user")
            user_name = user_el.get_text(strip=True).replace("리뷰어 이름,", "").strip() if user_el else "익명"

            content = ""
            content_el = container.select_one("p.desc_review") or container.select_one("p.txt_comment")
            if content_el:
                more_span = content_el.select_one(".btn_more")
                if more_span:
                    more_span.extract()
                
                content = content_el.get_text(strip=True)
                content = content.replace('\n', ' ').replace('\r', ' ')

            rating = "5"
            rating_el = container.select_one("span.starred_grade") or container.select_one("span.ico_star")
            if rating_el:
                num_txt = re.search(r"(\d+(?:\.\d+)?)", rating_el.get_text())
                if num_txt:
                    val = float(num_txt.group(1))
                    rating = f"{int(val)}" if val.is_integer() else f"{val:.1f}"

            date_el = container.select_one("span.txt_date") or container.select_one("span.time_write")
            raw_date = date_el.get_text(strip=True) if date_el else ""
            date = raw_date
            
            if raw_date:
                match = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', raw_date)
                if match:
                    y, m, d = match.groups()
                    date = f"{y}년 {int(m)}월 {int(d)}일"

            key = (date, user_name, content)
            if key in seen:
                continue
            seen.add(key)

            self.reviews.append({
                "_user_name": user_name,
                "rating": rating,
                "date": date,
                "content": content
            })

        return len(self.reviews) - before

    def _flush_checkpoint(self) -> None:
        """크래시 발생에 대비하여 현재까지 수집된 데이터를 체크포인트로 저장한다."""
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, f"reviews_{self.SITE_NAME}.checkpoint.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, 
                fieldnames=["rating", "date", "content"], 
                extrasaction='ignore'
            )
            writer.writeheader()
            writer.writerows(self.reviews)
        self._flushed = len(self.reviews)
        self.logger.info("중간 저장: %d건 -> %s", self._flushed, path)