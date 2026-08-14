"""
Adzuna HTML 크롤러.

공식 Jobs API(app_id/app_key) 는 사용하지 않는다.
국가별 공개 검색·상세 HTML 을 curl_cffi(Chrome TLS 지문)로 수집한다.

수집 방식 (2026-08-03)
----------------------
1. SERP: GET /search?q={what}&p={page}[&w={where}]
   → article[data-aid] 에서 공고 ID 목록
2. 상세: GET /jobs/details/{aid}
   → 제목·회사·지역·급여·본문 HTML 파싱 후 raw_text(JSON) + raw_html 저장

비고
----
- www.adzuna.com (US) 는 Human Verification(405) 으로 차단 — COUNTRY_DOMAINS 미포함
- www.adzuna.co.uk / .com.au 는 실측 통과
- 과도한 요청 시 429 — 페이지·상세 사이 딜레이 필수
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from src.crawlers.adzuna.search_queries import (
    DEFAULT_BATCH_FUNCTIONS,
    DEFAULT_COUNTRIES,
    get_queries_for_function,
)
from src.crawlers.common.curl_cffi_client import (
    DEFAULT_IMPERSONATE,
    DEFAULT_TIMEOUT,
    CurlCffiClient,
    default_browser_headers,
    random_delay as _random_delay,
)
from src.models.schemas import RawJobPosting
from src.storage.json_writer import get_saved_ids, save_documents

logger = logging.getLogger(__name__)

_SOURCE_NAME = "adzuna"
_COLLECTION = "raw_job_postings"
_IMPERSONATE = DEFAULT_IMPERSONATE
_TIMEOUT = DEFAULT_TIMEOUT
_MAX_PAGES = 20
_RESULTS_HINT = 10  # SERP 페이지당 카드 수(실측)

# country code → 공개 웹 호스트 (공식 API country path 와 별개)
COUNTRY_DOMAINS: dict[str, str] = {
    "gb": "www.adzuna.co.uk",
    "uk": "www.adzuna.co.uk",
    "au": "www.adzuna.com.au",
}

# Adzuna 전용 차단 시그널
_BLOCK_SIGNALS = (
    "human verification",
    "complete the security check",
    "just a moment",
    "cf-browser-verification",
    "attention required",
    "enable javascript and cookies",
)

_BLOCKED_SENTINEL = object()
_SALARY_RANGE_RE = re.compile(
    r"[£$€]?\s*([\d,]+(?:\.\d+)?)\s*[-–—to]+\s*[£$€]?\s*([\d,]+(?:\.\d+)?)",
    re.I,
)
_SALARY_SINGLE_RE = re.compile(r"[£$€]\s*([\d,]+(?:\.\d+)?)", re.I)


class AdzunaBlockedError(RuntimeError):
    """봇 차단(CAPTCHA/405/429)으로 배치를 중단해야 할 때."""


def crawl_adzuna(
    what: str,
    country: str = "gb",
    where: str | None = None,
    crawl_date: str | None = None,
    save_path: str | None = None,
    max_pages: int = 3,
    max_jobs: int | None = None,
) -> str:
    """검색어·국가 조건으로 Adzuna HTML 을 수집해 raw_job_postings JSON 저장."""
    if not what or not what.strip():
        raise ValueError("what(검색어)는 필수입니다.")

    country = country.lower().strip()
    domain = COUNTRY_DOMAINS.get(country)
    if not domain:
        raise ValueError(
            f"지원하지 않는 country={country!r}. "
            f"사용 가능: {sorted(set(COUNTRY_DOMAINS) - {'uk'})}"
        )

    _crawl_date = crawl_date or date.today().isoformat()
    filename = _build_filename(country, what, where)
    saved_ids = get_saved_ids(_COLLECTION, base_dir=save_path)
    new_docs: list[dict[str, Any]] = []

    with _AdzunaHttpCrawler(domain) as crawler:
        try:
            collected = crawler.collect(
                what=what.strip(),
                where=(where or "").strip() or None,
                saved_ids=saved_ids,
                max_pages=min(max_pages, _MAX_PAGES),
                max_jobs=max_jobs,
            )
        except AdzunaBlockedError:
            logger.error("[adzuna] 차단으로 수집 중단 — country=%s what=%r", country, what)
            collected = []

        for raw in collected:
            new_docs.append(raw.to_dict())

    logger.info(
        "[adzuna] 수집 완료 — country=%s what=%r 신규=%d",
        country, what, len(new_docs),
    )
    if not new_docs:
        return ""

    saved = save_documents(
        documents=new_docs,
        collection_name=_COLLECTION,
        filename=filename,
        crawl_date=_crawl_date,
        base_dir=save_path,
        job_function_name=what,
    )
    return str(saved)


# 하위 호환 별칭 (구 client.fetch_adzuna)
fetch_adzuna = crawl_adzuna


def run_adzuna_batch(
    job_functions: list[str] | None = None,
    countries: list[str] | None = None,
    crawl_date: str | None = None,
    save_dir: str | None = None,
    max_pages: int = 2,
    max_jobs: int | None = None,
) -> None:
    """직무 × 국가 조합을 순회하며 crawl_adzuna 를 호출한다."""
    functions = job_functions or DEFAULT_BATCH_FUNCTIONS
    countries = countries or DEFAULT_COUNTRIES
    _crawl_date = crawl_date or date.today().isoformat()

    queries: list[tuple[str, str]] = []
    for func in functions:
        for q in get_queries_for_function(func)[:1]:
            for country in countries:
                queries.append((country, q))

    failed = 0
    for idx, (country, what) in enumerate(queries, start=1):
        label = f"[{idx}/{len(queries)}] {country}/{what!r}"
        try:
            logger.info("[adzuna] %s 시작", label)
            crawl_adzuna(
                what=what,
                country=country,
                crawl_date=_crawl_date,
                save_path=save_dir,
                max_pages=max_pages,
                max_jobs=max_jobs,
            )
        except Exception as exc:
            failed += 1
            logger.error("[adzuna] %s 실패: %s", label, exc, exc_info=True)
        _random_delay(2.0, 3.5)

    logger.info("[adzuna] 배치 종료 — 조합 %d, 실패 %d", len(queries), failed)


class _AdzunaHttpCrawler:
    def __init__(self, domain: str) -> None:
        self._domain = domain
        self._base_url = f"https://{domain}"
        self._client = CurlCffiClient(
            impersonate=_IMPERSONATE,
            timeout=_TIMEOUT,
            headers=default_browser_headers(
                accept_language="en-GB,en;q=0.9",
                accept=(
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,*/*;q=0.8"
                ),
            ),
            block_signals=_BLOCK_SIGNALS,
        )
        # 하위 호환·테스트용 — 실제 HTTP 는 _client 경유
        self._session = self._client.session

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "_AdzunaHttpCrawler":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def collect(
        self,
        what: str,
        where: str | None,
        saved_ids: set,
        max_pages: int,
        max_jobs: int | None,
    ) -> list[RawJobPosting]:
        results: list[RawJobPosting] = []
        seen: set[str] = set()

        for page in range(1, max_pages + 1):
            if max_jobs is not None and len(results) >= max_jobs:
                break

            aids = self._fetch_serp_aids(what, where, page)
            if aids is _BLOCKED_SENTINEL:
                raise AdzunaBlockedError("SERP blocked")
            if not aids:
                logger.info("[adzuna] page=%d 결과 없음 — 종료", page)
                break

            for aid in aids:
                if max_jobs is not None and len(results) >= max_jobs:
                    break
                if aid in seen:
                    continue
                seen.add(aid)
                if (_SOURCE_NAME, aid) in saved_ids:
                    continue

                raw = self._fetch_detail(aid)
                if raw is _BLOCKED_SENTINEL:
                    raise AdzunaBlockedError(f"detail blocked aid={aid}")
                if raw is None:
                    continue
                results.append(raw)
                saved_ids.add((_SOURCE_NAME, aid))

        return results

    def _fetch_serp_aids(
        self, what: str, where: str | None, page: int,
    ) -> list[str] | object:
        params: dict[str, Any] = {"q": what, "p": page}
        if where:
            params["w"] = where
        url = f"{self._base_url}/search?{urlencode(params)}"
        _random_delay(1.2, 2.5)

        try:
            resp = self._client.get(url)
        except Exception as exc:
            logger.error("[adzuna] SERP 요청 실패: %s", exc)
            return []

        if resp.status_code in (401, 403, 405, 429):
            logger.warning("[adzuna] SERP status=%s — 차단으로 간주", resp.status_code)
            return _BLOCKED_SENTINEL

        text = resp.text or ""
        if self._client.is_blocked(text):
            logger.warning("[adzuna] SERP CAPTCHA/차단 감지")
            return _BLOCKED_SENTINEL

        soup = BeautifulSoup(text, "lxml")
        aids = [
            (el.get("data-aid") or "").strip()
            for el in soup.select("article[data-aid]")
        ]
        aids = [a for a in aids if a]
        logger.info("[adzuna] SERP page=%d aids=%d", page, len(aids))
        return aids

    def _fetch_detail(self, aid: str) -> RawJobPosting | None | object:
        url = f"{self._base_url}/jobs/details/{aid}"
        _random_delay(0.8, 1.8)

        try:
            resp = self._client.get(url)
        except Exception as exc:
            logger.error("[adzuna] 상세 요청 실패 (%s): %s", aid, exc)
            return None

        if resp.status_code == 404:
            logger.debug("[adzuna] 상세 404 건너뜀 aid=%s", aid)
            return None
        if resp.status_code in (401, 403, 405, 429):
            logger.warning("[adzuna] 상세 status=%s aid=%s", resp.status_code, aid)
            return _BLOCKED_SENTINEL

        html = resp.text or ""
        if self._client.is_blocked(html):
            logger.warning("[adzuna] 상세 CAPTCHA/차단 aid=%s", aid)
            return _BLOCKED_SENTINEL

        job = _parse_detail_to_job(html, aid, url)
        if not job or not job.get("title"):
            logger.warning("[adzuna] 상세 파싱 실패 aid=%s", aid)
            return None

        return RawJobPosting(
            source_name=_SOURCE_NAME,
            source_job_id=aid,
            original_url=url,
            raw_html=html,
            raw_text=json.dumps(job, ensure_ascii=False),
        )


def _parse_detail_to_job(html: str, aid: str, url: str) -> dict[str, Any] | None:
    """상세 HTML → 파서 호환 JSON (구 API 응답 필드와 유사한 형태)."""
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1")
    title = title_el.get_text(" ", strip=True) if title_el else ""

    company_el = soup.select_one(".ui-company")
    company = company_el.get_text(" ", strip=True) if company_el else ""

    location_el = soup.select_one(".ui-location")
    location = location_el.get_text(" ", strip=True) if location_el else ""

    salary_el = soup.select_one(".ui-salary")
    salary_text = salary_el.get_text(" ", strip=True) if salary_el else ""
    salary_min, salary_max = _parse_salary(salary_text)

    body_el = soup.select_one(".adp-body")
    description = body_el.get_text("\n", strip=True) if body_el else ""

    category = _extract_category_from_ldjson(soup)
    created = _extract_date_posted(soup)
    posting = _extract_job_posting_ldjson(soup)

    contract_type = ""
    contract_time = ""
    employment_types: list[str] = []
    salary_currency = None
    salary_period = None

    # 카드 메타: "N Consulting Ltd London, London 300 - 350 GBP Per day Contract"
    card_info = soup.select_one(".ui-job-card-info")
    card_text = card_info.get_text(" ", strip=True) if card_info else ""
    if re.search(r"\bcontract\b", card_text, re.I):
        contract_type = "contract"
    if re.search(r"\bpermanent\b", card_text, re.I):
        contract_type = "permanent"
    if re.search(r"\bfull[\s_-]?time\b", card_text, re.I):
        contract_time = "full_time"
    if re.search(r"\bpart[\s_-]?time\b", card_text, re.I):
        contract_time = "part_time"

    if isinstance(posting, dict):
        emp = posting.get("employmentType")
        if isinstance(emp, list):
            employment_types = [str(x) for x in emp if x]
        elif isinstance(emp, str) and emp.strip():
            employment_types = [emp.strip()]
        if not contract_type and any("CONTRACT" in e.upper() for e in employment_types):
            contract_type = "contract"
        if not contract_time and any("FULL_TIME" in e.upper() or e.upper() == "FULL-TIME" for e in employment_types):
            contract_time = "full_time"

        base = posting.get("baseSalary") or {}
        if isinstance(base, dict):
            currency = (base.get("currency") or "").strip() or None
            value = base.get("value") or {}
            if isinstance(value, dict):
                unit = (value.get("unitText") or "").strip().upper() or None
                vmin = value.get("minValue")
                vmax = value.get("maxValue")
                if salary_min is None and vmin is not None:
                    try:
                        salary_min = float(str(vmin).replace(",", ""))
                    except ValueError:
                        pass
                if salary_max is None and vmax is not None:
                    try:
                        salary_max = float(str(vmax).replace(",", ""))
                    except ValueError:
                        pass
                salary_currency = currency
                if unit in {"DAY", "HOUR", "WEEK", "MONTH", "YEAR"}:
                    salary_period = {
                        "DAY": "DAILY",
                        "HOUR": "HOURLY",
                        "WEEK": "WEEKLY",
                        "MONTH": "MONTHLY",
                        "YEAR": "ANNUAL",
                    }.get(unit)
            if not salary_text and (salary_min is not None or salary_max is not None):
                cur = currency or ""
                lo = f"{salary_min:g}" if salary_min is not None else ""
                hi = f"{salary_max:g}" if salary_max is not None else ""
                unit_l = (value.get("unitText") or "").lower() if isinstance(value, dict) else ""
                salary_text = f"{lo} - {hi} {cur} per {unit_l}".strip()

        if not category:
            ind = posting.get("industry")
            if isinstance(ind, str) and ind.strip():
                category = ind.strip()
            elif isinstance(ind, list) and ind:
                category = str(ind[0])

        # JobPosting description 이 더 풍부하면 보조
        if not description and isinstance(posting.get("description"), str):
            description = BeautifulSoup(posting["description"], "lxml").get_text("\n", strip=True)

    if not title:
        return None

    # salary_raw 에서 통화/기간 보강
    if salary_currency is None and salary_text:
        if "GBP" in salary_text.upper() or "£" in salary_text:
            salary_currency = "GBP"
        elif "USD" in salary_text.upper() or "$" in salary_text:
            salary_currency = "USD"
        elif "EUR" in salary_text.upper() or "€" in salary_text:
            salary_currency = "EUR"
    if salary_period is None and salary_text:
        low = salary_text.lower()
        if "day" in low:
            salary_period = "DAILY"
        elif "hour" in low:
            salary_period = "HOURLY"
        elif "month" in low:
            salary_period = "MONTHLY"
        elif "year" in low or "annum" in low:
            salary_period = "ANNUAL"

    job: dict[str, Any] = {
        "id": aid,
        "title": title,
        "description": description,
        "redirect_url": url,
        "created": created,
        "company": {"display_name": company},
        "location": {
            "display_name": location,
            "area": _location_area(location),
        },
        "category": {"label": category, "tag": ""},
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_raw": salary_text or None,
        "salary_currency": salary_currency,
        "salary_period": salary_period,
        "contract_type": contract_type,
        "contract_time": contract_time,
        "employment_types": employment_types,
        "_source": "html_crawl",
    }
    return job


def _extract_job_posting_ldjson(soup: BeautifulSoup) -> dict[str, Any] | None:
    for sc in soup.find_all("script", type="application/ld+json"):
        raw = (sc.string or sc.get_text() or "").strip()
        if not raw or "JobPosting" not in raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def _extract_category_from_ldjson(soup: BeautifulSoup) -> str:
    for sc in soup.find_all("script", type="application/ld+json"):
        raw = (sc.string or sc.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            # BreadcrumbList
            for el in item.get("itemListElement") or []:
                if not isinstance(el, dict):
                    continue
                name = (el.get("name") or "").strip()
                if name and name.lower() not in {"jobs", "home"} and "job" in name.lower():
                    return name
            if item.get("@type") == "JobPosting":
                ind = item.get("industry")
                if isinstance(ind, str) and ind.strip():
                    return ind.strip()
    return ""


def _extract_date_posted(soup: BeautifulSoup) -> str | None:
    for sc in soup.find_all("script", type="application/ld+json"):
        raw = (sc.string or sc.get_text() or "").strip()
        if not raw or "datePosted" not in raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("datePosted"):
                return str(item["datePosted"])
    return None


def _location_area(location: str) -> list[str]:
    if not location:
        return []
    parts = [p.strip() for p in location.split(",") if p.strip()]
    return parts


def _parse_salary(text: str) -> tuple[float | None, float | None]:
    if not text:
        return None, None
    cleaned = text.replace(",", "")
    m = _SALARY_RANGE_RE.search(cleaned)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _SALARY_SINGLE_RE.search(cleaned)
    if m:
        val = float(m.group(1))
        return val, val
    return None, None


def _is_blocked(text: str) -> bool:
    """Adzuna 전용 시그널 — 테스트·하위 호환."""
    from src.crawlers.common.http_utils import is_blocked

    return is_blocked(text, signals=_BLOCK_SIGNALS)


def _build_filename(country: str, what: str, where: str | None) -> str:
    parts = ["adzuna", country, what.strip().replace("/", "_").replace(" ", "_")]
    if where:
        parts.append(where.strip().replace(" ", "_"))
    return "_".join(parts)
