"""Safe, idempotent persistence for processed review records."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import create_engine, text


UPSERT_REVIEW = text("""
    INSERT INTO reviews (
        source_site, source_review_id, review_date, rating, content, tokens,
        text_len, token_count, emoji_count, year, month, weekday,
        content_hash, collected_at
    ) VALUES (
        :source_site, :source_review_id, :review_date, :rating, :content, :tokens,
        :text_len, :token_count, :emoji_count, :year, :month, :weekday,
        :content_hash, :collected_at
    )
    ON DUPLICATE KEY UPDATE
        rating = VALUES(rating), content = VALUES(content), tokens = VALUES(tokens),
        text_len = VALUES(text_len), token_count = VALUES(token_count),
        emoji_count = VALUES(emoji_count), year = VALUES(year), month = VALUES(month),
        weekday = VALUES(weekday), collected_at = VALUES(collected_at),
        updated_at = CURRENT_TIMESTAMP
""")


def to_database_record(row: dict[str, Any], collected_at: datetime) -> dict[str, Any]:
    """Map the reusable processor's CSV row to the fixed RDS schema."""
    site = str(row["site"])
    review_date = str(row["date"])
    content = str(row["content"])
    return {
        "source_site": site,
        "source_review_id": row.get("reviewId"),
        "review_date": review_date,
        "rating": float(row["rating"]),
        "content": content,
        "tokens": str(row.get("tokens", "")),
        "text_len": int(row["text_len"]),
        "token_count": int(row["token_count"]),
        "emoji_count": int(row["emoji_count"]),
        "year": int(row["year"]),
        "month": int(row["month"]),
        "weekday": int(row["weekday"]),
        "content_hash": hashlib.sha256(
            f"{site}\x1f{review_date}\x1f{content}".encode("utf-8")
        ).hexdigest(),
        "collected_at": collected_at,
    }


def upsert_reviews(database_url: str, rows: Iterable[dict[str, Any]]) -> int:
    """Upsert records in one transaction; credentials belong to collector_user."""
    collected_at = datetime.now(timezone.utc).replace(tzinfo=None)
    records = [to_database_record(row, collected_at) for row in rows]
    if not records:
        return 0

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(UPSERT_REVIEW, records)
    finally:
        engine.dispose()
    return len(records)
