"""
Arbeitnow 공식 공개 API 클라이언트.

이용약관 (응답 meta.terms / https://www.arbeitnow.com/blog/job-board-api)
-----------------------------------------------------------------------
- 남용 금지 — 분당 수 회 수준으로 보수적으로 호출 (호출 간 최소 20초)
- 백링크 의무: arbeitnow.com 출처 표기
- 재게시 금지: 제3자 채용 사이트 재게시 용도 금지
- API는 as-is 제공

인증: 불필요

수집 방식
---------
- ApiClientBase 기반 공식 API 호출 (HTML 크롤링 아님)
- 페이지네이션: ?page=N , 응답 links.next 가 null 이면 종료
  (links.last / 총 페이지 수는 제공되지 않음)

엔드포인트
----------
  GET https://www.arbeitnow.com/api/job-board-api
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from src.crawlers.common.api_client_base import ApiClientBase, RateLimitPolicy
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_SOURCE_NAME = "arbeitnow"
_COLLECTION = "raw_job_postings"

# 이용약관: 남용 금지 — 호출 간 20초 ≈ 분당 3회
_MIN_INTERVAL_SECONDS = 20
_MAX_CONSECUTIVE_FAILURES = 3

RESULTS_PER_PAGE = 100


class ArbeitnowApiClient(ApiClientBase):
    """Arbeitnow job-board API."""

    source_name = _SOURCE_NAME
    base_url = "https://www.arbeitnow.com"
    api_path = "/api/job-board-api"
    collection_name = _COLLECTION
    timeout = (10.0, 60.0)  # 응답이 클 수 있어 read timeout 여유
    allow_redirects = True
    rate_limit = RateLimitPolicy(
        min_interval_seconds=_MIN_INTERVAL_SECONDS,
        max_retries=3,
        backoff_base=2.0,
        status_backoff_multipliers={403: 3.0, 429: 3.0, 503: 3.0},
    )

    def extract_jobs(self, page_data: dict[str, Any]) -> list[dict[str, Any]]:
        jobs = page_data.get("data") or []
        return jobs if isinstance(jobs, list) else []

    def extract_job_id(self, job: dict[str, Any]) -> str:
        return str(job.get("slug") or "").strip()

    def extract_original_url(self, job: dict[str, Any], source_job_id: str) -> str:
        return (job.get("url") or "").strip() or (
            f"{self.base_url}/jobs/{source_job_id}"
        )

    def has_next_page(self, page_data: dict[str, Any]) -> bool:
        links = page_data.get("links") or {}
        return bool(links.get("next"))


_client = ArbeitnowApiClient()


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def fetch_arbeitnow(
    page: int = 1,
    crawl_date: str | None = None,
    save_path: str | None = None,
) -> str:
    """한 페이지를 수집·저장한다."""
    saved_path, _has_next = _fetch_page(
        page=page,
        crawl_date=crawl_date,
        save_path=save_path,
    )
    return saved_path


def run_arbeitnow_batch(
    crawl_date: str | None = None,
    save_dir: str | None = None,
    max_pages: int | None = None,
) -> None:
    """
    links.next 를 따라 페이지를 순회한다.
    검색어·카테고리 필터가 없는 API이므로 페이지 번호만 순회한다.
    """
    logger.info(
        "[arbeitnow] 배치 시작 — crawl_date=%s, max_pages=%s",
        crawl_date or date.today().isoformat(),
        max_pages,
    )

    page = 1
    consecutive_failures = 0

    while True:
        if max_pages is not None and page > max_pages:
            logger.info("[arbeitnow] max_pages=%d 도달, 배치 종료", max_pages)
            break

        logger.info("[arbeitnow] [%d] 페이지 처리", page)
        try:
            _saved_path, has_next = _fetch_page(
                page=page,
                crawl_date=crawl_date,
                save_path=save_dir,
            )
        except Exception as exc:
            consecutive_failures += 1
            logger.error(
                "[arbeitnow] 페이지 처리 실패 (page=%d): %s",
                page, exc, exc_info=True,
            )
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                logger.error("[arbeitnow] 연속 실패 한도 초과, 배치 중단")
                break
            page += 1
            _client.sleep_interval()
            continue

        if has_next is None:
            consecutive_failures += 1
            logger.error(
                "[arbeitnow] 페이지 %d API 실패 (%d/%d)",
                page, consecutive_failures, _MAX_CONSECUTIVE_FAILURES,
            )
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                logger.error("[arbeitnow] 연속 실패 한도 초과, 배치 중단")
                break
            page += 1
            _client.sleep_interval()
            continue

        consecutive_failures = 0

        if not has_next:
            logger.info("[arbeitnow] links.next 없음 — page=%d에서 배치 종료", page)
            break

        page += 1
        if max_pages is not None and page > max_pages:
            logger.info("[arbeitnow] max_pages=%d 도달, 배치 종료", max_pages)
            break

        logger.debug(
            "[arbeitnow] %ds 대기 (rate limit 준수)",
            _client.rate_limit.min_interval_seconds,
        )
        _client.sleep_interval()

    logger.info("[arbeitnow] 배치 완료 — 마지막 page=%d", page)


# ---------------------------------------------------------------------------
# 내부
# ---------------------------------------------------------------------------

def _fetch_page(
    page: int,
    crawl_date: str | None,
    save_path: str | None,
) -> tuple[str, bool | None]:
    """
    한 페이지를 수집·저장한다.

    Returns
    -------
    (saved_path, has_next)
      has_next : links.next 존재 여부. API 실패 시 None.
    """
    today = date.today().isoformat()
    crawl_date = crawl_date or today

    if page < 1:
        logger.error("[arbeitnow] page는 1 이상이어야 함: %s", page)
        return "", None

    logger.info("[arbeitnow] 수집 시작 — page=%d", page)

    # 모듈 _call_api 경유 — 테스트가 이 심볼을 패치한다
    raw_data = _call_api({"page": page})
    if raw_data is None:
        logger.error("[arbeitnow] API 호출 실패 — page=%d", page)
        return "", None

    raw_jobs = raw_data.get("data")
    if raw_jobs is not None and not isinstance(raw_jobs, list):
        logger.error("[arbeitnow] 응답 data 필드가 리스트가 아님 — page=%d", page)
        return "", None

    jobs = _client.extract_jobs(raw_data)
    has_next = _client.has_next_page(raw_data)
    meta = raw_data.get("meta") or {}
    logger.info(
        "[arbeitnow] 응답 수신 — page=%d, jobs=%d, has_next=%s, per_page=%s",
        page, len(jobs), has_next, meta.get("per_page"),
    )

    if not jobs:
        logger.info("[arbeitnow] 결과 없음 — page=%d", page)
        return "", False

    saved_ids = get_saved_ids(_COLLECTION, save_path)
    raw_docs, skipped = _client.jobs_to_raw_dicts(jobs, saved_ids)

    logger.info(
        "[arbeitnow] 신규: %d건, 중복 건너뜀: %d건 (page=%d, has_next=%s)",
        len(raw_docs), skipped, page, has_next,
    )

    if not raw_docs:
        return "", has_next

    filename = f"arbeitnow_page_{page}"
    saved = save_documents(
        documents=raw_docs,
        collection_name=_COLLECTION,
        filename=filename,
        crawl_date=crawl_date,
        base_dir=save_path,
    )
    return str(saved), has_next


def _call_api(params: dict[str, Any]) -> dict[str, Any] | None:
    """기존 테스트 시그니처 유지."""
    return _client.call_api(params).data
