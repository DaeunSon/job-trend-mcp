"""
고용24(work24.go.kr) 크롤러.

주요 함수
---------
crawl_work24()       — 검색어 하나에 대한 공고를 수집해 raw_job_postings JSON으로 저장
run_work24_batch()   — job_functions를 순회하며 crawl_work24를 반복 호출

수집 방식
---------
1. 검색 결과 페이지를 POST 요청으로 순회
   - currentPageNo 파라미터로 페이지 이동
   - 첫 페이지에서 총 건수 파악 → 총 페이지 수 계산
2. 각 카드에서 wantedAuthNo, infoTypeCd 추출
   - infoTypeCd 가 EXCLUDED_INFO_TYPE_CDS(사람인/잡코리아/원티드)이면 건너뜀
   - (source_name, source_job_id) 가 이미 저장되어 있으면 건너뜀
3. 유효한 공고마다 상세 페이지 GET 요청 → raw_html 저장

중복 필터링
-----------
- 정보제공처 필터: EXCLUDED_INFO_TYPE_CDS 에 포함된 infoTypeCd 는 수집 안 함
- ID 중복 필터: 이미 저장된 (source_name, source_job_id) 는 건너뜀
- 추가 방어: 검색 시 siteClcd 파라미터로 알려진 제외 출처를 미리 필터링 시도
  (실제 동작 여부는 사이트 HTML 폼에서 확인 필요)

URL 구조 (2026-07-29 확인)
---------------------------
검색:  POST https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do
         form: srcKeyword={query} (필수 — keyword 단독 전송 시 필터 미적용)
               keyword={query}, keywordWantedTitle=Y, keywordBusiNm=Y, keywordJobCont=Y
상세:  GET  https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do
         ?wantedAuthNo={id}&infoTypeCd={code}&infoTypeGroup=tb_workinfogubun

source_job_id
-------------
상세 페이지 URL 의 wantedAuthNo 파라미터 값.
예: wantedAuthNo=ABC1234567890 → source_job_id = "ABC1234567890"

재택근무 siteClcd 필터
----------------------
고용24 검색 폼에 '재택근무 가능' 체크박스가 있음.
파라미터명 추정: reEmployee=Y 또는 homePossibleYn=Y.
정확한 값은 브라우저 개발자 도구 → Network → Form Data 로 확인 필요.
현재는 필터 없이 전체 수집 후 extractor 에서 재택근무 여부 판단.
"""
from __future__ import annotations

import json
import logging
import math
import time
import random
from datetime import date
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from src.crawlers.base_crawler import BaseCrawler
from src.crawlers.common import (
    BROWSER_USER_AGENT,
    DEFAULT_BLOCK_SIGNALS,
    build_crawl_filename,
    html_to_text,
    is_blocked,
)
from src.crawlers.work24.extractor import (
    extract_list_cards,
    extract_total_count,
    is_excluded_source,
)
from src.crawlers.work24.search_queries import (
    WORK24_SEARCH_QUERIES,
    get_queries_for_function,
)
from src.models.schemas import RawJobPosting
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.work24.go.kr"
_SEARCH_PATH = "/wk/a/b/1200/retriveDtlEmpSrchList.do"
_DETAIL_PATH = "/wk/a/b/1500/empDetailAuthView.do"
_RESULTS_PER_PAGE = 10          # 10 / 30 / 50 중 선택 가능. 초기에는 10 으로 안정적으로 시작.
_MAX_PAGES = 50
_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "work24"

# 고용24 추가 차단 징후 (common 기본셋 + "로봇")
_BLOCK_SIGNALS = (*DEFAULT_BLOCK_SIGNALS, "로봇")


# ---------------------------------------------------------------------------
# 내부 크롤러 클래스
# ---------------------------------------------------------------------------


class _Work24Crawler(BaseCrawler):
    """requests + BeautifulSoup 기반 고용24 크롤러."""

    def __init__(self) -> None:
        super().__init__(
            source_name=_SOURCE_NAME,
            base_url=_BASE_URL,
            user_agent=BROWSER_USER_AGENT,
            rate_limit_min=1.5,
            rate_limit_max=3.0,
        )
        self._session.headers.update(
            {
                "Referer": "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    def crawl(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("crawl_work24() 를 사용하세요.")

    # ------------------------------------------------------------------
    # 검색 결과 페이지 요청
    # ------------------------------------------------------------------

    def fetch_serp(self, query: str, page: int) -> tuple[BeautifulSoup, str] | None:
        """
        검색 결과 페이지를 요청하고 (BeautifulSoup, html) 튜플을 반환한다.
        차단 또는 실패 시 None 반환.

        고용24 는 POST 방식으로 검색 결과를 반환한다.

        검색어 파라미터 (2026-07-30 실측):
          - srcKeyword : 실제 검색어 (이 필드가 없으면 키워드 필터가 무시됨)
          - keyword    : 보조 필드 (원본 검색어 보존용, 단독 전송 시 미적용)
          - keywordWantedTitle / keywordBusiNm / keywordJobCont :
            제목·회사명·직무내용 검색 범위 플래그 (Y/N)
        """
        url = _BASE_URL + _SEARCH_PATH

        # siteClcd 복수 전달 방법 — 폼 필드를 같은 이름으로 여러 번 보내는 방식.
        # 고용24 사이트는 whitelist(포함) 방식이므로, 원하는 출처를 명시적으로 지정하는 대신
        # 전체 수집 후 infoTypeCd 로 제외 필터링하는 방식을 기본으로 한다.
        # (siteClcd 제외 목록을 모두 열거하면 새 출처 추가 시 누락 위험이 있음)
        form_data: dict[str, str] = {
            "searchMode": "Y",
            # srcKeyword 가 실질 검색 필터. keyword 만 보내면 전체 최신순(~14만 건)이 반환됨.
            "srcKeyword": query,
            "keyword": query,
            "keywordWantedTitle": "Y",
            "keywordBusiNm": "Y",
            "keywordJobCont": "Y",
            "keywordStaAreaNm": "N",
            "currentPageNo": str(page),
            "resultCnt": str(_RESULTS_PER_PAGE),
            "sortField": "DATE",
            "sortOrderBy": "DESC",
        }

        logger.info("[work24] SERP 요청 (page=%d, query=%r): %s", page, query, url)
        try:
            # POST 먼저 시도, 실패하면 GET fallback
            resp = self._session.post(
                url,
                data=form_data,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException:
            # GET fallback
            try:
                resp = self._session.get(
                    url,
                    params=form_data,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
            except requests.exceptions.RequestException as exc:
                logger.error("[work24] SERP 요청 실패 (page=%d): %s", page, exc)
                return None

        if _is_blocked(resp.text):
            logger.warning("[work24] 차단 감지 (SERP page=%d)", page)
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        return soup, resp.text

    def fetch_detail(
        self,
        wanted_auth_no: str,
        info_type_cd: str,
        info_type_group: str = "tb_workinfogubun",
    ) -> tuple[str, str] | None:
        """
        상세 페이지를 GET 요청하고 (raw_html, raw_text) 튜플을 반환한다.
        차단 또는 실패 시 None 반환.
        """
        params = {
            "wantedAuthNo": wanted_auth_no,
            "infoTypeCd": info_type_cd,
            "infoTypeGroup": info_type_group,
        }
        url = _BASE_URL + _DETAIL_PATH + "?" + urlencode(params)
        self._session.headers.update({"Referer": _BASE_URL + _SEARCH_PATH})

        logger.debug("[work24] 상세 요청: wantedAuthNo=%s, infoTypeCd=%s", wanted_auth_no, info_type_cd)
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.error(
                "[work24] 상세 요청 실패 (wantedAuthNo=%s): %s",
                wanted_auth_no, exc,
            )
            return None

        if _is_blocked(resp.text):
            logger.warning("[work24] 차단 감지 (상세 wantedAuthNo=%s)", wanted_auth_no)
            return None

        raw_html = resp.text
        raw_text = html_to_text(raw_html)
        return raw_html, raw_text

    # ------------------------------------------------------------------
    # 수집 오케스트레이션
    # ------------------------------------------------------------------

    def collect_jobs(
        self,
        query: str,
        saved_ids: set[tuple[str, str]],
        max_pages: int = _MAX_PAGES,
    ) -> list[dict[str, Any]]:
        """
        검색 결과 페이지를 순회하며 상세 페이지 HTML 을 수집한다.

        Parameters
        ----------
        query      : 검색어
        saved_ids  : 이미 저장된 (source_name, source_job_id) 세트 — 중복 건너뜀
        max_pages  : 최대 순회 페이지 수

        Returns
        -------
        수집된 RawJobPosting dict 목록
        """
        collected: list[dict[str, Any]] = []
        total_pages = max_pages
        consecutive_skip_pages = 0  # 연속 전체 스킵(이미 수집) 페이지 수

        for page in range(1, max_pages + 1):
            if page > total_pages:
                break

            result = self.fetch_serp(query, page)
            if result is None:
                logger.warning("[work24] SERP 실패 (page=%d) — 중단", page)
                break

            soup, serp_html = result

            # 1페이지에서 총 건수 파악 → 실제 총 페이지 수 계산
            if page == 1:
                total_count = extract_total_count(serp_html)
                if total_count == 0:
                    logger.info("[work24] 검색 결과 0건 (query=%r)", query)
                    return collected
                total_pages = min(
                    max_pages,
                    math.ceil(total_count / _RESULTS_PER_PAGE),
                )
                logger.info(
                    "[work24] query=%r — 총 %d건, %d페이지",
                    query, total_count, total_pages,
                )

            cards = extract_list_cards(serp_html)
            if not cards:
                logger.warning(
                    "[work24] 카드 추출 실패 (page=%d) — HTML 구조 변경 또는 마지막 페이지",
                    page,
                )
                break

            page_new = 0
            for card in cards:
                wanted_auth_no = card["wanted_auth_no"]
                info_type_cd = card["info_type_cd"]

                # ── 정보제공처 필터링 ──────────────────────────────────────────
                if is_excluded_source(info_type_cd):
                    logger.debug(
                        "[work24] 제외 출처 건너뜀: wantedAuthNo=%s, infoTypeCd=%s (%s)",
                        wanted_auth_no, info_type_cd,
                        _INFO_TYPE_CD_LABEL.get(info_type_cd, info_type_cd),
                    )
                    continue

                # ── 중복 건너뜀 ────────────────────────────────────────────────
                if (_SOURCE_NAME, wanted_auth_no) in saved_ids:
                    logger.debug("[work24] 이미 수집됨: wantedAuthNo=%s", wanted_auth_no)
                    continue

                # ── 상세 페이지 수집 ────────────────────────────────────────────
                try:
                    detail = self.fetch_detail(
                        wanted_auth_no=wanted_auth_no,
                        info_type_cd=info_type_cd,
                        info_type_group=card.get("info_type_group", "tb_workinfogubun"),
                    )
                except Exception as exc:
                    logger.warning(
                        "[work24] 상세 수집 예외 (wantedAuthNo=%s): %s",
                        wanted_auth_no, exc,
                    )
                    detail = None

                if detail is None:
                    logger.warning(
                        "[work24] 상세 수집 실패: wantedAuthNo=%s", wanted_auth_no
                    )
                    continue

                raw_html, _ = detail

                # raw_text 에 카드 메타 + 검색어를 JSON 으로 저장 (파싱 시 활용)
                raw_text_payload = json.dumps(
                    {
                        "search_query": query,
                        "card_meta": {
                            "wanted_auth_no": wanted_auth_no,
                            "info_type_cd": info_type_cd,
                            "title_raw": card.get("title_raw", ""),
                            "company_raw": card.get("company_raw", ""),
                            "provider_text": card.get("provider_text", ""),
                        },
                    },
                    ensure_ascii=False,
                )

                detail_url = card["detail_url"]
                raw = RawJobPosting(
                    source_name=_SOURCE_NAME,
                    source_job_id=wanted_auth_no,
                    original_url=detail_url,
                    raw_html=raw_html,
                    raw_text=raw_text_payload,
                )
                collected.append(raw.to_dict())
                saved_ids.add((_SOURCE_NAME, wanted_auth_no))
                page_new += 1

                self._wait()  # 상세 요청 간격

            logger.info("[work24] page=%d — 신규 수집 %d건 (누적 %d건)", page, page_new, len(collected))

            # 전체 스킵 페이지 연속 3번이면 중단 (이미 다 수집된 구간)
            if page_new == 0:
                consecutive_skip_pages += 1
                if consecutive_skip_pages >= 3:
                    logger.info("[work24] 연속 %d 페이지 전체 스킵 — 중단", consecutive_skip_pages)
                    break
            else:
                consecutive_skip_pages = 0

        return collected


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------


def crawl_work24(
    query: str | None = None,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_pages: int = _MAX_PAGES,
) -> str:
    """
    고용24에서 검색어 조건에 맞는 채용공고를 수집해 raw_job_postings JSON으로 저장한다.

    정보제공처가 사람인/잡코리아/원티드인 공고는 수집하지 않는다.
    이미 저장된 (source_name, source_job_id) 는 건너뛴다.

    Parameters
    ----------
    query       : 검색어. None 이면 빈 검색(전체 최신순).
    crawl_date  : 저장 경로 날짜 라벨 (YYYY-MM-DD). None 이면 오늘.
    save_path   : data 루트 경로. None 이면 프로젝트 기본값.
    max_pages   : 최대 순회 페이지 수 (기본 50).

    Returns
    -------
    저장된 파일 경로 문자열. 수집 건수가 0이면 빈 문자열.
    """
    today = date.today().isoformat()
    crawl_date = crawl_date or today
    query = (query or "").strip()

    logger.info("[work24] 수집 시작 — query=%r, date=%s", query or "(전체)", crawl_date)

    # 저장된 ID 로드 (중복 방지)
    saved_ids = get_saved_ids(_COLLECTION, base_dir=save_path)

    with _Work24Crawler() as crawler:
        collected = crawler.collect_jobs(
            query=query,
            saved_ids=saved_ids,
            max_pages=max_pages,
        )

    if not collected:
        logger.info("[work24] 신규 수집 건수 0 — 파일 저장 안 함")
        return ""

    # 파일명: work24_{query}.json (빈 검색이면 work24_전체.json)
    label = query if query else "전체"
    filename = build_crawl_filename(_SOURCE_NAME, label)

    from src.storage.json_writer import save_documents as _save
    dest = _save(
        documents=collected,
        collection_name=_COLLECTION,
        filename=filename,
        crawl_date=crawl_date,
        base_dir=save_path,
        job_function_name=query,
    )
    logger.info("[work24] 수집 완료 — %d건 저장: %s", len(collected), dest)
    return str(dest)


def run_work24_batch(
    job_functions: list[str] | None = None,
    crawl_date: str | None = None,
    save_dir: str | None = None,
    max_pages: int = _MAX_PAGES,
) -> None:
    """
    job_functions 를 순회하며 crawl_work24 를 반복 호출한다.

    한 검색어가 실패해도 나머지는 계속 진행한다 (부분 실패 허용).

    Parameters
    ----------
    job_functions : taxonomy job_function_name 목록.
                    None 이면 WORK24_SEARCH_QUERIES 전체 쿼리를 사용.
    crawl_date    : 저장 경로 날짜 라벨 (YYYY-MM-DD). None 이면 오늘.
    save_dir      : data 루트 경로. None 이면 프로젝트 기본값.
    max_pages     : 각 검색어당 최대 순회 페이지 수.
    """
    # 검색어 목록 결정
    if job_functions is None:
        queries = _flatten_queries(WORK24_SEARCH_QUERIES)
    else:
        queries = []
        for func in job_functions:
            queries.extend(get_queries_for_function(func))
        if not queries:
            logger.warning("[work24] 매핑된 검색어 없음 (job_functions=%r)", job_functions)
            return

    logger.info("[work24] 배치 시작 — %d개 검색어", len(queries))

    ok = 0
    fail = 0
    for query in queries:
        try:
            result = crawl_work24(
                query=query,
                crawl_date=crawl_date,
                save_path=save_dir,
                max_pages=max_pages,
            )
            if result:
                ok += 1
            # 0건 수집은 ok 로 카운트하지 않되 실패도 아님
        except Exception as exc:
            fail += 1
            logger.error(
                "[work24] 검색어 실패 (query=%r): %s",
                query, exc, exc_info=True,
            )
        # 검색어 간 추가 대기
        time.sleep(random.uniform(2.0, 4.0))

    logger.info(
        "[work24] 배치 완료 — 성공(저장): %d, 실패: %d / 전체 %d개 검색어",
        ok, fail, len(queries),
    )


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

#: infoTypeCd → 사람이 읽을 수 있는 이름 (로그용)
#: siteClcd 실측 결과 (2026-07-29):
#:   CSI=사람인(32,045건), CWT=원티드(2,441건), WK=고용24(0 IT건)
_INFO_TYPE_CD_LABEL: dict[str, str] = {
    "CSI": "사람인",
    "CJK": "잡코리아",
    "CIN": "인크루트",
    "CLE": "클린아이",
    "CWT": "원티드",
    "WK":  "고용24",
    "NR":  "나라일터",
    "AL":  "알리오",
    "BY":  "병역일터",
}


def _is_blocked(html: str) -> bool:
    """차단 신호가 HTML 에 포함되어 있으면 True."""
    return is_blocked(html, signals=_BLOCK_SIGNALS)


def _flatten_queries(mapping: dict[str, list[str]]) -> list[str]:
    """중복 없이 평탄화된 검색어 목록을 반환한다."""
    seen: set[str] = set()
    result: list[str] = []
    for queries in mapping.values():
        for q in queries:
            if q not in seen:
                seen.add(q)
                result.append(q)
    return result
