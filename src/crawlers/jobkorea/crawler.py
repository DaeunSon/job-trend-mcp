"""
잡코리아 크롤러.

주요 함수
---------
crawl_jobkorea()        — 검색어 하나에 대한 공고를 수집해 raw_job_postings JSON으로 저장
run_jobkorea_batch()    — job_functions를 순회하며 crawl_jobkorea를 반복 호출

수집 방식
---------
1. 검색 결과 SERP 페이지 순회 (Page_No 파라미터)
   - recruitSort=regDt 로 최신 등록순 정렬
   - "총 N건" 텍스트로 전체 건수 파악 → 총 페이지 수 계산
   - 각 카드에서 job_id, 회사명, 공고명, 채용형태, 위치 추출
2. 상세 페이지 요청 (job_id 기준) → raw_html 저장
   - 상세 페이지 방문 전에 이미 저장된 (source_name, source_job_id) 중복 체크

증분 수집 (incremental=True, 기본값)
--------------------------------------
최신 등록순으로 페이지를 순회하다가 이미 저장된 job_id가 나오면 즉시 중단한다.
첫 수집 이후 재실행 시 신규 공고만 빠르게 가져오는 용도.

전체 수집 (incremental=False)
--------------------------------------
이미 저장된 job_id는 개별 건너뛰되 중단하지 않고 끝까지 순회한다.
첫 번째 전체 수집, 또는 누락 공고 보완 시 사용.

URL 구조
--------
SERP:   https://www.jobkorea.co.kr/Search/?stext={query}&tabType=recruit
        &Page_No={n}&recruitSort=regDt
상세:   https://www.jobkorea.co.kr/Recruit/GI_Read/{job_id}

source_job_id
--------------
잡코리아 공고 카드 href의 GI_Read/(숫자) 패턴.
예: GI_Read/24115438 → source_job_id = "24115438"
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Iterator
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from src.crawlers.common import (
    BROWSER_USER_AGENT,
    HtmlSerpCrawler,
    build_crawl_filename,
    html_to_text,
    is_blocked,
    parse_total_count,
    run_query_batch,
)
from src.models.schemas import RawJobPosting
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.jobkorea.co.kr"
_SEARCH_PATH = "/Search/"
_DETAIL_PATH = "/Recruit/GI_Read/"
_RESULTS_PER_PAGE = 20
_MAX_PAGES = 50
_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "jobkorea"

_TOTAL_COUNT_SELECTORS = (
    ".recruit-totalNum",
    ".search-count strong",
    "#content .cnt strong",
    ".tplJobCount",
)


# ---------------------------------------------------------------------------
# 내부 크롤러 클래스
# ---------------------------------------------------------------------------

class _JobkoreaCrawler(HtmlSerpCrawler):
    """requests + BeautifulSoup 기반 잡코리아 크롤러."""

    # class attr — __init__ 없이 __new__ 하는 테스트에서도 self.source_name 사용 가능
    source_name = _SOURCE_NAME
    results_per_page = _RESULTS_PER_PAGE
    default_max_pages = _MAX_PAGES
    job_id_field = "job_id"

    def __init__(self) -> None:
        super().__init__(
            source_name=_SOURCE_NAME,
            base_url=_BASE_URL,
            user_agent=BROWSER_USER_AGENT,
            rate_limit_min=2.0,
            rate_limit_max=3.5,
            timeout=(10, 45),  # connect 10s / read 45s — 상세 페이지 응답이 느린 경우 대비
        )
        self._session.headers.update(
            {
                "Referer": "https://www.jobkorea.co.kr/",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    # ------------------------------------------------------------------
    # SERP
    # ------------------------------------------------------------------

    def fetch_serp(self, query: str, page: int) -> BeautifulSoup | None:
        """검색 결과 페이지를 요청하고 파싱된 BeautifulSoup을 반환한다. 차단 시 None."""
        params = {
            "stext": query,
            "tabType": "recruit",
            "Page_No": str(page),
            "recruitSort": "regDt",  # 최신 등록순 정렬
        }
        url = _BASE_URL + _SEARCH_PATH + "?" + urlencode(params, encoding="utf-8")

        logger.info("[jobkorea] SERP 요청 (page=%d): %s", page, url)
        try:
            resp = self.get(url)
        except requests.exceptions.RequestException as exc:
            logger.error("[jobkorea] SERP 요청 실패 (page=%d): %s", page, exc)
            return None

        if is_blocked(resp.text):
            logger.warning(
                "[jobkorea] 차단 감지 (SERP page=%d) — 응답 앞 200자: %s",
                page, resp.text[:200],
            )
            return None

        return BeautifulSoup(resp.text, "lxml")

    def get_total_count(self, soup: BeautifulSoup) -> int:
        """검색 결과 총 건수를 파싱한다. 파싱 실패 시 0 반환."""
        return parse_total_count(
            soup,
            selectors=_TOTAL_COUNT_SELECTORS,
            text_patterns=(r"총\s*([\d,]+)\s*건",),
        )

    def extract_job_cards(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        """
        SERP HTML에서 공고 카드 정보를 추출한다.

        잡코리아 SERP 구조 (2026년 기준 — Next.js + Tailwind CSS):
          카드:    div[data-sentry-component="CardJob"]
          제목:    a[data-sentry-component="Title"] span
          회사명:  span.text-typo-b2-16  (Tailwind typography 클래스)
          위치:    div[data-sentry-component="GrayChip"] span.truncate  (첫 번째 칩)
          job_id:  href 내 GI_Read/(숫자) 패턴

        Returns
        -------
        list of dict: job_id, title, company, location, career_type, detail_url
        """
        cards: list[dict[str, str]] = []
        seen: set[str] = set()

        card_els = soup.find_all("div", attrs={"data-sentry-component": "CardJob"})
        if not card_els:
            for sel in ["article.list-item", "li[data-gno]", "div.list-post"]:
                card_els = soup.select(sel)
                if card_els:
                    break

        for card in card_els:
            job_id = _extract_job_id_from_card(card)
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)

            detail_url = _extract_detail_url(card, job_id)

            title_tag = card.find("a", attrs={"data-sentry-component": "Title"})
            if title_tag:
                span = title_tag.find("span")
                title = span.get_text(strip=True) if span else title_tag.get_text(strip=True)
            else:
                title = _extract_card_text(card, [".post-title", ".title", "a.name"])

            company_tag = card.find("span", class_="text-typo-b2-16")
            company = company_tag.get_text(strip=True) if company_tag else _extract_card_text(
                card, [".company-name", ".corp-name", "[class*='corpNm']"]
            )

            chips = card.find_all("div", attrs={"data-sentry-component": "GrayChip"})
            location = (
                chips[0].find("span", class_="truncate").get_text(strip=True) if chips else ""
            )

            career_span = card.find("span", class_="text-typo-c1-13")
            career_type = career_span.get_text(strip=True) if career_span else ""

            cards.append({
                "job_id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "career_type": career_type,
                "education": "",
                "deadline": "",
                "detail_url": detail_url,
            })

        if not cards:
            logger.debug(
                "[jobkorea] SERP 카드 추출 실패 — CardJob 컴포넌트 없음. "
                "HTML 구조 변경 여부 확인 필요 (Next.js SSR 기반)."
            )

        return cards

    # ------------------------------------------------------------------
    # 상세 페이지
    # ------------------------------------------------------------------

    def fetch_detail(self, job_id: str, query: str) -> tuple[str, str] | None:
        """
        상세 페이지를 요청하고 (raw_html, raw_text) 튜플을 반환한다.
        차단 또는 실패 시 None 반환.
        """
        url = f"{_BASE_URL}{_DETAIL_PATH}{job_id}"
        params = {"Oem_Code": "C1", "logpath": "1", "stext": query}
        full_url = url + "?" + urlencode(params, encoding="utf-8")

        self._session.headers.update({"Referer": _BASE_URL + _SEARCH_PATH})
        try:
            resp = self.get(full_url)
        except requests.exceptions.RequestException as exc:
            logger.error("[jobkorea] 상세 페이지 요청 실패 (%s): %s", job_id, exc)
            return None

        if is_blocked(resp.text):
            logger.warning(
                "[jobkorea] 차단 감지 (상세 job_id=%s) — 응답 앞 200자: %s",
                job_id, resp.text[:200],
            )
            return None

        return resp.text, html_to_text(resp.text)

    def fetch_detail_for_collect(
        self,
        job_id: str,
        query: str,
        card: dict[str, str],
    ) -> tuple[str, str] | None:
        return self.fetch_detail(job_id, query)

    def build_original_url(self, job_id: str, card: dict[str, str]) -> str:
        return f"{_BASE_URL}{_DETAIL_PATH}{job_id}"

    # ------------------------------------------------------------------
    # 수집 오케스트레이션
    # ------------------------------------------------------------------

    def collect_jobs_paged(  # type: ignore[override]
        self,
        query: str,
        saved_ids: set[tuple[str, str]],
        max_pages: int = _MAX_PAGES,
        incremental: bool = True,
    ) -> Iterator[list[RawJobPosting]]:
        """
        SERP 페이지를 최신 등록순으로 순회하며 상세 페이지 HTML을 수집하고,
        한 SERP 페이지분의 결과를 모을 때마다 yield 한다.

        Parameters
        ----------
        incremental : True(기본) — 이미 저장된 job_id를 만나면 즉시 중단
                      False      — 끝까지 순회하며 신규 건만 수집
        """
        yield from super().collect_jobs_paged(
            query=query,
            saved_ids=saved_ids,
            max_pages=max_pages,
            duplicate_mode="stop" if incremental else "skip",
        )

    def collect_jobs(
        self,
        query: str,
        saved_ids: set[tuple[str, str]],
        max_pages: int = _MAX_PAGES,
        incremental: bool = True,
    ) -> list[RawJobPosting]:
        """
        collect_jobs_paged의 편의 래퍼.
        하위 호환성 유지용 — 기존 테스트 및 단순 호출 코드에서 사용한다.
        """
        results: list[RawJobPosting] = []
        for batch in self.collect_jobs_paged(query, saved_ids, max_pages, incremental):
            results.extend(batch)
        return results


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def crawl_jobkorea(
    query: str,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_pages: int = _MAX_PAGES,
    incremental: bool = True,
) -> str:
    """
    잡코리아에서 주어진 검색어 하나에 대한 채용공고를 수집해
    raw_job_postings 구조의 JSON으로 저장한다.

    ⚠️ robots.txt 미준수 — 상업적 목적 사용 전 법무 검토 필요.
    """
    if not query or not query.strip():
        raise ValueError("query는 필수 파라미터입니다.")

    _crawl_date = crawl_date or date.today().isoformat()
    filename = _build_filename(query)

    logger.info(
        "[jobkorea] crawl_jobkorea 시작 — query=%r, crawl_date=%s, "
        "max_pages=%d, incremental=%s",
        query, _crawl_date, max_pages, incremental,
    )

    saved_ids = get_saved_ids(_COLLECTION, base_dir=save_path)
    logger.debug("[jobkorea] 기존 저장된 공고 수: %d", len(saved_ids))

    total_new = 0
    saved_file_path = ""

    with _JobkoreaCrawler() as crawler:
        for page_batch in crawler.collect_jobs_paged(
            query=query,
            saved_ids=saved_ids,
            max_pages=max_pages,
            incremental=incremental,
        ):
            if not page_batch:
                continue

            page_docs: list[dict[str, Any]] = [r.to_dict() for r in page_batch]
            saved_file = save_documents(
                documents=page_docs,
                collection_name=_COLLECTION,
                filename=filename,
                crawl_date=_crawl_date,
                base_dir=save_path,
                job_function_name=query,
            )
            total_new += len(page_docs)
            saved_file_path = str(saved_file)
            logger.info(
                "[jobkorea] 페이지 저장 완료 — 이번 배치: %d건, 누적 신규: %d건",
                len(page_docs), total_new,
            )

    logger.info("[jobkorea] 수집 완료 — 총 신규: %d건 (query=%r)", total_new, query)

    if not saved_file_path:
        logger.info("[jobkorea] 저장할 새 문서 없음")
        return ""

    return saved_file_path


def run_jobkorea_batch(
    job_functions: list[str],
    crawl_date: str | None = None,
    save_dir: str = "./data/raw_job_postings",
    max_pages: int = _MAX_PAGES,
    incremental: bool = True,
) -> None:
    """
    job_functions를 순회하며 crawl_jobkorea를 반복 호출한다.
    한 검색어가 실패해도 나머지는 계속 진행한다 (부분 실패 허용).

    ⚠️ robots.txt 미준수 — 상업적 목적 사용 전 법무 검토 필요.
    """
    run_query_batch(
        source_name=_SOURCE_NAME,
        job_functions=job_functions,
        crawl_fn=crawl_jobkorea,
        crawl_date=crawl_date,
        save_path=save_dir,
        max_pages=max_pages,
        incremental=incremental,
    )


# ---------------------------------------------------------------------------
# 내부 헬퍼 (사이트 전용 셀렉터 + 테스트 호환 래퍼)
# ---------------------------------------------------------------------------

def _is_blocked(html: str) -> bool:
    """HTML 응답에서 봇 차단 징후를 확인한다."""
    return is_blocked(html)


def _extract_job_id_from_card(card) -> str | None:
    """공고 카드에서 job_id를 추출한다."""
    for attr in ["data-gno", "data-no", "data-id", "data-jobid"]:
        val = card.get(attr, "").strip()
        if val and val.isdigit():
            return val

    for a_tag in card.find_all("a", href=re.compile(r"GI_Read/[0-9]+")):
        href = a_tag.get("href", "")
        m = re.search(r"GI_Read/([0-9]+)", href)
        if m:
            return m.group(1)

    return None


def _extract_detail_url(card, job_id: str) -> str:
    """카드에서 상세 URL을 추출한다. 없으면 job_id로 조립한다."""
    for a_tag in card.select("a[href*='GI_Read']"):
        href = a_tag.get("href", "")
        if href:
            return urljoin(_BASE_URL, href)
    return f"{_BASE_URL}{_DETAIL_PATH}{job_id}"


def _extract_card_text(card, selectors: list[str]) -> str:
    """카드 내 특정 셀렉터 목록에서 첫 번째로 매칭되는 텍스트를 반환한다."""
    for sel in selectors:
        tag = card.select_one(sel)
        if tag:
            return tag.get_text(strip=True)
    return ""


def _build_filename(query: str) -> str:
    """저장 파일명 조립. 예: jobkorea_백엔드_개발자"""
    return build_crawl_filename(_SOURCE_NAME, query)
