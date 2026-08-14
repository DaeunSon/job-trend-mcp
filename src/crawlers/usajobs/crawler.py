"""
USAJobs 크롤러.

주요 함수
---------
crawl_usajobs()       — keyword/직무에 맞는 공고를 수집해 raw_job_postings JSON 저장
run_usajobs_batch()   — job_functions 를 순회하며 crawl_usajobs 반복 호출

수집 방식 (0단계 조사 결과 — 내부 JSON API, 2026-07-30 확인)
--------------------------------------------------------------
검색 페이지(/search?k=...)는 초기 HTML에 공고가 없고, searchmain.js 가
POST /Search/ExecuteSearch 로 결과를 채운다.

  1) GET  /Search/Results?...   → 세션 쿠키(akavpau_usajobs 등) 시드
  2) POST /Search/ExecuteSearch → JSON { Total, Pager, Jobs: [...] }

★ 세션 쿠키 유지 필수
  GET 과 POST 는 반드시 동일 requests.Session() 을 써야 한다.
  BaseCrawler._session 하나로 시드·검색을 모두 수행한다.
  연결을 매번 새로 열면 쿠키가 끊겨 검색이 실패할 수 있다.

★ User-Agent 고정
  Akamai가 봇성 UA에 403을 줄 수 있음.
  src.config.sources.USAJOBS_USER_AGENT (2026-07-30 실측 성공값)만 사용.
  임의 변경 금지.

raw_job_postings 저장 규칙
--------------------------
- raw_text  : Jobs[] 항목 1건의 JSON (상세에서 급여 보강 필드 주입)
- raw_html  : 공고 상세 페이지 HTML (/job/{DocumentID})
- source_job_id : str(DocumentID)
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import date
from typing import Any

import requests

from src.config.sources import USAJOBS_USER_AGENT
from src.crawlers.base_crawler import BaseCrawler
from src.crawlers.usajobs.extractor import apply_detail_salary_to_job
from src.crawlers.usajobs.search_queries import get_keywords_for_function
from src.crawlers.usajobs.session_client import USAJobsSessionClient
from src.models.schemas import RawJobPosting
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.usajobs.gov"
_RESULTS_PATH = "/Search/Results"
_SEARCH_PATH = "/Search/ExecuteSearch"
_RESULTS_URL = (
    f"{_BASE_URL}{_RESULTS_PATH}"
    "?hp=public&s=startdate&sd=desc&p=1"
)
_SEARCH_URL = f"{_BASE_URL}{_SEARCH_PATH}"

_RESULTS_PER_PAGE = 50
_MAX_PAGES = 40  # 50 * 40 = 2000건 상한 (ExecuteSearch Total 기준)
_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "usajobs"

# 고정 UA — sources.USAJOBS_USER_AGENT 와 동일 객체(문자열)를 써야 한다.
_USER_AGENT = USAJOBS_USER_AGENT

_BLOCK_SIGNALS = [
    "access denied",
    "robot or human",
    "just a moment",
    "please enable javascript",
    "human verification",
    "bot detection",
    "cloudflare",
]


# ---------------------------------------------------------------------------
# 내부 크롤러 클래스
# ---------------------------------------------------------------------------

class _USAJobsCrawler(BaseCrawler):
    """
    USAJobs 내부 JSON API 크롤러.

    동일 self._session(requests.Session)으로
    GET(쿠키 시드) → POST(검색) 순서를 유지한다.
    """

    def __init__(self) -> None:
        super().__init__(
            source_name=_SOURCE_NAME,
            base_url=_BASE_URL,
            user_agent=_USER_AGENT,
            rate_limit_min=1.0,
            rate_limit_max=2.0,
        )
        # Accept 등은 요청별로 달라지므로 세션 공통 헤더는 UA·언어만 유지.
        self._session.headers.update(
            {
                "User-Agent": _USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Origin": _BASE_URL,
            }
        )
        # GET-시드 → POST 는 USAJobs 전용 SessionClient 에 위임
        # (BaseCrawler 확장 대신 — 재사용처가 없는 패턴)
        self._session_client = USAJobsSessionClient(
            self._session,
            user_agent=_USER_AGENT,
            wait_fn=self._wait,
            retry_count=self.retry_count,
            timeout=self.timeout,
            is_blocked_fn=_is_blocked,
            results_url=_RESULTS_URL,
            base_url=_BASE_URL,
        )

    @property
    def _session_seeded(self) -> bool:
        """테스트·하위 호환 — SessionClient 상태 노출."""
        return self._session_client.session_seeded

    def crawl(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("crawl_usajobs() 를 사용하세요.")

    def seed_session(self, force: bool = False) -> bool:
        """GET /Search/Results 로 세션 쿠키를 심는다."""
        return self._session_client.seed_session(force=force)

    # ------------------------------------------------------------------
    # 검색 API
    # ------------------------------------------------------------------

    def execute_search(
        self,
        keyword: str,
        page: int = 1,
        results_per_page: int = _RESULTS_PER_PAGE,
    ) -> dict[str, Any] | None:
        """
        POST /Search/ExecuteSearch (시드된 동일 Session 사용).

        Returns
        -------
        응답 JSON dict, 또는 실패 시 None
        """
        if not self.seed_session():
            return None

        payload = {
            "Keyword": keyword,
            "HiringPath": ["public"],
            "SortField": "startdate",
            "SortDirection": "desc",
            "Page": str(page),
            "ResultsPerPage": results_per_page,
        }

        logger.info(
            "[usajobs] ExecuteSearch POST (keyword=%r, page=%d, Session id=%s, cookies=%s)",
            keyword,
            page,
            id(self._session),
            list(self._session.cookies.keys()),
        )

        try:
            resp = self._session_client.post_json(_SEARCH_URL, payload)
        except requests.exceptions.RequestException as exc:
            logger.error(
                "[usajobs] ExecuteSearch 실패 (keyword=%r, page=%d): %s",
                keyword, page, exc,
            )
            return None

        if _is_blocked(resp.text):
            logger.warning(
                "[usajobs] 차단 감지 (keyword=%r, page=%d) — 세션 재시드 시도",
                keyword, page,
            )
            if not self.seed_session(force=True):
                return None
            try:
                resp = self._session_client.post_json(_SEARCH_URL, payload)
            except requests.exceptions.RequestException as exc:
                logger.error("[usajobs] 재시드 후 ExecuteSearch 실패: %s", exc)
                return None
            if _is_blocked(resp.text):
                logger.warning("[usajobs] 재시드 후에도 차단 — 중단")
                return None

        try:
            data = resp.json()
        except ValueError as exc:
            logger.error(
                "[usajobs] ExecuteSearch JSON 파싱 실패 (keyword=%r): %s — body(200자)=%s",
                keyword, exc, resp.text[:200],
            )
            return None

        if not isinstance(data, dict) or data.get("IsValid") is False:
            logger.warning(
                "[usajobs] ExecuteSearch 무효 응답 (keyword=%r, page=%d): %s",
                keyword, page, data,
            )
            return None

        return data

    # ------------------------------------------------------------------
    # 수집 오케스트레이션
    # ------------------------------------------------------------------

    def collect_jobs(
        self,
        keyword: str,
        saved_ids: set[tuple[str, str]],
        max_pages: int = _MAX_PAGES,
        max_jobs: int | None = None,
        results_per_page: int = _RESULTS_PER_PAGE,
    ) -> list[RawJobPosting]:
        """키워드 하나로 페이지를 순회하며 RawJobPosting 목록을 반환한다."""
        results: list[RawJobPosting] = []
        page = 1

        while page <= max_pages:
            data = self.execute_search(
                keyword=keyword,
                page=page,
                results_per_page=results_per_page,
            )
            if data is None:
                logger.warning(
                    "[usajobs] 응답 없음 (keyword=%r, page=%d) — 수집 중단",
                    keyword, page,
                )
                break

            jobs = data.get("Jobs") or []
            if not isinstance(jobs, list) or not jobs:
                logger.info(
                    "[usajobs] 더 이상 공고 없음 (keyword=%r, page=%d) — 완료",
                    keyword, page,
                )
                break

            total = data.get("Total", "?")
            pager = data.get("Pager") or {}
            logger.info(
                "[usajobs] keyword=%r page=%d — %d건 / Total=%s",
                keyword, page, len(jobs), total,
            )

            for job in jobs:
                if not isinstance(job, dict):
                    continue
                doc_id = job.get("DocumentID")
                if doc_id is None:
                    logger.debug("[usajobs] DocumentID 없음, 건너뜀: %r", job.get("Title"))
                    continue
                sid = str(doc_id)
                if (_SOURCE_NAME, sid) in saved_ids:
                    logger.debug("[usajobs] 이미 저장됨, 건너뜀: %s", sid)
                    continue

                uri = (job.get("PositionURI") or "").replace(":443", "").strip()
                if not uri:
                    uri = f"https://www.usajobs.gov/job/{sid}"

                # 검색 API만으로는 본문·max 급여가 없으므로 상세 페이지를 함께 수집
                job, detail_html = self._fetch_job_detail(job, sid, uri)

                posting = RawJobPosting(
                    source_name=_SOURCE_NAME,
                    source_job_id=sid,
                    original_url=uri,
                    raw_html=detail_html,
                    raw_text=json.dumps(job, ensure_ascii=False),
                )
                results.append(posting)
                saved_ids.add((_SOURCE_NAME, sid))

                if max_jobs is not None and len(results) >= max_jobs:
                    logger.info("[usajobs] max_jobs=%d 도달 — 수집 중단", max_jobs)
                    return results

            if not _has_next_page(pager, page):
                logger.info(
                    "[usajobs] 마지막 페이지 (keyword=%r, page=%d)",
                    keyword, page,
                )
                break

            page += 1

        logger.info(
            "[usajobs] keyword=%r — 신규 %d건 수집",
            keyword, len(results),
        )
        return results

    def _fetch_job_detail(
        self,
        job: dict[str, Any],
        document_id: str,
        uri: str,
    ) -> tuple[dict[str, Any], str]:
        """
        공고 상세 HTML을 가져와 raw_html 용으로 반환하고,
        RemunerationMaximumAmount / 급여 범위를 job dict 에 주입한다.

        실패 시 (job 원본, "").
        """
        detail_url = uri or f"{_BASE_URL}/job/{document_id}"
        try:
            response = self.get(detail_url)
            html = response.text or ""
        except Exception as exc:
            logger.warning(
                "[usajobs] 상세 페이지 수집 실패 (%s): %s",
                document_id, exc,
            )
            return job, ""

        if not html or _is_blocked(html):
            logger.warning(
                "[usajobs] 상세 페이지 차단/빈 응답 — 생략 (%s)",
                document_id,
            )
            return job, ""

        apply_detail_salary_to_job(job, html)
        logger.debug(
            "[usajobs] 상세 수집: %s html=%dB max=%s",
            document_id,
            len(html),
            job.get("MaximumRange"),
        )
        return job, html


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def crawl_usajobs(
    query: str,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_pages: int = _MAX_PAGES,
    max_jobs: int | None = None,
) -> str:
    """
    USAJobs에서 검색어에 맞는 채용공고를 수집해 raw_job_postings JSON으로 저장한다.
    이미 저장된 (source_name, source_job_id)는 건너뛴다.

    Parameters
    ----------
    query       : taxonomy job_function_name 또는 영문 키워드
    crawl_date  : 저장 경로용 날짜 라벨. None이면 오늘
    save_path   : 저장 기준 디렉토리 (data 루트). None이면 기본값
    max_pages   : 키워드별 최대 페이지 수
    max_jobs    : 키워드 합산 최대 수집 건수. None이면 제한 없음

    Returns
    -------
    저장된 JSON 경로 문자열 (저장 없으면 "")
    """
    if crawl_date is None:
        crawl_date = date.today().isoformat()

    keywords = _resolve_keywords(query)
    saved_ids = get_saved_ids(_COLLECTION, base_dir=save_path)
    all_postings: list[RawJobPosting] = []

    # ★ 한 번의 with 블록 = 하나의 Session. 시드·모든 POST가 같은 쿠키 jar를 공유.
    with _USAJobsCrawler() as crawler:
        assert isinstance(crawler, _USAJobsCrawler)
        if not crawler.seed_session():
            logger.error("[usajobs] 초기 세션 시드 실패 — 수집 중단 (query=%r)", query)
            return ""

        for kw in keywords:
            postings = crawler.collect_jobs(
                keyword=kw,
                saved_ids=saved_ids,
                max_pages=max_pages,
                max_jobs=(
                    None if max_jobs is None
                    else max(0, max_jobs - len(all_postings))
                ),
            )
            all_postings.extend(postings)

            if max_jobs is not None and len(all_postings) >= max_jobs:
                all_postings = all_postings[:max_jobs]
                logger.info("[usajobs] max_jobs=%d 도달 — 키워드 순회 중단", max_jobs)
                break

            if len(keywords) > 1:
                wait = random.uniform(2.0, 4.0)
                logger.debug("[usajobs] 다음 키워드까지 %.1fs 대기", wait)
                time.sleep(wait)

    if not all_postings:
        logger.info("[usajobs] '%s' — 신규 공고 없음", query)
        return ""

    docs = [p.to_dict() for p in all_postings]
    safe_query = query.replace("/", "_").replace(" ", "_")
    filename = f"usajobs_{safe_query}"

    saved = save_documents(
        documents=docs,
        collection_name=_COLLECTION,
        filename=filename,
        crawl_date=crawl_date,
        base_dir=save_path,
        job_function_name=query,
    )
    logger.info(
        "[usajobs] '%s' 수집 완료 — %d건 저장 → %s",
        query, len(docs), saved,
    )
    return str(saved)


def run_usajobs_batch(
    job_functions: list[str],
    crawl_date: str | None = None,
    save_dir: str = "./data/raw_job_postings",
    max_pages: int = _MAX_PAGES,
    max_jobs: int | None = None,
) -> None:
    """
    job_functions를 순회하며 crawl_usajobs를 반복 호출한다.
    한 검색어가 실패해도 나머지는 계속 진행한다 (부분 실패 허용).
    """
    if crawl_date is None:
        crawl_date = date.today().isoformat()

    logger.info(
        "[usajobs] 배치 시작 — %d개 직무, crawl_date=%s, max_pages=%d%s",
        len(job_functions), crawl_date, max_pages,
        f", max_jobs={max_jobs}" if max_jobs else "",
    )

    success_count = 0
    fail_count = 0

    for i, func in enumerate(job_functions, 1):
        logger.info("[usajobs] [%d/%d] '%s' 수집 시작", i, len(job_functions), func)
        try:
            result = crawl_usajobs(
                query=func,
                crawl_date=crawl_date,
                save_path=str(save_dir).removesuffix("/raw_job_postings"),
                max_pages=max_pages,
                max_jobs=max_jobs,
            )
            if result:
                success_count += 1
            else:
                logger.info("[usajobs] '%s' — 결과 없음 (건너뜀)", func)
        except Exception as exc:
            fail_count += 1
            logger.error("[usajobs] '%s' 수집 실패: %s", func, exc, exc_info=True)

        if i < len(job_functions):
            wait = random.uniform(2.0, 4.0)
            logger.debug("[usajobs] 다음 직무까지 %.1fs 대기", wait)
            time.sleep(wait)

    logger.info(
        "[usajobs] 배치 완료 — 성공: %d건, 실패: %d건",
        success_count, fail_count,
    )


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _resolve_keywords(query: str) -> list[str]:
    """taxonomy 직무명 → keyword 목록. 매핑 없으면 query 자체."""
    query = (query or "").strip()
    if not query:
        return []
    keywords = get_keywords_for_function(query)
    if keywords:
        return keywords
    logger.debug("[usajobs] '%s' — taxonomy 매핑 없음, query를 keyword로 사용", query)
    return [query]


def _has_next_page(pager: dict[str, Any], current_page: int) -> bool:
    if not isinstance(pager, dict):
        return False
    if pager.get("HasNextPage") is True:
        return True
    try:
        num_pages = int(pager.get("NumberOfPages") or 0)
    except (TypeError, ValueError):
        return False
    return current_page < num_pages


def _is_blocked(text: str) -> bool:
    lower = (text or "").lower()
    return any(signal in lower for signal in _BLOCK_SIGNALS)
