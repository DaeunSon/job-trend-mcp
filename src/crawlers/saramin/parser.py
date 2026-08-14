"""
사람인 raw_job_postings (parse_status: PENDING) → job_postings 파싱.

주요 함수:
  parse_raw_posting()     — 단일 RawJobPosting dict → JobPosting dict 변환
  run_saramin_parse()     — 저장된 raw 파일을 일괄 파싱하는 오케스트레이터

파싱 전략:
  - 사람인 상세 페이지 HTML에서 구조화된 필드 추출
  - JSON-LD(application/ld+json) 구조화 데이터가 있으면 우선 파싱
  - alias_resolver로 회사명·지역명 표준화
  - 파싱 성공 → parse_status: PARSED, parsed_job_posting_id 연결
  - 파싱 실패 → parse_status: FAILED (부분 실패 허용)

사람인 HTML 셀렉터 특성 (2026년 기준):
  - 공고 제목: .job-tit h1, h1.tit, .jv-tit h1
  - 회사명:    .jv-summary .corp-name a, .coName a
  - 지역:      .jv-summary .job-condition (근무지역 항목)
  - 급여:      .jv-summary .job-condition (급여 항목) 또는 .salary
  - 고용형태:  .jv-summary .job-condition (고용형태 항목)
  - 경력:      .jv-summary .job-condition (경력 항목)
  - 학력:      .jv-summary .job-condition (학력 항목)
  - 마감:      .jv-summary .job-condition (마감일 항목)
  - 공고내용:  .jv-cont .cont, .job-description, #jobDescriptionWrap
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from src.models.schemas import (
    CareerLevel,
    SalaryInfo,
)
from src.crawlers.parse_batch import process_raw_file
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.normalization.job_taxonomy import extract_saramin_function_raw
from src.normalization.work_arrangement import detect_work_arrangement, scoped_text_from_selectors
from src.storage.json_writer import (
    _BASE_DATA_DIR,
    iter_collection_json_files,
)

logger = logging.getLogger(__name__)

_RAW_COLLECTION = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME = "saramin"


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def parse_raw_posting(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    단일 raw_job_postings 문서를 job_postings 구조로 파싱한다.

    Returns
    -------
    job_postings 문서 dict, 또는 파싱 실패 시 None
    """
    source_job_id = raw.get("source_job_id", "")
    source_name = raw.get("source_name", "")
    original_url = raw.get("original_url", "")
    raw_html = raw.get("raw_html", "")

    if not raw_html:
        logger.warning("[saramin] raw_html 없음: %s/%s", source_name, source_job_id)
        return None

    soup = BeautifulSoup(raw_html, "lxml")

    try:
        ld_data = _extract_json_ld(soup)
        # JS 변수(jobCategoryNm 등)는 relay/view 양쪽 모두 항상 추출
        fb = _extract_meta_fallback(soup)

        title = _extract_title(soup, ld_data)
        company_raw = _extract_company(soup, ld_data)
        location_raw = _extract_location(soup, ld_data)
        description = _extract_description(soup, ld_data)
        salary_info = _extract_salary(soup, ld_data)
        employment_type_raw, employment_reliable = _extract_employment_type(soup, ld_data)
        career_raw_text, career_min, career_max = _extract_career_raw(soup)
        education_level = _extract_education_level(soup)
        posted_at = _extract_posted_at(soup, ld_data)
        expires_at = _extract_expires_at(soup, ld_data)
        skills = _extract_skills(description)
        work_arrangement_text = _work_arrangement_scope_text(soup, description)

        # relay/view 페이지처럼 wrap_jview가 비어 있는 경우 fallback 적용
        if not title or not company_raw:

            if not title:
                title = fb.get("title", "")
            if not company_raw:
                company_raw = fb.get("company", "")
            if not description:
                description = fb.get("meta_description", "")
            if not expires_at:
                expires_at = fb.get("deadline")

            # 경력/학력 재추출 (조건 테이블이 없는 경우)
            if not career_raw_text and fb.get("career"):
                career_raw_text, career_min, career_max = _parse_career_raw(fb["career"])
            if not education_level and fb.get("education"):
                education_level = _clean_education_level(fb["education"])

            # 급여 재추출
            if salary_info.raw_text is None and fb.get("salary_raw"):
                raw_sal = fb["salary_raw"]
                min_amt, max_amt, currency, period = _parse_salary_text(raw_sal)
                salary_info = SalaryInfo(
                    raw_text=raw_sal,
                    min_amount=min_amt,
                    max_amount=max_amt,
                    currency_code=currency,
                    pay_period=period,
                )

            # relay 페이지에서는 employment_type을 조건 테이블로 정확히 추출 불가
            if not employment_reliable:
                employment_type_raw = ""

            if not work_arrangement_text and description:
                work_arrangement_text = description

            # 스킬: jobCategoryNm에서 추가 추출 + job_category/function 매핑
            if fb.get("job_categories"):
                extra_text = fb["job_categories"].replace(",", " ").replace("/", " ")
                extra_skills = _extract_skills(extra_text)
                for s in extra_skills:
                    if s not in skills:
                        skills.append(s)

        job_categories_str = fb.get("job_categories", "")
        job_function_raw = extract_saramin_function_raw(job_categories_str)

        extracted = RawExtractedFields(
            title=title,
            company_raw=company_raw,
            description=description,
            location_raw=location_raw,
            employment_type_raw=employment_type_raw,
            career_raw_text=career_raw_text,
            career_min_years=career_min,
            career_max_years=career_max,
            work_arrangement_text=work_arrangement_text,
            education_level=education_level,
            job_function_raw=job_function_raw,
            skills=skills,
            salary=salary_info,
            posted_at=posted_at,
            expires_at=expires_at,
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[saramin] 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_saramin_parse(
    crawl_date: str | None = None,
    base_dir: str | None = None,
    reparse: bool = False,
) -> None:
    """
    저장된 raw_job_postings 문서를 일괄 파싱한다.

    reparse=False (기본): parse_status='PENDING'이고 source_name='saramin'인 것만 파싱
    reparse=True       : source_name='saramin'인 모든 문서를 다시 파싱 (PARSED 포함)

    - 파싱 성공: job_postings 컬렉션에 저장 + 원본 parse_status → PARSED
    - 파싱 실패: 원본 parse_status → FAILED (배치 중단 없음)
    """
    _data_root = Path(base_dir) if base_dir else _BASE_DATA_DIR
    raw_root = _data_root / _RAW_COLLECTION

    if not raw_root.exists():
        logger.warning("[saramin] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="saramin",
    ):
        n_ok, n_fail = _process_raw_file(
            json_file=json_file,
            date_label=date_label,
            base_dir=base_dir,
            reparse=reparse,
        )
        total_parsed += n_ok
        total_failed += n_fail

    logger.info(
        "[saramin] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
        total_parsed, total_failed,
        " (재파싱)" if reparse else "",
    )


# ---------------------------------------------------------------------------
# 내부: 파일 단위 처리
# ---------------------------------------------------------------------------

def _process_raw_file(
    json_file: Path,
    date_label: str,
    base_dir: str | None,
    reparse: bool = False,
) -> tuple[int, int]:
    """raw JSON 파일 하나를 파싱하고 결과를 저장한다. (성공 수, 실패 수) 반환."""
    return process_raw_file(
        json_file=json_file,
        date_label=date_label,
        base_dir=base_dir,
        parse_fn=parse_raw_posting,
        source_name=_SOURCE_NAME,
        reparse=reparse,
        log_prefix="[saramin]",
    )


# ---------------------------------------------------------------------------
# HTML / JSON-LD 파싱 헬퍼
# ---------------------------------------------------------------------------

def _extract_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    """application/ld+json 스크립트에서 JobPosting 타입을 우선 반환한다."""
    candidates: list[dict[str, Any]] = []
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                candidates.append(data)
            elif isinstance(data, list):
                candidates.extend(d for d in data if isinstance(d, dict))
        except Exception:
            continue

    for d in candidates:
        if d.get("@type") == "JobPosting":
            return d
    return candidates[0] if candidates else {}


def _extract_meta_fallback(soup: BeautifulSoup) -> dict[str, Any]:
    """
    사람인 relay/view 페이지용 fallback 추출.

    relay 페이지는 공고 본문이 JS로 동적 로드되어 wrap_jview div가 비어 있으므로,
    <title>, <meta name="description">, JS 변수(companyNm, jobCategoryNm)에서
    가능한 모든 정보를 추출한다.

    Returns
    -------
    dict with keys: title, company, career, education, deadline, job_categories,
                    meta_description (모두 없으면 빈 문자열)
    """
    result: dict[str, Any] = {}
    html_text = str(soup)

    # 1. JS 변수 companyNm, jobCategoryNm 추출
    m = re.search(r"companyNm\s*=\s*'([^']+)'", html_text)
    if m:
        result["company"] = m.group(1).strip()

    m = re.search(r"jobCategoryNm\s*=\s*'([^']+)'", html_text)
    if m:
        result["job_categories"] = m.group(1).strip()

    # 2. meta description에서 구조화 필드 추출
    #    형식: "{company}, {title}, 경력:{...}, 학력:{...}, {salary}, 마감일:{date}, 홈페이지:{url}"
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        content = meta.get("content", "").strip()
        if content:
            result["meta_description"] = content
            # 키:값 패턴으로 개별 필드 추출
            m = re.search(r"경력:(.+?)(?=,\s*(?:마감일:|홈페이지:|경력:|학력:)|$)", content)
            if m:
                result["career"] = m.group(1).strip()

            # 학력·급여 구간: "학력:..." ~ "마감일:" 사이를 분리
            # 급여는 키 있는 형태(연봉:N만원)와 키 없는 형태(면접 후 결정, 협의 등) 모두 처리
            edu_block = re.search(r"학력:(.+?),\s*마감일:", content)
            if edu_block:
                raw_block = edu_block.group(1)
                # 1) 키 있는 급여 패턴: ", 연봉:|월급:|시급:" 에서 분리
                key_sal = re.search(r",\s*((?:연봉|월급|시급|급여)(?:\s*협의)?:.+)$", raw_block)
                if key_sal:
                    result["education"] = raw_block[:key_sal.start()].strip()
                    result["salary_raw"] = key_sal.group(1).strip()
                else:
                    # 2) 키 없는 급여 패턴: 마지막 콤마 기준 분리
                    #    ex) "대학졸업(2,3년)이상, 면접 후 결정"
                    #        → rfind(",") → education="대학졸업(2,3년)이상", salary="면접 후 결정"
                    last_comma = raw_block.rfind(",")
                    if last_comma != -1:
                        result["education"] = raw_block[:last_comma].strip()
                        result["salary_raw"] = raw_block[last_comma + 1:].strip()
                    else:
                        result["education"] = raw_block.strip()
            else:
                # 마감일 없는 경우 fallback
                m = re.search(r"학력:(.+?)(?=,\s*(?:홈페이지:|경력:)|$)", content)
                if m:
                    result["education"] = m.group(1).strip()

            m = re.search(r"마감일:(\d{4}-\d{2}-\d{2}|\d{4}\.\d{2}\.\d{2})", content)
            if m:
                result["deadline"] = m.group(1).replace(".", "-")

    # 3. <title> 태그에서 공고 제목 추출
    #    형식: "[{company}] {title}(D-N) - 사람인"
    title_tag = soup.find("title")
    if title_tag:
        raw_title = title_tag.get_text(strip=True)
        clean = raw_title
        # "[회사명] " 접두사 제거
        company = result.get("company", "")
        if company:
            clean = re.sub(r"^\[" + re.escape(company) + r"\]\s*", "", clean)
        # " - 사람인" 접미사 제거 (D-N 제거보다 먼저 실행)
        clean = re.sub(r"\s*-\s*사람인\s*$", "", clean)
        # "(D-숫자)" 또는 "(D+숫자)" 접미사 제거
        clean = re.sub(r"\s*\(D[-+]?\d+\)\s*$", "", clean)
        result["title"] = clean.strip()

    return result


def _extract_title(soup: BeautifulSoup, ld: dict[str, Any]) -> str:
    """공고 제목 추출."""
    if ld.get("title"):
        return str(ld["title"]).strip()

    for sel in [
        ".job-tit h1",
        "h1.tit",
        ".jv-tit h1",
        ".recruit-title h1",
        "h1.recruit-title",
        ".box-jv-cont h1",
        "h2.tit",
        "h1",
    ]:
        tag = soup.select_one(sel)
        if tag:
            return tag.get_text(strip=True)
    return ""


def _extract_company(soup: BeautifulSoup, ld: dict[str, Any]) -> str:
    """회사명 추출."""
    org = ld.get("hiringOrganization", {})
    if isinstance(org, dict) and org.get("name"):
        return str(org["name"]).strip()

    for sel in [
        ".jv-summary .corp-name a",
        ".wrap-jv-cont .coName a",
        ".company-name a",
        "a.coComp",
        ".corp-name a",
        ".coName",
        "[class*='corpName'] a",
    ]:
        tag = soup.select_one(sel)
        if tag:
            return tag.get_text(strip=True)
    return ""


def _extract_location(soup: BeautifulSoup, ld: dict[str, Any]) -> str:
    """근무 위치 추출 — raw_text용 전체 주소."""

    def _clean_loc(text: str) -> str:
        """'지도보기' 링크 텍스트 및 이후 내용 제거."""
        text = re.sub(r"\s*지도\s*보기.*$", "", text, flags=re.IGNORECASE)
        return re.sub(r"\s{2,}", " ", text).strip()

    # 1. 근무지위치 섹션 data-address (전체 주소 — relay/view 페이지)
    for sel in [".jv_location[data-address]", ".jv_cont.jv_location[data-address]"]:
        tag = soup.select_one(sel)
        if tag:
            addr = tag.get("data-address", "").strip()
            if addr:
                return _clean_loc(addr)

    # 2. JSON-LD streetAddress (상세 주소)
    job_loc = ld.get("jobLocation", {})
    if isinstance(job_loc, dict):
        addr = job_loc.get("address", {})
        if isinstance(addr, dict):
            street = addr.get("streetAddress", "").strip()
            if street:
                return _clean_loc(street)
            parts = [
                addr.get("addressLocality", ""),
                addr.get("addressRegion", ""),
            ]
            text = " ".join(p for p in parts if p)
            if text:
                return _clean_loc(text)

    # 3. 근무지위치 address 태그 (첫 번째 지역 주소 span)
    addr_tag = soup.select_one(".jv_location address.address")
    if addr_tag:
        for span in addr_tag.select("span"):
            text = span.get_text(strip=True)
            if text and _looks_like_ko_address(text):
                return _clean_loc(text)

    # 4. 조건 테이블 근무지역 (짧은 주소 fallback)
    location = _extract_from_condition_table(
        soup, ["근무지역", "근무지 위치", "근무지", "지역"]
    )
    if location:
        return _clean_loc(location)

    for sel in [
        ".jv-summary .loc",
        ".work-place",
        ".location",
        "[class*='workPlace']",
        ".tplPlace",
    ]:
        tag = soup.select_one(sel)
        if tag:
            return _clean_loc(tag.get_text(strip=True))
    return ""


def _looks_like_ko_address(text: str) -> bool:
    """한국 행정구역으로 시작하는 주소 텍스트인지 확인."""
    ko_regions = (
        "서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종",
        "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주", "전국",
    )
    cleaned = re.sub(r"^\(\d{5}\)\s*", "", text.strip())
    return any(cleaned.startswith(r) for r in ko_regions)


def _extract_description(soup: BeautifulSoup, ld: dict[str, Any]) -> str:
    """공고 설명 전문 추출."""
    if ld.get("description"):
        desc_soup = BeautifulSoup(str(ld["description"]), "lxml")
        return desc_soup.get_text(separator="\n", strip=True)

    for sel in [
        ".jv-cont .cont",
        ".job-description",
        "#jobDescriptionWrap",
        ".view-detail",
        ".jd-contents",
        "[class*='jobDescription']",
        "[id*='description']",
        ".tplJobDetail",
    ]:
        tag = soup.select_one(sel)
        if tag:
            return tag.get_text(separator="\n", strip=True)
    return ""


def _extract_salary(soup: BeautifulSoup, ld: dict[str, Any]) -> SalaryInfo:
    """급여 정보 추출."""
    base_sal = ld.get("baseSalary", {})
    if isinstance(base_sal, dict):
        value = base_sal.get("value", {})
        if isinstance(value, dict):
            min_v = value.get("minValue")
            max_v = value.get("maxValue")
            unit = value.get("unitText", "YEAR")
            currency = base_sal.get("currency", "KRW")
            period_map = {"YEAR": "ANNUAL", "MONTH": "MONTHLY", "HOUR": "HOURLY"}
            period = period_map.get(unit.upper(), "ANNUAL")
            if min_v is not None or max_v is not None:
                raw_text = f"{currency} {min_v or ''} ~ {max_v or ''} / {unit}"
                return SalaryInfo(
                    raw_text=raw_text.strip(),
                    min_amount=str(min_v) if min_v is not None else None,
                    max_amount=str(max_v) if max_v is not None else None,
                    currency_code=currency,
                    pay_period=period,
                )

    # 사람인 조건 테이블에서 급여 추출
    raw_text = _extract_from_condition_table(soup, ["급여", "연봉", "임금"])

    if not raw_text:
        salary_keywords = ["만원", "원", "연봉", "월급", "시급", "면접 후 결정", "회사 내규", "협의"]
        for sel in [".salary", "[class*='salary']", "[class*='Salary']"]:
            for tag in soup.select(sel):
                text = tag.get_text(strip=True)
                if any(kw in text for kw in salary_keywords):
                    raw_text = text
                    break
            if raw_text:
                break

    if not raw_text:
        return SalaryInfo()

    min_amt, max_amt, currency, period = _parse_salary_text(raw_text)
    return SalaryInfo(
        raw_text=raw_text,
        min_amount=min_amt,
        max_amount=max_amt,
        currency_code=currency,
        pay_period=period,
    )


def _parse_salary_text(
    text: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """급여 텍스트에서 (min, max, currency, period) 추출."""
    currency: str | None = None
    period: str | None = None
    amounts_int: list[int] = []

    if "만원" in text:
        currency = "KRW"
        # "N~M만원" 또는 "N-M만원" 범위 패턴을 우선 처리 (단위가 맨 끝에만 붙는 형태)
        range_m = re.search(r"([\d,]+)\s*[~\-]\s*([\d,]+)\s*만원", text)
        if range_m:
            amounts_int = [
                int(range_m.group(1).replace(",", "")) * 10_000,
                int(range_m.group(2).replace(",", "")) * 10_000,
            ]
        else:
            amounts_raw = re.findall(r"[\d,]+(?:\.\d+)?(?=\s*만원)", text)
            amounts_int = [int(a.replace(",", "")) * 10_000 for a in amounts_raw]
    elif "원" in text:
        currency = "KRW"
        amounts_raw = re.findall(r"[\d,]+(?:\.\d+)?(?=\s*원)", text)
        amounts_int = [int(a.replace(",", "")) for a in amounts_raw]
    elif "$" in text:
        currency = "USD"
        amounts_raw = re.findall(r"[\d,]+", text.replace("$", ""))
        amounts_int = [int(a.replace(",", "")) for a in amounts_raw]

    text_lower = text.lower()
    if any(kw in text_lower for kw in ["연봉", "per year", "annual", "/년"]):
        period = "ANNUAL"
    elif any(kw in text_lower for kw in ["월급", "월", "per month", "monthly", "/월"]):
        period = "MONTHLY"
    elif any(kw in text_lower for kw in ["시급", "per hour", "hourly", "/시간"]):
        period = "HOURLY"

    min_amt = str(min(amounts_int)) if amounts_int else None
    max_amt = str(max(amounts_int)) if len(amounts_int) > 1 else None
    return min_amt, max_amt, currency, period


def _extract_employment_type(
    soup: BeautifulSoup, ld: dict[str, Any]
) -> tuple[str, bool]:
    """
    고용 형태 원문 추출.

    Returns
    -------
    (raw_text, reliable)
    reliable=False 이면 relay fallback 등에서 값을 버려야 한다.
    """
    emp_type = ld.get("employmentType", "")
    if emp_type:
        emp_str = emp_type if isinstance(emp_type, str) else " ".join(emp_type)
        return emp_str.strip(), True

    emp_text = _extract_from_condition_table(soup, ["고용형태", "고용 형태", "근무형태"])
    if emp_text:
        return emp_text.strip(), True

    for sel in [".emp-type", "[class*='empType']", ".tplEmpType"]:
        for tag in soup.select(sel):
            text = tag.get_text(strip=True)
            if text:
                return text, True

    # 전체 페이지 스캔 — 신뢰도 낮음
    kw_map = ["정규직", "계약직", "파트타임", "인턴", "프리랜서", "파견직"]
    full_text = soup.get_text(separator=" ", strip=True)
    for kw in kw_map:
        if kw == "인턴":
            if re.search(r"인턴(?:십|\s|$)", full_text):
                return kw, False
        elif kw in full_text:
            return kw, False

    return "", False


def _work_arrangement_scope_text(soup: BeautifulSoup, description: str) -> str:
    """근무 형태 탐지용 텍스트 — 공고 본문 영역으로 범위 제한."""
    parts: list[str] = []
    for sel in [".wrap_jview", ".jview", ".jv-cont .cont", ".jv-cont"]:
        tag = soup.select_one(sel)
        if tag:
            parts.append(tag.get_text(separator=" ", strip=True))
    if description:
        parts.append(description)
    return " ".join(parts) if parts else description


def _extract_work_arrangement(soup: BeautifulSoup, description: str) -> str | None:
    """근무 형태 추출 (공통 정책 위임). 테스트·하위 호환용."""
    return detect_work_arrangement(_work_arrangement_scope_text(soup, description))


def _extract_career_raw(soup: BeautifulSoup) -> tuple[str, int | None, int | None]:
    """경력 원문 및 연수 추출."""
    career_text = _extract_from_condition_table(soup, ["경력", "경력사항"])
    if career_text:
        return _parse_career_raw(career_text)

    for sel in [".career", "[class*='career']", ".tplCareer"]:
        tag = soup.select_one(sel)
        if tag:
            return _parse_career_raw(tag.get_text(strip=True))

    return "", None, None


def _extract_career_level(soup: BeautifulSoup) -> CareerLevel:
    """경력 수준 추출 (테스트·하위 호환용 — 정규화는 posting_normalizer)."""
    from src.taxonomy.career_levels import normalize_career_level

    raw_text, min_y, max_y = _extract_career_raw(soup)
    return normalize_career_level(
        raw_text=raw_text, min_years=min_y, max_years=max_y
    )


def _parse_career_raw(text: str) -> tuple[str, int | None, int | None]:
    """경력 텍스트에서 원문과 연수 범위를 추출한다."""
    min_y: int | None = None
    max_y: int | None = None

    m = re.search(r"(\d+)\s*년?\s*[~\-]\s*(\d+)\s*년", text)
    if m:
        min_y, max_y = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(\d+)\s*년\s*이상", text)
        if m:
            min_y = int(m.group(1))

    return text.strip(), min_y, max_y


def _parse_career_text(text: str) -> CareerLevel:
    """경력 텍스트 → CareerLevel (테스트·하위 호환용)."""
    from src.taxonomy.career_levels import normalize_career_level

    raw_text, min_y, max_y = _parse_career_raw(text)
    return normalize_career_level(
        raw_text=raw_text, min_years=min_y, max_years=max_y
    )


def _extract_education_level(soup: BeautifulSoup) -> str | None:
    """학력 수준 추출."""
    edu_text = _extract_from_condition_table(soup, ["학력", "최종학력"])
    if edu_text:
        return _clean_education_level(edu_text) or None

    for sel in [".education", "[class*='education']", ".edu"]:
        tag = soup.select_one(sel)
        if tag:
            return _clean_education_level(tag.get_text(strip=True)) or None
    return None


def _clean_education_level(text: str) -> str:
    """
    학력 텍스트에서 전공명 등 부가정보를 제거한다.

    사람인 HTML에서 학력 셀에 전공 선호도(물리,수학,전산,전자 등)가
    공백 없이 이어 붙는 경우를 처리한다.

    Examples
    --------
    "대졸(4년제) 이상(예정자 가능)물리,수학,전산,전자"
      → "대졸(4년제) 이상(예정자 가능)"
    "고졸 이상"
      → "고졸 이상"
    "학력무관"
      → "학력무관"
    """
    if not text:
        return text
    # "(예정자 가능)", "(졸업예정자 포함)" 등 예정자 관련 괄호 이후 텍스트 제거
    text = re.sub(r"(\([^)]*예정자[^)]*\)).*$", r"\1", text)
    # 닫는 괄호 바로 뒤 공백 없이 이어지는 한글/콤마 텍스트 제거
    # ex) "이상(예정자 가능)물리,수학" → "이상(예정자 가능)"
    text = re.sub(r"\)([가-힣,]+)$", ")", text)
    return text.strip()


def _extract_posted_at(soup: BeautifulSoup, ld: dict[str, Any]) -> str | None:
    """게시일 추출. ISO date 형식(YYYY-MM-DD) 또는 None 반환."""
    for key in ("datePosted",):
        val = ld.get(key)
        if val:
            m = re.search(r"\d{4}-\d{2}-\d{2}", str(val))
            if m:
                return m.group()

    # 사람인 조건 테이블에서 등록일 추출
    posted_text = _extract_from_condition_table(soup, ["등록일", "게시일", "공고등록일"])
    if posted_text:
        m = re.search(r"\d{4}[.\-/]\d{2}[.\-/]\d{2}", posted_text)
        if m:
            return m.group().replace(".", "-").replace("/", "-")

    for sel in ["time[datetime]", ".post-date", "[class*='postDate']", "[class*='registDt']"]:
        tag = soup.select_one(sel)
        if tag:
            dt_attr = tag.get("datetime", "")
            if dt_attr:
                m = re.search(r"\d{4}-\d{2}-\d{2}", str(dt_attr))
                if m:
                    return m.group()
            text = tag.get_text(strip=True)
            m = re.search(r"\d{4}[.\-/]\d{2}[.\-/]\d{2}", text)
            if m:
                return m.group().replace(".", "-").replace("/", "-")

    return None


def _extract_expires_at(soup: BeautifulSoup, ld: dict[str, Any]) -> str | None:
    """마감일 추출. ISO date 형식(YYYY-MM-DD) 또는 None 반환."""
    val = ld.get("validThrough")
    if val:
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(val))
        if m:
            return m.group()

    # 사람인 조건 테이블에서 마감일 추출
    deadline_text = _extract_from_condition_table(soup, ["마감일", "마감", "접수마감"])
    if deadline_text:
        if "상시" in deadline_text:
            return None
        m = re.search(r"\d{4}[.\-/]\d{2}[.\-/]\d{2}", deadline_text)
        if m:
            return m.group().replace(".", "-").replace("/", "-")

    return None


def _extract_skills(description: str) -> list[str]:
    """직무 설명에서 기술 스택 키워드를 추출한다."""
    from src.taxonomy.skills import find_skills_in_text
    return find_skills_in_text(description)


from src.normalization.location_utils import parse_korean_location, trim_to_district

# 테스트·하위 호환 alias
_parse_location_text = parse_korean_location
_trim_to_district = trim_to_district


def _extract_from_condition_table(soup: BeautifulSoup, label_candidates: list[str]) -> str:
    """
    사람인 상세 페이지의 조건 테이블/목록에서 특정 레이블의 값을 추출한다.

    사람인 상세 페이지 조건 구조 예시:
      <div class="jv-summary">
        <dl>
          <dt>근무지역</dt><dd>서울 강남구</dd>
          <dt>경력</dt><dd>경력 3~5년</dd>
          ...
        </dl>
      </div>
    또는
      <table class="jv-detail">
        <tr><th>근무지역</th><td>서울 강남구</td></tr>
        ...
      </table>
    """
    # dl/dt-dd 구조
    for dl in soup.select("dl"):
        dts = dl.select("dt")
        dds = dl.select("dd")
        for i, dt in enumerate(dts):
            dt_text = dt.get_text(strip=True)
            if any(label in dt_text for label in label_candidates):
                if i < len(dds):
                    return dds[i].get_text(strip=True)

    # table th-td 구조
    for table in soup.select("table"):
        for row in table.select("tr"):
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td:
                th_text = th.get_text(strip=True)
                if any(label in th_text for label in label_candidates):
                    return td.get_text(strip=True)

    # span.tit + span.txt 구조 (사람인 일부 페이지)
    for item in soup.select(".info-item, .jv-cont-item"):
        tit = item.select_one(".tit, .label, dt")
        val = item.select_one(".txt, .value, dd")
        if tit and val:
            tit_text = tit.get_text(strip=True)
            if any(label in tit_text for label in label_candidates):
                return val.get_text(strip=True)

    return ""

