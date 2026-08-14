"""
HTML SERP → 상세 페이지 수집 공통 루프.

사이트별 구현이 제공할 것
------------------------
- fetch_serp / get_total_count / extract_job_cards
- job_id_field (카드 dict 키, 예: rec_idx / job_id)
- fetch_detail_for_collect(job_id, query, card)
- build_original_url(job_id, card)

중복 정책 (duplicate_mode)
--------------------------
- skip    : 이미 저장된 id는 건너뛰고 계속 (saramin force=False, jobkorea full)
- stop    : 이미 저장된 id를 만나면 즉시 중단 (jobkorea incremental)
- refetch : 이미 저장된 id도 다시 상세 수집 (saramin force=True)
"""
from __future__ import annotations

import logging
import math
from abc import abstractmethod
from typing import Any, Iterator, Literal

from bs4 import BeautifulSoup

from src.crawlers.base_crawler import BaseCrawler
from src.models.schemas import RawJobPosting

logger = logging.getLogger(__name__)

DuplicateMode = Literal["skip", "stop", "refetch"]


class HtmlSerpCrawler(BaseCrawler):
    """SERP 페이지 순회 + 상세 HTML 수집 템플릿."""

    results_per_page: int = 20
    default_max_pages: int = 50
    # 카드 dict에서 source_job_id로 쓸 키
    job_id_field: str = "job_id"

    def crawl(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            f"Use the module-level crawl_{self.source_name}() entrypoint."
        )

    # ------------------------------------------------------------------
    # 사이트별 훅
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch_serp(self, query: str, page: int) -> BeautifulSoup | None:
        """검색 결과 페이지. 차단/실패 시 None."""

    @abstractmethod
    def get_total_count(self, soup: BeautifulSoup) -> int:
        """검색 결과 총 건수. 실패 시 0."""

    @abstractmethod
    def extract_job_cards(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        """SERP에서 공고 카드 목록 추출."""

    @abstractmethod
    def fetch_detail_for_collect(
        self,
        job_id: str,
        query: str,
        card: dict[str, str],
    ) -> tuple[str, str] | None:
        """상세 페이지 (raw_html, raw_text). 차단/실패 시 None."""

    @abstractmethod
    def build_original_url(self, job_id: str, card: dict[str, str]) -> str:
        """저장용 원본 URL."""

    # ------------------------------------------------------------------
    # 공통 오케스트레이션
    # ------------------------------------------------------------------

    def collect_jobs_paged(
        self,
        query: str,
        saved_ids: set[tuple[str, str]],
        max_pages: int | None = None,
        duplicate_mode: DuplicateMode = "skip",
    ) -> Iterator[list[RawJobPosting]]:
        """
        SERP 페이지를 순회하며 상세 HTML을 수집하고,
        한 SERP 페이지분 결과를 모을 때마다 yield 한다.
        """
        _max_pages = max_pages if max_pages is not None else self.default_max_pages
        total_pages = _max_pages
        tag = self.source_name

        for page in range(1, _max_pages + 1):
            if page > total_pages:
                break

            soup = self.fetch_serp(query, page)
            if soup is None:
                logger.warning("[%s] SERP 차단 또는 실패 (page=%d) — 중단", tag, page)
                return

            if page == 1:
                total_count = self.get_total_count(soup)
                if total_count == 0:
                    logger.info("[%s] 검색 결과 0건 (query=%r)", tag, query)
                    return
                total_pages = min(
                    math.ceil(total_count / self.results_per_page),
                    _max_pages,
                )
                logger.info(
                    "[%s] 총 %d건 / %d 페이지 (query=%r, duplicate_mode=%s)",
                    tag, total_count, total_pages, query, duplicate_mode,
                )

            cards = self.extract_job_cards(soup)
            if not cards:
                logger.info("[%s] 카드 없음 (page=%d) — 종료", tag, page)
                return

            logger.info("[%s] page=%d: %d건 발견", tag, page, len(cards))

            page_results: list[RawJobPosting] = []
            blocked = False
            reached_old = False

            for card in cards:
                job_id = card[self.job_id_field]
                already = (self.source_name, job_id) in saved_ids

                if already and duplicate_mode == "stop":
                    logger.info(
                        "[%s] 기존 공고 감지 (%s=%s) — 증분 수집 완료 (page=%d)",
                        tag, self.job_id_field, job_id, page,
                    )
                    reached_old = True
                    break

                if already and duplicate_mode == "skip":
                    logger.debug("[%s] 중복 건너뜀: %s", tag, job_id)
                    continue

                # refetch: already여도 계속 수집
                result = self.fetch_detail_for_collect(job_id, query, card)
                if result is None:
                    logger.warning(
                        "[%s] 상세 페이지 실패/차단 (%s=%s) — 배치 중단",
                        tag, self.job_id_field, job_id,
                    )
                    blocked = True
                    break

                raw_html, raw_text = result
                raw = RawJobPosting(
                    source_name=self.source_name,
                    source_job_id=job_id,
                    original_url=self.build_original_url(job_id, card),
                    raw_html=raw_html,
                    raw_text=raw_text,
                )
                page_results.append(raw)
                saved_ids.add((self.source_name, job_id))

            yield page_results

            if reached_old or blocked:
                return
