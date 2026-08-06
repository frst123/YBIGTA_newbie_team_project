from fastapi import APIRouter, HTTPException

from app.responses.base_response import BaseResponse
from review_analysis.preprocessing.mongo_processor import (
    MongoReviewProcessor,
    RAW_COLLECTION,
)
from database.mongodb_connection import mongo_db

review = APIRouter(prefix="/review")

SITE_PROCESSORS = {
    "kakao": MongoReviewProcessor,
    "tripadvisor": MongoReviewProcessor,
    "tripdotcom": MongoReviewProcessor,
}


@review.post("/preprocess/{site_name}", status_code=200)
def preprocess_reviews(site_name: str):
    if site_name not in SITE_PROCESSORS:
        raise HTTPException(
            status_code=404,
            detail=f"지원하지 않는 사이트입니다: {site_name}",
        )

    if mongo_db[RAW_COLLECTION].count_documents({"site_name": site_name}) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"{site_name}의 원본 데이터가 없습니다.",
        )

    processor = SITE_PROCESSORS[site_name](site_name)
    processor.preprocess()
    processor.feature_engineering()
    saved = processor.save_to_database()

    return {
        "status": "success",
        "site_name": site_name,
        "processed_count": saved,
        "stats": processor.summary(),
    }