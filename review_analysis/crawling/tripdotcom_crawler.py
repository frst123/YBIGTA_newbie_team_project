import os
import csv
import time
import random
import requests
from functools import wraps
from typing import Callable, Any, Optional, TypeVar, cast, Dict
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

# BaseCrawler
from review_analysis.crawling.base_crawler import BaseCrawler

F = TypeVar('F', bound=Callable[..., Any])

def retry(max_attempts: int = 3, delay: float = 2.0) -> Callable[[F], F]:
    """
    네트워크 요청 실패 시 재시도 수행을 위한 데코레이터.
    :param max_attempts: 최대 재시도 횟수
    :param delay: 재시도 간 대기 시간 (초)
    :return: 데코레이터 함수
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (TimeoutException, WebDriverException, requests.exceptions.RequestException) as exc:
                    last_exc = exc
                    print(f"[재시도] {func.__name__} 에러 ({attempt}/{max_attempts}): {exc}")
                    time.sleep(delay * attempt)
            assert last_exc is not None
            raise last_exc
        return cast(F, wrapper)
    return decorator


class TripdotcomCrawler(BaseCrawler):
    """
    Trip.com 리뷰 크롤러
    Selenium을 사용하여 인증 토큰을 확보 => Trip.com API를 통해 리뷰 데이터를 수집
    """
    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        self.output_path = os.path.join(self.output_dir, "reviews_tripdotcom.csv")
        
        # 클래스 내부에 고정된 크롤링 대상 설정
        self.target_url = "https://kr.trip.com/travel-guide/attraction/seoul/gyeongbokgung-palace-78910/"
        self.api_url = "https://kr.trip.com/restapi/soa2/19707/getReviewSearch"
        self.sight_id = 78910
        
        self.session = requests.Session()
        self.reviews: Dict[int, Dict[str, Any]] = {}
        self._fingerprint: Optional[str] = None

    def start_browser(self) -> None:
        """
        Selenium 브라우저 세션 초기화
        인증 토큰 확보 및 세션 쿠키 설정
        """
        options = Options()
        options.add_argument("window-size=1920x1080")
        options.add_argument("lang=ko_KR")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        try:
            print("1. 브라우저 세션 초기화 및 인증 토큰 확보 중...")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
            })

            driver.get(self.target_url)
            time.sleep(5) 
            
            # 인증 토큰 및 세션 쿠키 확보
            for cookie in driver.get_cookies():
                self.session.cookies.set(cookie['name'], cookie['value'])
                if "fxpcql" in cookie['name'].lower():
                    self._fingerprint = cookie['value']

            user_agent = driver.execute_script("return navigator.userAgent;")
            self.session.headers.update({
                "User-Agent": user_agent,
                "Origin": "https://kr.trip.com",
                "Content-Type": "application/json;charset=UTF-8",
            })
        finally:
            try:
                driver.quit()
            except NameError:
                pass

    def _build_request_url(self) -> str:
        """
        API 요청 URL을 구성하고, 인증 토큰과 trace ID를 쿼리 파라미터에 추가
        :return: 완전한 API 요청 URL
        """
        parts = urlsplit(self.api_url)
        query = dict(parse_qsl(parts.query))
        fingerprint = self._fingerprint or "default_fingerprint"
        trace_id = f"{fingerprint}-{int(time.time() * 1000)}-{random.randint(1000000, 9999999)}"
        query["_fxpcqlniredt"] = fingerprint
        query["x-traceID"] = trace_id
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    @retry(max_attempts=3, delay=2.0)
    def _request_api(self, url: str, payload: dict) -> dict:
        """
        API 요청을 수행하고 JSON 응답을 반환
        :param url: API 요청 URL
        :param payload: POST 요청에 사용할 JSON 페이로드
        :return: API 응답 JSON 데이터"""
        response = self.session.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()

    def scrape_reviews(self) -> None:
        """데이터를 실제로 수집하는 메서드 (main.py에서 첫 번째로 호출됨)
        ko-KR 리뷰를 우선적으로 수집하며, 필요 시 다른 언어도 추가 가능
        중간저장 기능 추가 완료!"""
        self.start_browser()
        locales = ["ko-KR"]
        
        print(f"2. 한국어 리뷰 크롤링 시작!! (저장 예정 경로: {self.output_path})")

        for locale in locales:
            page_index = 1
            print(f"\n[{locale}] 언어 리뷰 수집 시작")
            
            while True:
                payload = {
                    "poiId": self.sight_id,
                    "locale": locale,
                    "pageSize": 50,
                    "pageIndex": page_index,
                    "commentTagId": 0,
                    "head": {
                        "cid": "09034160114304763238",
                        "syscode": "09",
                        "lang": "01",
                        "extension": [
                            {"name": "locale", "value": locale},
                            {"name": "platform", "value": "Online"}
                        ]
                    }
                }
                
                try:
                    request_url = self._build_request_url()
                    data = self._request_api(request_url, payload)
                    review_list = data.get("reviewList", [])
                    
                    if not review_list:
                        print(f"[{locale}] 더 이상 반환할 리뷰가 없습니다.")
                        break
                        
                    for item in review_list:
                        content = item.get("translateContent") or item.get("content", "")
                        if content:
                            rev_id = item.get("reviewId")
                            self.reviews[rev_id] = {
                                "reviewId": rev_id,
                                "language": locale,
                                "rating": item.get("userRating", 0),
                                "date": item.get("createTimeDesc", ""),
                                "content": content
                            }
                            
                    print(f"  - [{locale}] Page {page_index} 완료 | 전체 누적: {len(self.reviews)}건")
                    
                    
                    if page_index % 5 == 0:
                        self.save_to_database()
                    
                    page_index += 1
                    time.sleep(1.5 + random.uniform(0, 1.0))
                    
                except Exception as e:
                    print(f"[{locale}] 수집 중 에러 발생: {e}")
                    break

    def save_to_database(self) -> None:
        """수집된 데이터를 최종적으로 저장하는 메서드 (main.py에서 두 번째로 호출됨)"""
        if not self.reviews:
            print("[경고] 저장할 리뷰 데이터가 없습니다.")
            return
            
        try:
            with open(self.output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["reviewId", "language", "rating", "date", "content"])
                writer.writeheader()
                writer.writerows(self.reviews.values())
            print(f"[저장 성공] 총 {len(self.reviews)}건의 데이터가 {self.output_path}에 안전하게 저장되었습니다.")
        except OSError as e:
            print(f"[저장 실패] 파일 쓰기 중 오류가 발생했습니다: {e}")
            raise e