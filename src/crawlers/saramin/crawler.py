"""
사람인 크롤러.

주요 함수
---------
crawl_saramin()         — 검색어 하나에 대한 공고를 수집해 raw_job_postings JSON으로 저장
run_saramin_batch()     — job_functions를 순회하며 crawl_saramin을 반복 호출

수집 방식
---------
1. 검색 결과 SERP 페이지 순회 (recruitPage 파라미터)
   - "총 N건" 텍스트로 전체 건수 파악 → 총 페이지 수 계산
   - 각 카드에서 rec_idx, 회사명, 공고명, 지역, 경력, 학력, 고용형태, 마감일 추출
2. 상세 페이지 요청 (rec_idx 기준) → raw_html 저장
   - 상세 페이지 방문 전에 이미 저장된 (source_name, source_job_id) 중복 체크

URL 구조
--------
SERP:   https://www.saramin.co.kr/zf_user/search/recruit
        ?searchword={query}&recruitPage={n}&recruitPageCount=40
상세:   https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx}

source_job_id
--------------
사람인 공고 카드 href의 rec_idx 파라미터 값.
예: /zf_user/jobs/relay/view?rec_idx=49283710 → source_job_id = "49283710"
"""
from __future__ import annotations

import copy
import logging
import re
from datetime import date
from typing import Any, Iterator
from urllib.parse import urlencode

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
from src.storage.json_writer import (
    get_saved_ids,
    load_all_documents_in_collection,
    save_documents,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.saramin.co.kr"
_SEARCH_PATH = "/zf_user/search/recruit"
_DETAIL_PATH = "/zf_user/jobs/view"
_RELAY_PATH = "/zf_user/jobs/relay/view"
_RESULTS_PER_PAGE = 40
_MAX_PAGES = 50
_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "saramin"

_TOTAL_COUNT_SELECTORS = (
    "span.cnt_result",
    ".cnt-all em",
    ".recruit-info .cnt strong em",
    ".cnt-area .total em",
    "strong.total em",
    ".search-count em",
    ".header-sort strong em",
)


# ---------------------------------------------------------------------------
# 내부 크롤러 클래스
# ---------------------------------------------------------------------------

class _SaraminCrawler(HtmlSerpCrawler):
    """requests + BeautifulSoup 기반 사람인 크롤러."""

    # class attr — __init__ 없이 __new__ 하는 테스트에서도 self.source_name 사용 가능
    source_name = _SOURCE_NAME
    results_per_page = _RESULTS_PER_PAGE
    default_max_pages = _MAX_PAGES
    job_id_field = "rec_idx"

    def __init__(self) -> None:
        super().__init__(
            source_name=_SOURCE_NAME,
            base_url=_BASE_URL,
            user_agent=BROWSER_USER_AGENT,
            rate_limit_min=1.0,
            rate_limit_max=2.5,
        )
        self._session.headers.update(
            {
                "Referer": "https://www.saramin.co.kr/",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
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
            "searchword": query,
            "recruitPage": str(page),
            "recruitPageCount": str(_RESULTS_PER_PAGE),
        }
        url = _BASE_URL + _SEARCH_PATH + "?" + urlencode(params, encoding="utf-8")

        logger.info("[saramin] SERP 요청 (page=%d): %s", page, url)
        try:
            resp = self.get(url)
        except requests.exceptions.RequestException as exc:
            logger.error("[saramin] SERP 요청 실패 (page=%d): %s", page, exc)
            return None

        if is_blocked(resp.text):
            logger.warning(
                "[saramin] 차단 감지 (SERP page=%d) — 응답 앞 200자: %s",
                page, resp.text[:200],
            )
            return None

        return BeautifulSoup(resp.text, "lxml")

    def get_total_count(self, soup: BeautifulSoup) -> int:
        """검색 결과 총 건수를 파싱한다. 파싱 실패 시 0 반환."""
        return parse_total_count(soup, selectors=_TOTAL_COUNT_SELECTORS)

    def extract_job_cards(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        """
        SERP HTML에서 공고 카드 정보를 추출한다.

        사람인 SERP 구조 (2026년 기준):
          카드:      article.list-post  또는  div.list-post
          rec_idx:   href 내 rec_idx=숫자 패턴  또는  data-rec-idx 속성
          제목:      a.str-tit span.tit  또는  .job-tit a
          회사명:    strong.corp-name a  또는  a.str-co
          조건칩:    dl.job-condition dt/dd 또는 ul.job-condition li span
          마감일:    .deadlines span.date  또는  .date-info

        Returns
        -------
        list of dict: rec_idx, title, company, location, career_type,
                      education, employment_type, deadline, detail_url
        """
        cards: list[dict[str, str]] = []
        seen: set[str] = set()

        card_els = soup.find_all("div", class_="item_recruit")
        if not card_els:
            card_els = soup.find_all("article", class_="list-post")
        if not card_els:
            card_els = soup.select("div.list-post")
        if not card_els:
            card_els = soup.select(".item-recruit")

        for card in card_els:
            rec_idx = _extract_rec_idx_from_card(card)
            if not rec_idx or rec_idx in seen:
                continue
            seen.add(rec_idx)

            location, career_type, education, employment_type = (
                _extract_conditions_from_card(card)
            )
            cards.append({
                "rec_idx": rec_idx,
                "title": _extract_title_from_card(card),
                "company": _extract_company_from_card(card),
                "location": location,
                "career_type": career_type,
                "education": education,
                "employment_type": employment_type,
                "deadline": _extract_deadline_from_card(card),
                "detail_url": _build_detail_url(rec_idx),
            })

        if not cards:
            logger.debug(
                "[saramin] SERP 카드 추출 실패 — list-post 없음. "
                "HTML 구조 변경 여부 확인 필요."
            )

        return cards

    # ------------------------------------------------------------------
    # 상세 페이지
    # ------------------------------------------------------------------

    def fetch_detail(self, rec_idx: str) -> tuple[str, str] | None:
        """
        상세 페이지를 요청하고 (raw_html, raw_text) 튜플을 반환한다.
        차단 또는 실패 시 None 반환.

        canonical URL(/jobs/view)로 요청해 서버 사이드 렌더링 콘텐츠를 수집한다.
        relay/view 페이지는 wrap_jview 콘텐츠를 JS로 동적 로드하므로
        정적 크롤링 시 공고 본문이 비어 있다.
        """
        url = _BASE_URL + _DETAIL_PATH
        params = {"rec_idx": rec_idx}
        full_url = url + "?" + urlencode(params, encoding="utf-8")

        self._session.headers.update({"Referer": _BASE_URL + _SEARCH_PATH})
        try:
            resp = self.get(full_url)
        except requests.exceptions.RequestException as exc:
            logger.error("[saramin] 상세 페이지 요청 실패 (%s): %s", rec_idx, exc)
            return None

        if is_blocked(resp.text):
            logger.warning(
                "[saramin] 차단 감지 (상세 rec_idx=%s) — 응답 앞 200자: %s",
                rec_idx, resp.text[:200],
            )
            return None

        return resp.text, html_to_text(resp.text)

    def fetch_detail_for_collect(
        self,
        job_id: str,
        query: str,
        card: dict[str, str],
    ) -> tuple[str, str] | None:
        return self.fetch_detail(job_id)

    def build_original_url(self, job_id: str, card: dict[str, str]) -> str:
        return _build_detail_url(job_id)

    # ------------------------------------------------------------------
    # 수집 오케스트레이션
    # ------------------------------------------------------------------

    def collect_jobs_paged(  # type: ignore[override]
        self,
        query: str,
        saved_ids: set[tuple[str, str]],
        max_pages: int = _MAX_PAGES,
        force: bool = False,
    ) -> Iterator[list[RawJobPosting]]:
        """
        SERP 페이지를 순회하며 상세 페이지 HTML을 수집하고,
        한 SERP 페이지분의 결과를 모을 때마다 yield 한다.

        Parameters
        ----------
        force : True 이면 saved_ids 에 있어도 재수집한다
        """
        yield from super().collect_jobs_paged(
            query=query,
            saved_ids=saved_ids,
            max_pages=max_pages,
            duplicate_mode="refetch" if force else "skip",
        )


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _load_existing_raw_by_job_id(
    filename: str,
    crawl_date: str,
    base_dir: str | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """
    동일 파일에 이미 저장된 raw 문서를 (source_name, source_job_id) → doc 으로 반환한다.

    force 재수집 시 기존 id / collected_at 을 유지하기 위해 사용한다.
    파일이 없으면 빈 dict.
    """
    docs = load_all_documents_in_collection(_COLLECTION, base_dir)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for doc in docs:
        sn = doc.get("source_name")
        sid = doc.get("source_job_id")
        if sn and sid:
            result[(sn, sid)] = doc
    return result


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def crawl_saramin(
    query: str,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_pages: int = _MAX_PAGES,
    force: bool = False,
) -> str:
    """
    사람인에서 주어진 검색어 하나에 대한 채용공고를 수집해
    raw_job_postings 구조의 JSON으로 저장한다.
    이미 저장된 (source_name, source_job_id) 조합은 건너뛴다.

    force=True 이면 기존 공고도 다시 수집해 raw_html 을 갱신하고
    parse_status 를 PENDING 으로 되돌린다. 파일을 삭제할 필요 없다.
    """
    if not query or not query.strip():
        raise ValueError("query는 필수 파라미터입니다.")

    _crawl_date = crawl_date or date.today().isoformat()
    filename = _build_filename(query)

    logger.info(
        "[saramin] crawl_saramin 시작 — query=%r, crawl_date=%s, max_pages=%d, force=%s",
        query, _crawl_date, max_pages, force,
    )

    saved_ids = set() if force else get_saved_ids(_COLLECTION, base_dir=save_path)
    existing_raw_by_job_id = _load_existing_raw_by_job_id(
        filename=filename,
        crawl_date=_crawl_date,
        base_dir=save_path,
    )
    logger.debug("[saramin] 기존 저장된 공고 수: %d", len(saved_ids))

    total_new = 0
    saved_file_path = ""

    with _SaraminCrawler() as crawler:
        for page_batch in crawler.collect_jobs_paged(
            query=query,
            saved_ids=saved_ids,
            max_pages=max_pages,
            force=force,
        ):
            if not page_batch:
                continue

            page_docs: list[dict[str, Any]] = []
            for raw in page_batch:
                doc = raw.to_dict()
                key = (doc["source_name"], doc["source_job_id"])
                existing = existing_raw_by_job_id.get(key)
                if existing:
                    doc["id"] = existing["id"]
                    doc["collected_at"] = existing.get("collected_at", doc["collected_at"])
                if force or existing:
                    doc["parse_status"] = "PENDING"
                    doc["parsed_job_posting_id"] = None
                page_docs.append(doc)

            saved_file = save_documents(
                documents=page_docs,
                collection_name=_COLLECTION,
                filename=filename,
                crawl_date=_crawl_date,
                base_dir=save_path,
                job_function_name=query,
                upsert=force,
                upsert_keys=("source_name", "source_job_id"),
            )
            for doc in page_docs:
                existing_raw_by_job_id[(doc["source_name"], doc["source_job_id"])] = doc
            total_new += len(page_docs)
            saved_file_path = str(saved_file)
            logger.info(
                "[saramin] 페이지 저장 완료 — 이번 배치: %d건, 누적 처리: %d건",
                len(page_docs), total_new,
            )

    logger.info("[saramin] 수집 완료 — 총 처리: %d건 (query=%r)", total_new, query)

    if not saved_file_path:
        logger.info("[saramin] 저장할 새 문서 없음")
        return ""

    return saved_file_path


def run_saramin_batch(
    job_functions: list[str],
    crawl_date: str | None = None,
    save_dir: str | None = None,
    force: bool = False,
) -> None:
    """
    job_functions를 순회하며 crawl_saramin을 반복 호출한다.
    한 검색어가 실패해도 나머지는 계속 진행한다 (부분 실패 허용).
    """
    run_query_batch(
        source_name=_SOURCE_NAME,
        job_functions=job_functions,
        crawl_fn=crawl_saramin,
        crawl_date=crawl_date,
        save_path=save_dir,
        force=force,
    )


# ---------------------------------------------------------------------------
# 내부 헬퍼 (사이트 전용 셀렉터 + 테스트 호환 래퍼)
# ---------------------------------------------------------------------------

def _is_blocked(html: str) -> bool:
    """HTML 응답에서 봇 차단 징후를 확인한다."""
    return is_blocked(html)


def _extract_rec_idx_from_card(card) -> str | None:
    """공고 카드에서 rec_idx를 추출한다."""
    val = card.get("value", "").strip()
    if val and val.isdigit():
        return val

    for attr in ["data-rec-idx", "data-position-idx", "data-idx", "data-id"]:
        val = card.get(attr, "").strip()
        if val and val.isdigit():
            return val

    for a_tag in card.find_all("a", href=re.compile(r"rec_idx=\d+")):
        href = a_tag.get("href", "")
        m = re.search(r"rec_idx=(\d+)", href)
        if m:
            return m.group(1)

    return None


def _extract_title_from_card(card) -> str:
    """공고 카드에서 공고 제목을 추출한다."""
    tit_tag = card.select_one("h2.job_tit a")
    if tit_tag:
        return tit_tag.get_text(strip=True)

    tit_a = card.select_one("a.str-tit")
    if tit_a:
        span = tit_a.select_one("span.tit, span")
        if span:
            return span.get_text(strip=True)
        return tit_a.get_text(strip=True)

    for sel in [".job_tit a", ".job-tit a", ".tit a", "h2.tit a", ".str-tit"]:
        tag = card.select_one(sel)
        if tag:
            return tag.get_text(strip=True)

    return ""


def _extract_company_from_card(card) -> str:
    """공고 카드에서 회사명을 추출한다."""
    for sel in [
        ".corp_name a", "a.corp_name",
        ".company_name a", "a.company_name",
    ]:
        tag = card.select_one(sel)
        if tag:
            return tag.get_text(strip=True)

    corp_strong = card.select_one("strong.corp-name, .corp_name, .corp-name")
    if corp_strong:
        a_tag = corp_strong.select_one("a")
        if a_tag:
            return a_tag.get_text(strip=True)
        return corp_strong.get_text(strip=True)

    for sel in ["a.str-co", ".company-name a", ".coName a"]:
        tag = card.select_one(sel)
        if tag:
            return tag.get_text(strip=True)

    return ""


def _extract_conditions_from_card(
    card,
) -> tuple[str, str, str, str]:
    """
    공고 카드의 조건 영역에서 (location, career_type, education, employment_type) 추출.
    """
    location = ""
    career_type = ""
    education = ""
    employment_type = ""

    cond_div = card.select_one(".job_condition")
    if cond_div:
        texts = []
        for s in cond_div.select("span"):
            s_copy = copy.copy(s)
            for blind in s_copy.select("em.blind, span.blind"):
                blind.decompose()
            text = s_copy.get_text(strip=True)
            if text:
                texts.append(text)
        return _assign_conditions(texts)

    cond_dl = card.select_one("dl.job-condition")
    if cond_dl:
        texts = [dd.get_text(strip=True) for dd in cond_dl.select("dd") if dd.get_text(strip=True)]
        return _assign_conditions(texts)

    cond_ul = card.select_one("ul.job-condition")
    if cond_ul:
        texts = []
        for li in cond_ul.select("li"):
            for blind in li.select("em.blind, span.blind"):
                blind.decompose()
            text = li.get_text(strip=True)
            if text:
                texts.append(text)
        return _assign_conditions(texts)

    cond_div = card.select_one(".job-condition, .condition-list")
    if cond_div:
        texts = [s.get_text(strip=True) for s in cond_div.select("span") if s.get_text(strip=True)]
        return _assign_conditions(texts)

    return location, career_type, education, employment_type


def _assign_conditions(texts: list[str]) -> tuple[str, str, str, str]:
    """
    조건 텍스트 목록에서 (location, career_type, education, employment_type)을 분류한다.
    순서에 의존하지 않고 키워드 기반으로 분류한다.
    """
    location = ""
    career_type = ""
    education = ""
    employment_type = ""

    _REGIONS = [
        "서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종",
        "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "전국",
    ]
    _CAREER_KEYWORDS = ["신입", "경력", "경력무관"]
    _EDUCATION_KEYWORDS = ["고졸", "대졸", "초대졸", "대학교", "학력", "무관", "석사", "박사"]
    _EMPLOYMENT_KEYWORDS = ["정규직", "계약직", "아르바이트", "인턴", "프리랜서", "파트타임", "파견직"]

    for text in texts:
        if not text:
            continue
        text_s = text.strip()

        if not employment_type and any(kw in text_s for kw in _EMPLOYMENT_KEYWORDS):
            employment_type = text_s
        elif not education and any(kw in text_s for kw in _EDUCATION_KEYWORDS):
            education = text_s
        elif not career_type and any(kw in text_s for kw in _CAREER_KEYWORDS):
            career_type = text_s
        elif not location and any(text_s.startswith(r) for r in _REGIONS):
            location = text_s

    if not any([location, career_type, education, employment_type]) and texts:
        location = texts[0] if len(texts) > 0 else ""
        career_type = texts[1] if len(texts) > 1 else ""
        education = texts[2] if len(texts) > 2 else ""
        employment_type = texts[3] if len(texts) > 3 else ""

    return location, career_type, education, employment_type


def _extract_deadline_from_card(card) -> str:
    """공고 카드에서 마감일을 추출한다 (D-day 또는 날짜 문자열)."""
    for sel in [
        ".job_date .date",
        ".job_date span",
        ".deadlines span.date",
        ".date-info .date",
        ".deadline span",
        "span.date",
        ".dday",
    ]:
        tag = card.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            if text and text != "상시채용":
                return text

    for tag in card.find_all(["span", "div", "p"]):
        text = tag.get_text(strip=True)
        if re.search(r"D[+-]?\d+|\d{4}\.\d{2}\.\d{2}|\d{4}-\d{2}-\d{2}", text):
            return text

    return ""


def _build_detail_url(rec_idx: str) -> str:
    """사용자용 공고 URL(relay)을 조립한다."""
    return f"{_BASE_URL}{_RELAY_PATH}?rec_idx={rec_idx}"


def _build_filename(query: str) -> str:
    """저장 파일명 조립. 예: saramin_백엔드_개발자"""
    return build_crawl_filename(_SOURCE_NAME, query)
