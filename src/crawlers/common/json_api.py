"""
내부 JSON API 계열 크롤러 공통 템플릿.

wanted · jumpit · rallit 처럼 목록 API → 상세 API → RawJobPosting 패턴을 공유한다.
사이트별 URL/파라미터/페이지네이션/헤더는 서브클래스 훅에 남긴다.
"""
from __future__ import annotations

import json
import logging
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any

import requests

from src.crawlers.base_crawler import BaseCrawler
from src.crawlers.common.http_utils import DEFAULT_BLOCK_SIGNALS, is_blocked
from src.models.schemas import RawJobPosting

logger = logging.getLogger(__name__)


@dataclass
class PageCursor:
    """목록 API 페이지네이션 상태."""

    filter_value: Any = None  # tag_ids | category_id | keyword | ...
    page: int = 1             # 1-based (jumpit/rallit) 또는 페이지 카운터
    offset: int = 0           # wanted offset 모드
    page_size: int = 20


class JsonApiCrawler(BaseCrawler):
    """목록 JSON → 상세 JSON → RawJobPosting 수집 템플릿."""

    page_size: int = 20
    default_max_pages: int = 100
    block_signals: tuple[str, ...] = DEFAULT_BLOCK_SIGNALS

    def crawl(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            f"Use the module-level crawl_{self.source_name}() entrypoint."
        )

    # ------------------------------------------------------------------
    # 공유 HTTP 헬퍼
    # ------------------------------------------------------------------

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        log_label: str = "",
    ) -> dict[str, Any] | None:
        """
        GET → 차단 검사 → JSON 파싱.
        실패/차단/파싱 오류 시 None.
        """
        tag = self.source_name
        label = log_label or url
        try:
            resp = self.get(url, params=params)
        except requests.exceptions.RequestException as exc:
            logger.error("[%s] 요청 실패 (%s): %s", tag, label, exc)
            return None

        if is_blocked(resp.text or "", signals=self.block_signals):
            logger.warning("[%s] 차단 감지 (%s)", tag, label)
            return None

        try:
            data = resp.json()
        except ValueError as exc:
            logger.error(
                "[%s] JSON 파싱 실패 (%s): %s — 응답(200자): %s",
                tag, label, exc, (resp.text or "")[:200],
            )
            return None

        if not isinstance(data, dict):
            logger.warning("[%s] JSON 루트가 dict 아님 (%s): %s", tag, label, type(data))
            return None
        return data

    # ------------------------------------------------------------------
    # 사이트별 훅
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch_list_page(self, cursor: PageCursor) -> dict[str, Any] | None:
        """목록 API 한 페이지. 실패 시 None."""

    @abstractmethod
    def extract_ids(self, page_data: dict[str, Any]) -> list[int]:
        """목록 응답에서 job/position id 목록."""

    @abstractmethod
    def advance_cursor(
        self,
        cursor: PageCursor,
        page_data: dict[str, Any],
        ids: list[int],
    ) -> PageCursor | None:
        """다음 페이지 커서. 없으면 None."""

    @abstractmethod
    def fetch_detail_json(self, job_id: int) -> dict[str, Any] | None:
        """상세 API JSON. 실패 시 None."""

    @abstractmethod
    def build_original_url(self, job_id: int) -> str:
        """사용자용 원본 URL."""

    # ------------------------------------------------------------------
    # 공통 오케스트레이션
    # ------------------------------------------------------------------

    def collect_json_jobs(
        self,
        cursor: PageCursor,
        saved_ids: set[tuple[str, str]],
        max_pages: int | None = None,
        max_jobs: int | None = None,
    ) -> list[RawJobPosting]:
        """
        목록 페이지를 순회하며 상세 JSON을 수집한다.
        이미 저장된 (source_name, source_job_id)는 건너뛴다.
        """
        results: list[RawJobPosting] = []
        pages_done = 0
        _max = max_pages if max_pages is not None else self.default_max_pages
        tag = self.source_name
        state = cursor

        while pages_done < _max:
            page_data = self.fetch_list_page(state)
            if page_data is None:
                logger.warning("[%s] 목록 API 응답 없음 — 수집 중단", tag)
                break

            ids = self.extract_ids(page_data)
            if not ids:
                logger.info("[%s] 더 이상 공고 없음 — 수집 완료", tag)
                break

            logger.info(
                "[%s] 목록 page=%s offset=%s 건수=%d",
                tag, state.page, state.offset, len(ids),
            )

            for job_id in ids:
                sid = str(job_id)
                if (tag, sid) in saved_ids:
                    logger.debug("[%s] 이미 저장됨, 건너뜀: id=%d", tag, job_id)
                    continue

                detail = self.fetch_detail_json(job_id)
                if detail is None:
                    logger.warning("[%s] 상세 수집 실패, 건너뜀: id=%d", tag, job_id)
                    continue

                posting = RawJobPosting(
                    source_name=tag,
                    source_job_id=sid,
                    original_url=self.build_original_url(job_id),
                    raw_html="",
                    raw_text=json.dumps(detail, ensure_ascii=False),
                )
                results.append(posting)
                saved_ids.add((tag, sid))
                logger.debug("[%s] 수집 완료: id=%d", tag, job_id)

                if max_jobs is not None and len(results) >= max_jobs:
                    logger.info("[%s] max_jobs=%d 도달 — 수집 중단", tag, max_jobs)
                    return results

            pages_done += 1
            nxt = self.advance_cursor(state, page_data, ids)
            if nxt is None:
                logger.info("[%s] 마지막 페이지 — 수집 완료", tag)
                break
            state = nxt

        logger.info("[%s] 총 %d건 수집 완료", tag, len(results))
        return results
