"""
랠릿 크롤러.

주요 함수
---------
fetch_rallit()         — keyword 하나에 대한 공고를 수집해
                         raw_job_postings 구조의 JSON으로 저장
run_rallit_batch()     — job_functions 목록을 순회하며 fetch_rallit을 반복 호출

수집 방식 — 내부 JSON API 직접 호출 (2026-07-29 확인)
-----------------------------------------------------
  목록 API  : GET /client/api/v1/position
  상세 API  : GET /client/api/v1/position/{id}
  Accept-Encoding 에 br 제외 (requests Brotli 미지원)
"""
from __future__ import annotations

import logging
import random
import time
from datetime import date
from typing import Any

from src.crawlers.common import (
    BROWSER_USER_AGENT,
    DEFAULT_BLOCK_SIGNALS,
    JsonApiCrawler,
    PageCursor,
    build_crawl_filename,
    is_blocked,
)
from src.crawlers.rallit.search_queries import get_keywords_for_function
from src.models.schemas import RawJobPosting
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_API_BASE_URL = "https://www.rallit.com"
_LIST_API = "/client/api/v1/position"
_DETAIL_API = "/client/api/v1/position/{position_id}"
_DETAIL_URL = "https://www.rallit.com/positions/{position_id}"
_PAGE_SIZE = 20
_MAX_PAGES = 30
_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "rallit"

_BLOCK_SIGNALS = (*DEFAULT_BLOCK_SIGNALS, "cloudflare")


class _RallitCrawler(JsonApiCrawler):
    """랠릿 내부 JSON API를 직접 호출하는 크롤러."""

    source_name = _SOURCE_NAME
    page_size = _PAGE_SIZE
    default_max_pages = _MAX_PAGES
    block_signals = _BLOCK_SIGNALS

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
                # br(Brotli)는 requests 기본 디코더 미지원 — 상세 API가 br로 내려오면 JSON 파싱 실패
                "Accept-Encoding": "gzip, deflate",
                "Referer": "https://www.rallit.com/",
                "Origin": "https://www.rallit.com",
                "Connection": "keep-alive",
            }
        )

    # ------------------------------------------------------------------
    # 목록 / 상세 (테스트 호환)
    # ------------------------------------------------------------------

    def fetch_positions_page(
        self,
        keyword: str | None,
        page: int = 1,
        size: int = _PAGE_SIZE,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {
            "pageNumber": page,
            "pageSize": size,
        }
        if keyword:
            params["keyword"] = keyword

        logger.info(
            "[rallit] 목록 API 요청 (keyword=%r, page=%d)",
            keyword, page,
        )
        body = self.get_json(
            _API_BASE_URL + _LIST_API,
            params=params,
            log_label=f"목록 keyword={keyword!r} page={page}",
        )
        if body is None:
            return None

        data = body.get("data")
        if not isinstance(data, dict):
            logger.warning(
                "[rallit] 목록 API 응답 data 필드 없음 (keyword=%r): %s",
                keyword, body,
            )
            return None
        return data

    def extract_position_ids(self, page_data: dict[str, Any]) -> list[int]:
        ids: list[int] = []
        for item in page_data.get("items") or []:
            pid = item.get("id")
            if pid is not None:
                try:
                    ids.append(int(pid))
                except (ValueError, TypeError):
                    logger.debug("[rallit] id 파싱 실패: %r", pid)
        return ids

    def has_next_page(
        self,
        page_data: dict[str, Any],
        current_page: int,
    ) -> bool:
        total_page: int = page_data.get("totalPage") or 0
        return current_page < total_page

    def fetch_position_detail(self, position_id: int) -> dict[str, Any] | None:
        logger.info("[rallit] 상세 API 요청: position_id=%d", position_id)
        body = self.get_json(
            _API_BASE_URL + _DETAIL_API.format(position_id=position_id),
            log_label=f"상세 position_id={position_id}",
        )
        if body is None:
            return None

        data = body.get("data")
        if not isinstance(data, dict):
            logger.warning(
                "[rallit] 상세 API 빈 data (position_id=%d): %s",
                position_id, body,
            )
            return None
        return data

    # ------------------------------------------------------------------
    # JsonApiCrawler 훅
    # ------------------------------------------------------------------

    def fetch_list_page(self, cursor: PageCursor) -> dict[str, Any] | None:
        return self.fetch_positions_page(
            cursor.filter_value,
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
        if not self.has_next_page(page_data, cursor.page):
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
        keyword: str | None,
        saved_ids: set[tuple[str, str]],
        max_pages: int = _MAX_PAGES,
        max_jobs: int | None = None,
        page_size: int = _PAGE_SIZE,
    ) -> list[RawJobPosting]:
        return self.collect_json_jobs(
            PageCursor(
                filter_value=keyword,
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

def fetch_rallit(
    query: str | None = None,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_pages: int = _MAX_PAGES,
    max_jobs: int | None = None,
) -> str:
    if crawl_date is None:
        crawl_date = date.today().isoformat()

    keywords = _resolve_keywords(query)
    saved_ids = get_saved_ids(_COLLECTION, base_dir=save_path)
    all_postings: list[RawJobPosting] = []

    with _RallitCrawler() as crawler:
        for kw in keywords:
            postings = crawler.collect_positions(
                keyword=kw,
                saved_ids=saved_ids,
                max_pages=max_pages,
                max_jobs=max_jobs,
            )
            all_postings.extend(postings)

            if max_jobs is not None and len(all_postings) >= max_jobs:
                logger.info("[rallit] max_jobs=%d 도달 — 키워드 순회 중단", max_jobs)
                all_postings = all_postings[:max_jobs]
                break

            if len(keywords) > 1:
                wait = random.uniform(2.0, 4.0)
                logger.debug("[rallit] 다음 키워드까지 %.1fs 대기", wait)
                time.sleep(wait)

    if not all_postings:
        logger.info("[rallit] '%s' — 신규 공고 없음", query)
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
        "[rallit] '%s' 수집 완료 — %d건 저장 → %s",
        query, len(docs), saved,
    )
    return str(saved)


def run_rallit_batch(
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
        crawl_fn=fetch_rallit,
        crawl_date=crawl_date,
        inter_query_delay=(2.0, 4.0),
        count_saved_only=True,
        save_path=save_path,
        max_pages=max_pages,
        max_jobs=max_jobs,
    )


def _resolve_keywords(query: str | None) -> list[str | None]:
    if not query:
        return [None]

    query = query.strip()

    if query.replace(",", "").replace(" ", "").isdigit():
        return [None]

    keywords = get_keywords_for_function(query)
    if keywords:
        return keywords

    logger.debug("[rallit] '%s' — taxonomy 매핑 없음, query를 keyword로 사용", query)
    return [query]


def _is_blocked(text: str) -> bool:
    return is_blocked(text, signals=_BLOCK_SIGNALS)
