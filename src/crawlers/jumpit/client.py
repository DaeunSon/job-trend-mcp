"""
점핏 크롤러.

주요 함수
---------
fetch_jumpit()         — jobCategory 하나에 대한 공고를 수집해
                         raw_job_postings 구조의 JSON으로 저장
run_jumpit_batch()     — job_functions 목록을 순회하며 fetch_jumpit을 반복 호출

수집 방식 — 내부 JSON API 직접 호출 (2026-07-28 확인)
-----------------------------------------------------
  목록 API  : GET https://jumpit-api.saramin.co.kr/api/positions
  상세 API  : GET https://jumpit-api.saramin.co.kr/api/position/{id}
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
from src.crawlers.jumpit.search_queries import get_category_ids_for_function
from src.models.schemas import RawJobPosting
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_API_BASE_URL = "https://jumpit-api.saramin.co.kr"
_LIST_API = "/api/positions"
_DETAIL_API = "/api/position/{position_id}"
_DETAIL_URL = "https://jumpit.saramin.co.kr/position/{position_id}"
_PAGE_SIZE = 20
_MAX_PAGES = 100
_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "jumpit"


class _JumpitCrawler(JsonApiCrawler):
    """점핏 내부 JSON API를 직접 호출하는 크롤러."""

    source_name = _SOURCE_NAME
    page_size = _PAGE_SIZE
    default_max_pages = _MAX_PAGES

    def __init__(self) -> None:
        super().__init__(
            source_name=_SOURCE_NAME,
            base_url=_API_BASE_URL,
            user_agent=BROWSER_USER_AGENT,
            rate_limit_min=1.0,
            rate_limit_max=2.0,
        )
        self._session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://jumpit.saramin.co.kr/positions",
                "Origin": "https://jumpit.saramin.co.kr",
                "Connection": "keep-alive",
            }
        )

    # ------------------------------------------------------------------
    # 목록 / 상세 (테스트 호환)
    # ------------------------------------------------------------------

    def fetch_positions_page(
        self,
        job_category_id: int,
        page: int = 1,
        size: int = _PAGE_SIZE,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {
            "sort": "createdAt",
            "page": page,
            "jobCategory": job_category_id,
            "size": size,
        }
        logger.info(
            "[jumpit] 목록 API 요청 (jobCategory=%d, page=%d)",
            job_category_id, page,
        )
        body = self.get_json(
            _API_BASE_URL + _LIST_API,
            params=params,
            log_label=f"목록 cat={job_category_id} page={page}",
        )
        if body is None:
            return None
        return body.get("result") or body

    def extract_position_ids(self, page_result: dict[str, Any]) -> list[int]:
        ids: list[int] = []
        for item in page_result.get("positions") or []:
            pid = item.get("id")
            if pid is not None:
                ids.append(int(pid))
        return ids

    def has_next_page(
        self,
        page_result: dict[str, Any],
        current_page: int,
        page_size: int,
    ) -> bool:
        total = page_result.get("totalCount", 0)
        fetched = current_page * page_size
        etc = page_result.get("etc")
        if etc is False:
            return False
        return fetched < total

    def fetch_position_detail(self, position_id: int) -> dict[str, Any] | None:
        logger.info("[jumpit] 상세 API 요청: position_id=%d", position_id)
        body = self.get_json(
            _API_BASE_URL + _DETAIL_API.format(position_id=position_id),
            log_label=f"상세 position_id={position_id}",
        )
        if body is None:
            return None
        result = body.get("result") or body
        if not result or not isinstance(result, dict):
            logger.warning(
                "[jumpit] 상세 API 빈 result (position_id=%d): %s",
                position_id, body,
            )
            return None
        return result

    # ------------------------------------------------------------------
    # JsonApiCrawler 훅
    # ------------------------------------------------------------------

    def fetch_list_page(self, cursor: PageCursor) -> dict[str, Any] | None:
        return self.fetch_positions_page(
            int(cursor.filter_value),
            page=cursor.page,
            size=cursor.page_size,
        )

    def extract_ids(self, page_data: dict[str, Any]) -> list[int]:
        return self.extract_position_ids(page_data)

    def advance_cursor(
        self,
        cursor: PageCursor,
        page_data: dict[str, Any],
        ids: list[int],
    ) -> PageCursor | None:
        if not self.has_next_page(page_data, cursor.page, cursor.page_size):
            return None
        return PageCursor(
            filter_value=cursor.filter_value,
            page=cursor.page + 1,
            offset=cursor.offset,
            page_size=cursor.page_size,
        )

    def fetch_detail_json(self, job_id: int) -> dict[str, Any] | None:
        return self.fetch_position_detail(job_id)

    def build_original_url(self, job_id: int) -> str:
        return _DETAIL_URL.format(position_id=job_id)

    def collect_positions(
        self,
        job_category_id: int,
        saved_ids: set[tuple[str, str]],
        max_pages: int = _MAX_PAGES,
        max_jobs: int | None = None,
        page_size: int = _PAGE_SIZE,
    ) -> list[RawJobPosting]:
        return self.collect_json_jobs(
            PageCursor(
                filter_value=job_category_id,
                page=1,
                page_size=page_size,
            ),
            saved_ids,
            max_pages=max_pages,
            max_jobs=max_jobs,
        )


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def fetch_jumpit(
    query: str | None = None,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_pages: int = _MAX_PAGES,
    max_jobs: int | None = None,
) -> str:
    if crawl_date is None:
        crawl_date = date.today().isoformat()

    category_ids = _resolve_category_ids(query)
    if not category_ids:
        logger.warning(
            "[jumpit] '%s'에 매핑된 jobCategory ID 없음 — 수집 건너뜀", query,
        )
        return ""

    saved_ids = get_saved_ids(_COLLECTION, base_dir=save_path)
    all_postings: list[RawJobPosting] = []

    with _JumpitCrawler() as crawler:
        for cat_id in category_ids:
            postings = crawler.collect_positions(
                job_category_id=cat_id,
                saved_ids=saved_ids,
                max_pages=max_pages,
                max_jobs=max_jobs,
            )
            all_postings.extend(postings)

            if max_jobs is not None and len(all_postings) >= max_jobs:
                logger.info("[jumpit] max_jobs=%d 도달 — 카테고리 순회 중단", max_jobs)
                all_postings = all_postings[:max_jobs]
                break

            if len(category_ids) > 1:
                wait = random.uniform(2.0, 4.0)
                logger.debug("[jumpit] 다음 카테고리까지 %.1fs 대기", wait)
                time.sleep(wait)

    if not all_postings:
        logger.info("[jumpit] '%s' — 신규 공고 없음", query)
        return ""

    docs = [p.to_dict() for p in all_postings]
    filename = build_crawl_filename(_SOURCE_NAME, query or "all")

    saved = save_documents(
        documents=docs,
        collection_name=_COLLECTION,
        filename=filename,
        crawl_date=crawl_date,
        base_dir=save_path,
        job_function_name=query,
    )
    logger.info(
        "[jumpit] '%s' 수집 완료 — %d건 저장 → %s",
        query, len(docs), saved,
    )
    return str(saved)


def run_jumpit_batch(
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
        crawl_fn=fetch_jumpit,
        crawl_date=crawl_date,
        inter_query_delay=(2.0, 4.0),
        count_saved_only=True,
        save_path=save_path,
        max_pages=max_pages,
        max_jobs=max_jobs,
    )


def _resolve_category_ids(query: str | None) -> list[int]:
    if not query:
        return []

    query = query.strip()

    if query.replace(",", "").replace(" ", "").isdigit():
        try:
            return [int(x.strip()) for x in query.split(",") if x.strip()]
        except ValueError:
            pass

    ids = get_category_ids_for_function(query)
    if ids:
        return ids

    logger.warning("[jumpit] '%s' — taxonomy/카테고리 매핑 없음", query)
    return []


def _is_blocked(text: str) -> bool:
    return is_blocked(text)
