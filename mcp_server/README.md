# YBIGTA Review MCP Server

경복궁 리뷰 크롤러/전처리 결과를 Agent가 안전하게 조회하도록 제공하는 읽기 전용 MCP 서버입니다.
원본 프로젝트와 분리된 독립 프로젝트이며 원본 GitHub 저장소에는 어떤 변경도 하지 않습니다.

## 확인한 데이터 계약

원본 Kakao 크롤러 출력:

| 컬럼 | 의미 |
| --- | --- |
| rating | 1~5점 평점 |
| date | 크롤러가 수집한 작성일 문자열 |
| content | 리뷰 본문 |

전처리 결과 `preprocessed_reviews_kakao.csv`:

| 컬럼 | 타입 | MCP 사용 여부 |
| --- | --- | --- |
| site | string | 필터/출처 |
| date | YYYY-MM-DD | 기간 검색/정렬 |
| rating | float | 평점 필터/집계 |
| content | string | 검색/응답 |
| tokens | 공백 구분 문자열 | 키워드 집계 |
| text_len | int | 평균 길이 집계 |
| token_count | int | 응답 |
| emoji_count | int | 응답 |
| year/month/weekday | int | DB 인덱스 후보 |
| tfidf_svd_00~15 | float | 현재 Tool에서는 노출하지 않음 |

현재 포함된 Kakao 전처리 CSV는 407행입니다. TF-IDF/SVD 값은 검색 결과를 불필요하게
키우므로 MCP 응답에서 제외했습니다.

## 구조

```text
MCP Tool -> ReviewService -> ReviewRepository -> CSV (현재)
                                      \-----> RDS (DB 확정 후)
```

```text
src/review_mcp/
├─ server.py
├─ app.py
├─ auth.py
├─ schemas.py
├─ services/review_service.py
└─ repositories/
   ├─ base.py
   ├─ csv_repository.py
   ├─ rds_repository.py
   └─ factory.py
```

Tool과 Service는 저장소 종류를 모릅니다. `DATA_BACKEND=rds`로 변경하면
`RdsReviewRepository`만 사용되므로 DB 연결 시 다른 계층을 수정하지 않습니다.

## MCP Tools

### `list_review_sources()`

사용 가능한 사이트, 행 수, 최초/최근 리뷰일, 마지막 적재 시간을 반환합니다.

### `get_latest_reviews(site="kakao", limit=10)`

- `site`: `kakao | tripadvisor | tripdotcom`
- `limit`: 1~50

### `search_reviews(...)`

- `site`: 허용된 사이트 enum
- `keyword`: 1~100자
- `start_date`, `end_date`: ISO 날짜
- `min_rating`, `max_rating`: 1~5
- `limit`: 1~100
- `offset`: 0~10,000

Raw SQL은 받지 않으며 모든 범위는 Pydantic으로 검증합니다.

### `aggregate_review_stats(...)`

`group_by=month|year|weekday` 기준 리뷰 수, 평균 평점, 평균 본문 길이와
긍정(4~5), 중립(3), 부정(1~2) 개수를 반환합니다.

### `get_top_review_keywords(...)`

전처리된 `tokens`에서 상위 키워드와 문서 출현 비율을 반환합니다.
`limit`은 1~30입니다.

모든 결과에는 `backend`, 적용 필터, 반환/전체 행 수, 생성 시각,
분석 행 제한으로 잘렸는지 여부가 포함됩니다.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
```

`.env`의 `MCP_AUTH_TOKEN`에 실제 랜덤 토큰을 넣습니다.

stdio/Inspector:

```powershell
mcp dev src/review_mcp/server.py
```

Streamable HTTP:

```powershell
uvicorn review_mcp.app:app --host 0.0.0.0 --port 8000
```

- Health: `GET /health`
- MCP endpoint: `POST /mcp`
- MCP 요청 헤더: `Authorization: Bearer <MCP_AUTH_TOKEN>`

Next.js Route Handler에서만 MCP를 호출하고 토큰을 브라우저로 보내지 않습니다.

## RDS 연결 시 조원에게 받을 값

1. MySQL RDS private endpoint, port, database name
2. `SELECT`만 가능한 `mcp_user`
3. MCP EC2 Security Group에서 RDS 3306으로 연결 가능한지
4. 실제 테이블명
5. 아래 canonical 컬럼 존재 여부

```text
id, site, date, rating, content, tokens,
text_len, token_count, emoji_count, collected_at
```

DB 스키마가 다르면 `src/review_mcp/repositories/rds_repository.py`의 Table 선언과
`_to_record()` 매핑만 수정합니다. 이후:

```dotenv
DATA_BACKEND=rds
DATABASE_URL=mysql+pymysql://mcp_user:...@private-endpoint:3306/reviews
REVIEW_TABLE=preprocessed_reviews
```

DB 계정에는 `SELECT`만 부여하고, 애플리케이션은 SQLAlchemy parameterized query만
사용합니다. `execute_sql` Tool은 제공하지 않습니다.

권장 인덱스:

```sql
CREATE INDEX ix_reviews_site_date ON preprocessed_reviews (site, date);
CREATE INDEX ix_reviews_site_rating_date
    ON preprocessed_reviews (site, rating, date);
```

## HTTP 보안

- MCP endpoint는 Bearer token 필수
- `MCP_AUTH_TOKEN`, `DATABASE_URL`은 환경변수로만 주입
- 내부 8000 포트를 인터넷에 직접 공개하지 않고 Nginx 뒤에 배치
- Security Group은 80/443만 공개하고 8000/3306은 공개하지 않음
- `MCP_ALLOWED_HOSTS`에 실제 도메인을 명시하여 DNS rebinding 차단
- RDS 계정은 read-only
- 조회 행 수와 분석 행 수 제한

## 테스트

```powershell
python -m unittest discover -s tests -v
```

테스트는 검색 필터/페이지네이션, 월별 집계, 키워드 집계,
MCP Tool 목록과 실제 Tool 호출을 확인합니다.

## 원본 코드와의 관계

스키마와 데이터 흐름은
`review_analysis/crawling/kakaomap_crawler.py`,
`review_analysis/preprocessing/common_processor.py`,
`database/preprocessed_reviews_kakao.csv`를 확인해 맞췄습니다.
크롤링/전처리/DB 적재는 AWS·DB 담당자의 영역이고 이 프로젝트는 적재된 데이터를
조회하는 MCP 계층만 담당합니다.
