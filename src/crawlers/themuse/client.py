"""
The Muse 공식 공개 API 클라이언트.

이용약관 (https://www.themuse.com/developers/api/v2/terms)
----------------------------------------------------------
- 미등록 기준 시간당 500건, 등록 시 시간당 3600건
- 응답 헤더 X-Ratelimit-Remaining으로 잔여 한도 실시간 확인 가능
- 상업적 재배포 및 제3자 채용 플랫폼 재게시 금지
- 출처 표기 및 원문 URL 링크 권장
  → source_name='themuse', original_url=refs.landing_page 필드로 자동 충족

인증: 선택사항 (api_key 파라미터 — 미등록 시 생략 가능)

수집 방식
---------
- ApiClientBase 기반 공식 API 호출 (HTML 크롤링 아님)
- 응답 JSON 원문을 RawJobPosting.raw_text 에 저장
- page 파라미터로 페이지네이션 (페이지당 20건)
- X-Ratelimit-Remaining ≤ 50 시 자동 대기

엔드포인트
----------
  GET https://www.themuse.com/api/public/jobs
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from src.crawlers.common.api_client_base import (
    ApiClientBase,
    RateLimitPolicy,
    parse_int_header,
)
from src.crawlers.themuse.search_queries import DEFAULT_BATCH_CATEGORIES
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_SOURCE_NAME = "themuse"
_COLLECTION = "raw_job_postings"

# 이용약관: 미등록 기준 시간당 500건 — 호출 간 최소 1초
_MIN_INTERVAL_SECONDS = 1.0
_RATE_LIMIT_THRESHOLD = 50

RESULTS_PER_PAGE = 20


class ThemuseApiClient(ApiClientBase):
    """The Muse public jobs API."""

    source_name = _SOURCE_NAME
    base_url = "https://www.themuse.com"
    api_path = "/api/public/jobs"
    collection_name = _COLLECTION
    timeout = (10.0, 30.0)
    rate_limit = RateLimitPolicy(
        min_interval_seconds=_MIN_INTERVAL_SECONDS,
        max_retries=3,
        backoff_base=2.0,
        header_remaining="X-Ratelimit-Remaining",
        header_reset="X-Ratelimit-Reset",
        header_threshold=_RATE_LIMIT_THRESHOLD,
        honor_429_reset_header=True,
    )

    def extract_jobs(self, page_data: dict[str, Any]) -> list[dict[str, Any]]:
        jobs = page_data.get("results") or []
        return jobs if isinstance(jobs, list) else []

    def extract_job_id(self, job: dict[str, Any]) -> str:
        return str(job.get("id") or "").strip()

    def extract_original_url(self, job: dict[str, Any], source_job_id: str) -> str:
        refs = job.get("refs") or {}
        landing = refs.get("landing_page")
        if landing:
            return str(landing)
        company = job.get("company") or {}
        short = company.get("short_name", "")
        job_slug = job.get("short_name", source_job_id)
        return f"{self.base_url}/jobs/{short}/{job_slug}"


_client = ThemuseApiClient()


# ---------------------------------------------------------------------------
# 공개 API (기존 시그니처 유지)
# ---------------------------------------------------------------------------

def fetch_themuse(
    category: str | None = None,
    level: str | None = None,
    location: str | None = None,
    crawl_date: str | None = None,
    save_path: str | None = None,
    page_count: int = 5,
    api_key: str | None = None,
) -> str:
    """
    The Muse 공식 API에서 조건에 맞는 채용공고를 가져와 raw_job_postings JSON으로 저장.
    """
    today = date.today().isoformat()
    crawl_date = crawl_date or today

    label_parts = []
    if category:
        label_parts.append(category.replace(" ", "_"))
    if level:
        label_parts.append(level.replace(" ", "_"))
    label = "_".join(label_parts) if label_parts else "all"

    logger.info(
        "[themuse] 수집 시작 — category=%s, level=%s, location=%s, page_count=%d",
        category, level, location, page_count,
    )

    saved_ids = get_saved_ids(_COLLECTION, save_path)
    raw_docs: list[dict[str, Any]] = []
    skipped = 0
    total_api_pages: int | None = None

    for page_num in range(1, page_count + 1):
        if total_api_pages is not None and page_num > total_api_pages:
            logger.info(
                "[themuse] API 페이지 상한(%d) 도달, 수집 완료 (category=%s)",
                total_api_pages, category,
            )
            break

        params: dict[str, Any] = {"page": page_num}
        if category:
            params["category"] = category
        if level:
            params["level"] = level
        if location:
            params["location"] = location
        if api_key:
            params["api_key"] = api_key

        # 모듈 _call_api 경유 — 테스트가 이 심볼을 패치한다
        page_data, rate_remaining, rate_reset = _call_api(params)
        if page_data is None:
            logger.error(
                "[themuse] API 호출 실패 — page=%d, category=%s", page_num, category,
            )
            break

        if total_api_pages is None:
            total_api_pages = page_data.get("page_count", 1)
            total_jobs = page_data.get("total", 0)
            logger.info(
                "[themuse] 응답 수신 — total=%d건, page_count=%d (category=%s)",
                total_jobs, total_api_pages, category,
            )

        jobs = _client.extract_jobs(page_data)
        if not jobs:
            logger.info("[themuse] 결과 없음 — page=%d, category=%s", page_num, category)
            break

        page_docs, page_skipped = _client.jobs_to_raw_dicts(jobs, saved_ids)
        for doc in page_docs:
            saved_ids.add((_SOURCE_NAME, doc["source_job_id"]))
        raw_docs.extend(page_docs)
        skipped += page_skipped

        logger.debug(
            "[themuse] page=%d 처리 완료 — 신규 누적: %d건, X-Ratelimit-Remaining: %s",
            page_num, len(raw_docs), rate_remaining,
        )

        waited = _client.maybe_wait_rate_limit(rate_remaining, rate_reset)
        if (
            not waited
            and page_num < min(page_count, total_api_pages or page_count)
        ):
            _client.sleep_interval()

    logger.info(
        "[themuse] 신규: %d건, 중복 건너뜀: %d건 (category=%s)",
        len(raw_docs), skipped, category,
    )

    if not raw_docs:
        return ""

    filename = f"themuse_{label}"
    saved = save_documents(
        documents=raw_docs,
        collection_name=_COLLECTION,
        filename=filename,
        crawl_date=crawl_date,
        base_dir=save_path,
    )
    return str(saved)


def run_themuse_batch(
    categories: list[str] | None = None,
    crawl_date: str | None = None,
    save_dir: str | None = None,
    page_count: int = 5,
    api_key: str | None = None,
) -> None:
    """categories를 순회하며 fetch_themuse를 반복 호출한다."""
    batch = categories if categories is not None else DEFAULT_BATCH_CATEGORIES
    total = len(batch)

    logger.info(
        "[themuse] 배치 시작 — %d개 카테고리, crawl_date=%s, page_count=%d",
        total,
        crawl_date or date.today().isoformat(),
        page_count,
    )

    for idx, cat in enumerate(batch, start=1):
        logger.info("[themuse] [%d/%d] 카테고리 처리: %s", idx, total, cat)
        try:
            fetch_themuse(
                category=cat,
                crawl_date=crawl_date,
                save_path=save_dir,
                page_count=page_count,
                api_key=api_key,
            )
        except Exception as exc:
            logger.error(
                "[themuse] 카테고리 처리 실패 (%s): %s", cat, exc, exc_info=True,
            )

    logger.info("[themuse] 배치 완료 — %d개 카테고리", total)


# ---------------------------------------------------------------------------
# 테스트·하위 호환 래퍼
# ---------------------------------------------------------------------------

def _call_api(
    params: dict[str, Any],
) -> tuple[dict[str, Any] | None, int | None, int | None]:
    """(page_data, rate_remaining, rate_reset) — 기존 테스트 시그니처 유지."""
    result = _client.call_api(params)
    return result.data, result.rate_remaining, result.rate_reset


def _parse_int_header(resp: Any, header_name: str) -> int | None:
    return parse_int_header(resp, header_name)
