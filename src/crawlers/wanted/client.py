"""
원티드 크롤러.

주요 함수
---------
fetch_wanted()         — tag_type_ids(직무 카테고리) 하나에 대한 공고를 수집해
                         raw_job_postings 구조의 JSON으로 저장
run_wanted_batch()     — job_functions 목록을 순회하며 fetch_wanted를 반복 호출

수집 방식 — 내부 JSON API 직접 호출 (2026-07-27 확인)
-----------------------------------------------------
  목록 API  : GET /api/v4/jobs
  상세 API  : GET /api/v4/jobs/{job_id}
"""
from __future__ import annotations

import logging
import random
import time
from datetime import date
from typing import Any

from src.crawlers.common import (
    BROWSER_USER_AGENT,
    JsonApiCrawler,
    PageCursor,
    build_crawl_filename,
    is_blocked,
)
from src.crawlers.wanted.search_queries import get_tag_ids_for_function
from src.models.schemas import RawJobPosting
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.wanted.co.kr"
_JOBS_API = "/api/v4/jobs"
_DETAIL_URL = "https://www.wanted.co.kr/wd/{job_id}"
_RESULTS_PER_PAGE = 20
_MAX_PAGES = 100
_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "wanted"


# ---------------------------------------------------------------------------
# 내부 크롤러 클래스
# ---------------------------------------------------------------------------

class _WantedCrawler(JsonApiCrawler):
    """원티드 내부 JSON API를 직접 호출하는 크롤러."""

    source_name = _SOURCE_NAME
    page_size = _RESULTS_PER_PAGE
    default_max_pages = _MAX_PAGES

    def __init__(self) -> None:
        super().__init__(
            source_name=_SOURCE_NAME,
            base_url=_BASE_URL,
            user_agent=BROWSER_USER_AGENT,
            rate_limit_min=0.5,
            rate_limit_max=1.5,
        )
        self._session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.wanted.co.kr/wdlist",
                "Origin": "https://www.wanted.co.kr",
                "wanted-user-country": "KR",
                "wanted-user-language": "ko",
                "Connection": "keep-alive",
            }
        )

    # ------------------------------------------------------------------
    # 목록 / 상세 (테스트 호환 공개 메서드)
    # ------------------------------------------------------------------

    def fetch_jobs_page(
        self,
        tag_type_ids: list[int],
        offset: int = 0,
        limit: int = _RESULTS_PER_PAGE,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {
            "country": "kr",
            "job_sort": "job.latest_order",
            "years": -1,
            "locations": "all",
            "limit": limit,
            "offset": offset,
        }
        if tag_type_ids:
            params["tag_type_ids"] = ",".join(str(i) for i in tag_type_ids)

        logger.info(
            "[wanted] 목록 API 요청 (tag_ids=%s, offset=%d)",
            tag_type_ids, offset,
        )
        return self.get_json(
            _BASE_URL + _JOBS_API,
            params=params,
            log_label=f"목록 offset={offset}",
        )

    def extract_job_ids(self, page_data: dict[str, Any]) -> list[int]:
        ids: list[int] = []
        for item in page_data.get("data", []):
            job_id = item.get("id")
            if job_id is not None:
                ids.append(int(job_id))
        return ids

    def has_next_page(self, page_data: dict[str, Any]) -> bool:
        return bool(page_data.get("links", {}).get("next"))

    def fetch_job_detail(self, job_id: int) -> dict[str, Any] | None:
        logger.info("[wanted] 상세 API 요청: job_id=%d", job_id)
        return self.get_json(
            f"{_BASE_URL}{_JOBS_API}/{job_id}",
            log_label=f"상세 job_id={job_id}",
        )

    # ------------------------------------------------------------------
    # JsonApiCrawler 훅
    # ------------------------------------------------------------------

    def fetch_list_page(self, cursor: PageCursor) -> dict[str, Any] | None:
        return self.fetch_jobs_page(
            cursor.filter_value or [],
            offset=cursor.offset,
            limit=cursor.page_size,
        )

    def extract_ids(self, page_data: dict[str, Any]) -> list[int]:
        return self.extract_job_ids(page_data)

    def advance_cursor(
        self,
        cursor: PageCursor,
        page_data: dict[str, Any],
        ids: list[int],
    ) -> PageCursor | None:
        if not self.has_next_page(page_data):
            return None
        return PageCursor(
            filter_value=cursor.filter_value,
            offset=cursor.offset + len(ids),
            page=cursor.page + 1,
            page_size=cursor.page_size,
        )

    def fetch_detail_json(self, job_id: int) -> dict[str, Any] | None:
        return self.fetch_job_detail(job_id)

    def build_original_url(self, job_id: int) -> str:
        return _DETAIL_URL.format(job_id=job_id)

    def collect_jobs(
        self,
        tag_type_ids: list[int],
        saved_ids: set[tuple[str, str]],
        max_pages: int = _MAX_PAGES,
        max_jobs: int | None = None,
    ) -> list[RawJobPosting]:
        return self.collect_json_jobs(
            PageCursor(
                filter_value=tag_type_ids,
                offset=0,
                page=0,
                page_size=_RESULTS_PER_PAGE,
            ),
            saved_ids,
            max_pages=max_pages,
            max_jobs=max_jobs,
        )


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def fetch_wanted(
    query: str,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_pages: int = _MAX_PAGES,
    max_jobs: int | None = None,
) -> str:
    if crawl_date is None:
        crawl_date = date.today().isoformat()

    tag_ids = _resolve_tag_ids(query)
    if not tag_ids:
        logger.warning(
            "[wanted] '%s'에 매핑된 tag_type_ids 없음 — 수집 건너뜀", query,
        )
        return ""

    saved_ids = get_saved_ids(_COLLECTION, base_dir=save_path)

    with _WantedCrawler() as crawler:
        postings = crawler.collect_jobs(
            tag_type_ids=tag_ids,
            saved_ids=saved_ids,
            max_pages=max_pages,
            max_jobs=max_jobs,
        )

    if not postings:
        logger.info("[wanted] '%s' — 신규 공고 없음", query)
        return ""

    docs = [p.to_dict() for p in postings]
    filename = build_crawl_filename(_SOURCE_NAME, query)

    saved = save_documents(
        documents=docs,
        collection_name=_COLLECTION,
        filename=filename,
        crawl_date=crawl_date,
        base_dir=save_path,
        job_function_name=query,
    )
    logger.info(
        "[wanted] '%s' 수집 완료 — %d건 저장 → %s",
        query, len(docs), saved,
    )
    return str(saved)


def run_wanted_batch(
    job_functions: list[str],
    crawl_date: str | None = None,
    save_dir: str = "./data/raw_job_postings",
    max_pages: int = _MAX_PAGES,
    max_jobs: int | None = None,
) -> None:
    from src.crawlers.common.batch import run_query_batch

    save_path = str(save_dir).removesuffix("/raw_job_postings")
    run_query_batch(
        source_name=_SOURCE_NAME,
        job_functions=job_functions,
        crawl_fn=fetch_wanted,
        crawl_date=crawl_date,
        inter_query_delay=(2.0, 4.0),
        count_saved_only=True,
        save_path=save_path,
        max_pages=max_pages,
        max_jobs=max_jobs,
    )


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _resolve_tag_ids(query: str) -> list[int]:
    query = query.strip()
    if not query:
        return []

    if query.replace(",", "").replace(" ", "").isdigit():
        try:
            return [int(x.strip()) for x in query.split(",") if x.strip()]
        except ValueError:
            pass

    ids = get_tag_ids_for_function(query)
    if ids:
        return ids

    logger.warning("[wanted] '%s' — taxonomy 매핑 없음", query)
    return []


def _is_blocked(text: str) -> bool:
    return is_blocked(text)
