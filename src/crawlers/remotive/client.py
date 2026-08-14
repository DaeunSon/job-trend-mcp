"""
Remotive 공식 공개 API 클라이언트.

이용약관 (https://remotive.com/api-documentation)
-------------------------------------------------
- 요청 빈도: 분당 2회 초과 금지, 하루 최대 4회 권장
- 출처 표기: Remotive 출처와 원문 URL을 반드시 남길 것
- 재게시 금지: 제3자 채용 사이트 재게시 용도 금지

인증: 불필요

수집 방식
---------
- ApiClientBase 기반 공식 API 호출 (HTML 크롤링 아님)
- 단일 응답으로 전체 목록 반환 (페이지네이션 없음)
- 배치 시 카테고리 간 최소 35초 간격 (분당 2회 제한)

엔드포인트
----------
  GET https://remotive.com/api/remote-jobs
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from src.crawlers.common.api_client_base import ApiClientBase, RateLimitPolicy
from src.crawlers.remotive.search_queries import DEFAULT_BATCH_CATEGORIES
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_SOURCE_NAME = "remotive"
_COLLECTION = "raw_job_postings"

# 분당 2회 제한 준수 — 호출 간 최소 35초
_MIN_INTERVAL_SECONDS = 35

RESULTS_PER_PAGE = 20


class RemotiveApiClient(ApiClientBase):
    """Remotive remote-jobs API."""

    source_name = _SOURCE_NAME
    base_url = "https://remotive.com"
    api_path = "/api/remote-jobs"
    collection_name = _COLLECTION
    timeout = (10.0, 30.0)
    rate_limit = RateLimitPolicy(
        min_interval_seconds=_MIN_INTERVAL_SECONDS,
        max_retries=3,
        backoff_base=2.0,
        status_backoff_multipliers={403: 3.0, 429: 3.0},
    )

    def extract_jobs(self, page_data: dict[str, Any]) -> list[dict[str, Any]]:
        jobs = page_data.get("jobs") or []
        return jobs if isinstance(jobs, list) else []

    def extract_job_id(self, job: dict[str, Any]) -> str:
        return str(job.get("id") or "").strip()

    def extract_original_url(self, job: dict[str, Any], source_job_id: str) -> str:
        return (job.get("url") or "").strip() or (
            f"{self.base_url}/remote-jobs/{source_job_id}"
        )


_client = RemotiveApiClient()


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def fetch_remotive(
    category: str | None = None,
    search: str | None = None,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_jobs: int | None = None,
) -> str:
    """
    Remotive 공식 API에서 category/search 조건 공고를 가져와 저장한다.
    API는 단일 응답으로 전체를 반환한다 (페이지네이션 없음).
    """
    today = date.today().isoformat()
    crawl_date = crawl_date or today

    params: dict[str, str] = {}
    if category:
        params["category"] = category
    if search:
        params["search"] = search

    label = category or search or "all"
    logger.info(
        "[remotive] 수집 시작 — category=%s, search=%s, max_jobs=%s",
        category, search, max_jobs,
    )

    # 모듈 _call_api 경유 — 테스트가 이 심볼을 패치한다
    raw_data = _call_api(params)
    if raw_data is None:
        logger.error("[remotive] API 호출 실패 — category=%s, search=%s", category, search)
        return ""

    jobs = _client.extract_jobs(raw_data)
    job_count = raw_data.get("job-count", len(jobs))
    logger.info("[remotive] 응답 수신 — %d건 (category=%s)", job_count, category)

    saved_ids = get_saved_ids(_COLLECTION, save_path)
    raw_docs, skipped = _client.jobs_to_raw_dicts(
        jobs, saved_ids, max_jobs=max_jobs,
    )
    if max_jobs is not None and len(raw_docs) >= max_jobs:
        logger.info(
            "[remotive] max_jobs=%d 도달, 수집 중단 (category=%s)",
            max_jobs, category,
        )

    logger.info(
        "[remotive] 신규: %d건, 중복 건너뜀: %d건 (category=%s)",
        len(raw_docs), skipped, category,
    )

    if not raw_docs:
        return ""

    filename = f"remotive_{label}"
    saved = save_documents(
        documents=raw_docs,
        collection_name=_COLLECTION,
        filename=filename,
        crawl_date=crawl_date,
        base_dir=save_path,
    )
    return str(saved)


def run_remotive_batch(
    categories: list[str] | None = None,
    crawl_date: str | None = None,
    save_dir: str | None = None,
    max_jobs: int | None = None,
) -> None:
    """
    categories를 순회하며 fetch_remotive를 반복 호출한다.
    이용약관 준수 — 호출 간 최소 35초 간격.
    """
    batch = categories if categories is not None else DEFAULT_BATCH_CATEGORIES
    total = len(batch)

    logger.info(
        "[remotive] 배치 시작 — %d개 카테고리, crawl_date=%s%s",
        total,
        crawl_date or date.today().isoformat(),
        f", max_jobs={max_jobs}" if max_jobs else "",
    )

    for idx, cat in enumerate(batch, start=1):
        logger.info("[remotive] [%d/%d] 카테고리 처리: %s", idx, total, cat)
        try:
            fetch_remotive(
                category=cat,
                crawl_date=crawl_date,
                save_path=save_dir,
                max_jobs=max_jobs,
            )
        except Exception as exc:
            logger.error("[remotive] 카테고리 처리 실패 (%s): %s", cat, exc, exc_info=True)

        if idx < total:
            logger.debug(
                "[remotive] %ds 대기 (rate limit 준수)",
                _client.rate_limit.min_interval_seconds,
            )
            _client.sleep_interval()

    logger.info("[remotive] 배치 완료 — %d개 카테고리", total)


def _call_api(params: dict[str, str]) -> dict[str, Any] | None:
    """기존 테스트 시그니처 유지 — 성공 시 dict, 실패 시 None."""
    return _client.call_api(params).data
