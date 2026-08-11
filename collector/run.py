"""Run existing crawlers/processors and load their results into private RDS."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Type

from collector.storage import upsert_reviews
from review_analysis.crawling.base_crawler import BaseCrawler
from review_analysis.crawling.kakaomap_crawler import KakaomapCrawler
from review_analysis.crawling.tripadvisor_crawler import TripadvisorCrawler
from review_analysis.crawling.tripdotcom_crawler import TripdotcomCrawler
from review_analysis.preprocessing.kakao_processor import KakaoProcessor
from review_analysis.preprocessing.tripadvisor_processor import TripadvisorProcessor
from review_analysis.preprocessing.tripdotcom_processor import TripdotcomProcessor


CRAWLERS: dict[str, Type[BaseCrawler]] = {
    "kakao": KakaomapCrawler,
    "tripadvisor": TripadvisorCrawler,
    "tripdotcom": TripdotcomCrawler,
}
PROCESSORS = {
    "kakao": KakaoProcessor,
    "tripadvisor": TripadvisorProcessor,
    "tripdotcom": TripdotcomProcessor,
}


def crawl_site(site: str, work_dir: Path) -> None:
    """Reuse the team's crawler implementation for one site."""
    crawler = CRAWLERS[site](str(work_dir))
    crawler.scrape_reviews()
    crawler.save_to_database()


def process_site(site: str, work_dir: Path) -> list[dict[str, str]]:
    """Reuse the team's processor after every source CSV has been refreshed."""
    raw_path = work_dir / f"reviews_{site}.csv"
    processor = PROCESSORS[site](str(raw_path), str(work_dir))
    processor.preprocess()
    processor.feature_engineering()
    processor.save_to_database()

    processed_path = work_dir / f"preprocessed_reviews_{site}.csv"
    with processed_path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled review collector")
    parser.add_argument("--work-dir", default="/data", help="persistent CSV/log directory")
    configured_sites = os.getenv("COLLECTOR_SITES", "kakao tripadvisor tripdotcom").split()
    parser.add_argument(
        "--sites",
        nargs="+",
        choices=CRAWLERS,
        default=configured_sites,
        help="sites to crawl (default: COLLECTOR_SITES or all sites)",
    )
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="use existing reviews_<site>.csv files and only preprocess/load them",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must use the collector_user RDS credential.")

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    # Processors fit one shared TF-IDF corpus, so refresh all raw CSVs before
    # processing any individual site.
    if not args.skip_crawl:
        for site in args.sites:
            crawl_site(site, work_dir)

    all_rows: list[dict[str, str]] = []
    for site in args.sites:
        all_rows.extend(process_site(site, work_dir))

    saved = upsert_reviews(database_url, all_rows)
    print(f"RDS upsert completed: {saved} processed reviews")


if __name__ == "__main__":
    main()
