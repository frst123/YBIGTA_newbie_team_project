from datetime import datetime

from collector.storage import to_database_record


def test_database_record_has_stable_site_scoped_hash() -> None:
    row = {
        "site": "kakao",
        "date": "2026-08-10",
        "rating": "5",
        "content": "좋아요",
        "tokens": "좋다",
        "text_len": "3",
        "token_count": "1",
        "emoji_count": "0",
        "year": "2026",
        "month": "8",
        "weekday": "0",
    }

    first = to_database_record(row, datetime(2026, 8, 11))
    second = to_database_record(row, datetime(2026, 8, 12))

    assert first["content_hash"] == second["content_hash"]
    assert first["source_site"] == "kakao"
    assert first["rating"] == 5.0
