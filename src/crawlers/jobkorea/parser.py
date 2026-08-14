"""
잡코리아 raw_job_postings (parse_status: PENDING) → job_postings 파싱.

주요 함수:
  parse_raw_posting()     — 단일 RawJobPosting dict → JobPosting dict 변환
  run_jobkorea_parse()    — 저장된 raw 파일을 일괄 파싱하는 오케스트레이터

파싱 전략:
  - 잡코리아 상세 페이지 HTML에서 구조화된 필드 추출
  - JSON-LD(application/ld+json) 구조화 데이터가 있으면 우선 파싱
  - alias_resolver로 회사명·지역명 표준화
  - 파싱 성공 → parse_status: PARSED, parsed_job_posting_id 연결
  - 파싱 실패 → parse_status: FAILED (부분 실패 허용)

잡코리아 HTML 셀렉터 특성 (2026년 기준):
  - 공고 제목: .view-header .tit, h1.title
  - 회사명:    .coName a, .corp-name
  - 지역:      .tbCol td[data-bind='workPlace'], .work-place
  - 급여:      .tbCol td[data-bind='salary'], #salaryInfo
  - 고용형태:  .tbCol td[data-bind='empType']
  - 경력:      .tbCol td[data-bind='career']
  - 마감:      .tbCol td[data-bind='deadlineDt']
  - 공고내용:  #jobDescriptionWrap, .view-detail
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from src.models.schemas import (
    CareerLevel,
    SalaryInfo,
)
from src.crawlers.parse_batch import process_raw_file
from src.normalization.location_utils import parse_korean_location, trim_to_district
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.normalization.job_taxonomy import extract_jobkorea_function_raw
from src.normalization.work_arrangement import detect_work_arrangement, scoped_text_from_selectors
from src.storage.json_writer import (
    _BASE_DATA_DIR,
    iter_collection_json_files,
)

# 테스트·하위 호환 alias
_parse_location_text = parse_korean_location
_trim_to_district = trim_to_district

logger = logging.getLogger(__name__)

_RAW_COLLECTION = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME = "jobkorea"


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
        logger.warning("[jobkorea] raw_html 없음: %s/%s", source_name, source_job_id)
        return None

    soup = BeautifulSoup(raw_html, "lxml")

    try:
        ld_data = _extract_json_ld(soup)

        title = _extract_title(soup, ld_data)
        company_raw = _extract_company(soup, ld_data)
        location_raw = _extract_location(soup, ld_data)
        description = _extract_description(soup, ld_data)
        salary_info = _extract_salary(soup, ld_data)
        employment_type_raw, _ = _extract_employment_type(soup, ld_data)
        career_raw_text, career_min, career_max = _extract_career_raw(soup, raw_html)
        education_level = _extract_education_level(ld_data)
        posted_at = _extract_posted_at(soup, ld_data)
        expires_at = _extract_expires_at(ld_data)
        flight_skills = _extract_flight_skills(raw_html)
        page_text = soup.get_text(separator=" ", strip=True)
        skills = flight_skills if flight_skills else _extract_skills(description, page_text)
        industry_name, size_category = _extract_company_extras(soup)
        job_function_raw = extract_jobkorea_function_raw(title, description)
        work_arrangement_text = _work_arrangement_scope_text(soup, description)

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
            company_industry=industry_name,
            company_size=size_category,
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[jobkorea] 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_jobkorea_parse(
    crawl_date: str | None = None,
    base_dir: str | None = None,
    reparse: bool = False,
) -> None:
    """
    저장된 raw_job_postings 문서를 일괄 파싱한다.

    reparse=False (기본): parse_status='PENDING'이고 source_name='jobkorea'인 것만 파싱
    reparse=True       : source_name='jobkorea'인 모든 문서를 다시 파싱 (PARSED 포함)

    - 파싱 성공: job_postings 컬렉션에 저장 + 원본 parse_status → PARSED
    - 파싱 실패: 원본 parse_status → FAILED (배치 중단 없음)
    """
    _data_root = Path(base_dir) if base_dir else _BASE_DATA_DIR
    raw_root = _data_root / _RAW_COLLECTION

    if not raw_root.exists():
        logger.warning("[jobkorea] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="jobkorea",
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
        "[jobkorea] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
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
        log_prefix="[jobkorea]",
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


def _extract_title(soup: BeautifulSoup, ld: dict[str, Any]) -> str:
    """공고 제목 추출."""
    if ld.get("title"):
        return str(ld["title"]).strip()

    for sel in [
        ".view-header .tit",
        "h1.title",
        ".recruit-title",
        ".jobTitle",
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
        "a.coName",
        ".coName a",
        ".corp-name",
        ".company-name",
        "[class*='corpNm']",
        ".tplCompName",
        "a.name",
    ]:
        tag = soup.select_one(sel)
        if tag:
            return tag.get_text(strip=True)
    return ""


def _extract_location(soup: BeautifulSoup, ld: dict[str, Any]) -> str:
    """근무 위치 추출.

    우선순위: JSON-LD streetAddress → addressLocality/Region → HTML 셀렉터 → 페이지 텍스트
    """
    job_loc = ld.get("jobLocation", {})
    if isinstance(job_loc, dict):
        addr = job_loc.get("address", {})
        if isinstance(addr, dict):
            # streetAddress가 가장 상세한 주소 포함 (예: "서울 영등포구 양평로 157")
            street = addr.get("streetAddress", "").strip()
            if street:
                return street
            parts = [
                addr.get("addressLocality", ""),
                addr.get("addressRegion", ""),
            ]
            text = " ".join(p for p in parts if p)
            if text:
                return text

    for sel in [
        "td[data-bind='workPlace']",
        ".work-place",
        ".location",
        "[class*='workPlace']",
        ".tplPlace",
    ]:
        tag = soup.select_one(sel)
        if tag:
            return tag.get_text(strip=True)

    # 페이지 텍스트에서 주소 패턴 탐색 (서울/경기/부산 등으로 시작하는 줄)
    _KO_REGIONS = [
        "서울", "경기", "인천", "부산", "대구", "대전",
        "광주", "울산", "세종", "강원", "충북", "충남",
        "전북", "전남", "경북", "경남", "제주",
    ]
    for line in soup.get_text(separator="\n", strip=True).split("\n"):
        line = line.strip()
        if len(line) > 5 and any(line.startswith(r) for r in _KO_REGIONS):
            return line

    return ""


def _extract_description(soup: BeautifulSoup, ld: dict[str, Any]) -> str:
    """공고 설명 전문 추출."""
    if ld.get("description"):
        desc_soup = BeautifulSoup(str(ld["description"]), "lxml")
        return desc_soup.get_text(separator="\n", strip=True)

    for sel in [
        "#jobDescriptionWrap",
        ".view-detail",
        ".job-detail-content",
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
            single_v = value.get("value")  # 단일 값 (범위 없는 경우)
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
            if single_v is not None:
                raw_text = f"{currency} {single_v} / {unit}"
                return SalaryInfo(
                    raw_text=raw_text.strip(),
                    min_amount=str(single_v),
                    max_amount=None,
                    currency_code=currency,
                    pay_period=period,
                )

    raw_text: str | None = None
    salary_keywords = ["만원", "원", "연봉", "월급", "시급", "면접 후 결정", "회사 내규"]
    for sel in [
        "td[data-bind='salary']",
        "#salaryInfo",
        ".salary",
        "[class*='salary']",
        "[class*='Salary']",
    ]:
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
    elif any(kw in text_lower for kw in ["월급", "per month", "monthly", "/월"]):
        period = "MONTHLY"
    elif any(kw in text_lower for kw in ["시급", "per hour", "hourly", "/시간"]):
        period = "HOURLY"

    min_amt = str(min(amounts_int)) if amounts_int else None
    max_amt = str(max(amounts_int)) if len(amounts_int) > 1 else None
    return min_amt, max_amt, currency, period


def _extract_employment_type(
    soup: BeautifulSoup, ld: dict[str, Any]
) -> tuple[str, bool]:
    """고용 형태 원문 추출."""
    emp_type = ld.get("employmentType", "")
    if emp_type:
        emp_str = emp_type if isinstance(emp_type, str) else " ".join(emp_type)
        return emp_str.strip(), True

    for sel in [
        "td[data-bind='empType']",
        ".emp-type",
        "[class*='empType']",
        ".tplEmpType",
    ]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            if text:
                return text, True

    kw_map = ["정규직", "계약직", "파트타임", "인턴", "프리랜서", "Full-time", "Part-time"]
    full_text = soup.get_text(separator=" ", strip=True)
    for kw in kw_map:
        if kw.lower() in full_text.lower():
            return kw, False

    return "", False


def _work_arrangement_scope_text(soup: BeautifulSoup, description: str) -> str:
    """근무 형태 탐지용 텍스트 — 공고 본문 영역으로 범위 제한."""
    return scoped_text_from_selectors(
        soup,
        ["#jobDescriptionWrap", ".view-detail", ".view-cont"],
        fallback=description,
    )


def _extract_work_arrangement(soup: BeautifulSoup, description: str) -> str | None:
    """근무 형태 추출 (공통 정책 위임)."""
    return detect_work_arrangement(_work_arrangement_scope_text(soup, description))


def _extract_flight_career_raw(
    raw_html: str,
) -> tuple[str, int | None, int | None] | None:
    """Flight data에서 경력 원문·연수 추출."""
    m = re.search(r'\\"careers\\":\s*(\[.*?\])', raw_html)
    if not m:
        return None
    try:
        careers_raw = m.group(1).replace('\\"', '"')
        careers = json.loads(careers_raw)
        if not careers:
            return None

        career = careers[0]
        career_type = career.get("type", "")
        range_data = career.get("range") or {}

        if career_type == "ANY":
            return "경력무관", None, None
        if career_type == "ENTRY":
            return "신입", 0, 0
        if career_type == "EXPERIENCED":
            min_y = range_data.get("from")
            max_y = range_data.get("to")
            if min_y is not None and max_y is not None:
                text = f"경력 {min_y}~{max_y}년"
            elif min_y is not None:
                text = f"경력 {min_y}년 이상"
            else:
                text = "경력"
            return text, min_y, max_y
        return None
    except Exception:
        return None


def _extract_flight_career(raw_html: str) -> CareerLevel | None:
    """Flight data 경력 (테스트·하위 호환)."""
    from src.taxonomy.career_levels import normalize_career_level

    raw = _extract_flight_career_raw(raw_html)
    if not raw:
        return None
    text, min_y, max_y = raw
    return normalize_career_level(raw_text=text, min_years=min_y, max_years=max_y)


def _extract_career_raw(
    soup: BeautifulSoup, raw_html: str
) -> tuple[str, int | None, int | None]:
    """경력 원문 및 연수 추출 (Flight data 우선)."""
    flight = _extract_flight_career_raw(raw_html)
    if flight:
        return flight

    for sel in [
        "td[data-bind='career']",
        ".career",
        "[class*='career']",
        ".tplCareer",
    ]:
        tag = soup.select_one(sel)
        if tag:
            return _parse_career_raw(tag.get_text(strip=True))

    return "", None, None


def _extract_career_level(soup: BeautifulSoup) -> CareerLevel:
    """경력 수준 (테스트·하위 호환)."""
    from src.taxonomy.career_levels import normalize_career_level

    raw_text, min_y, max_y = _extract_career_raw(soup, "")
    return normalize_career_level(
        raw_text=raw_text, min_years=min_y, max_years=max_y
    )


def _parse_career_raw(text: str) -> tuple[str, int | None, int | None]:
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
    """경력 텍스트 → CareerLevel (테스트·하위 호환)."""
    from src.taxonomy.career_levels import normalize_career_level

    raw_text, min_y, max_y = _parse_career_raw(text)
    return normalize_career_level(
        raw_text=raw_text, min_years=min_y, max_years=max_y
    )


def _extract_posted_at(soup: BeautifulSoup, ld: dict[str, Any]) -> str | None:
    """게시일 추출. ISO date 형식(YYYY-MM-DD) 또는 None 반환."""
    for key in ("datePosted", "validThrough"):
        val = ld.get(key)
        if val:
            m = re.search(r"\d{4}-\d{2}-\d{2}", str(val))
            if m:
                return m.group()

    for sel in [
        "td[data-bind='postDt']",
        ".post-date",
        "time[datetime]",
        "[class*='postDate']",
        "[class*='registDt']",
    ]:
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


def _extract_flight_skills(raw_html: str) -> list[str]:
    """
    Next.js Flight data에서 skills 배열을 추출한다.

    잡코리아 상세 페이지 HTML에는 공고 본문이 클라이언트 렌더링이지만,
    서버가 self.__next_f.push([...]) 형태로 이스케이프된 JSON을 내려준다.
    그 안에 \\\"skills\\\":[{\\\"name\\\":\\\"Java\\\",\\\"skillTypeCode\\\":\\\"HARD_SKILL\\\"}]
    형태로 기술 스택 목록이 포함돼 있다.
    """
    # skillTypeCode 가 있는 skills 배열만 추출 (code 기반 배열과 구분)
    m = re.search(
        r'\\"skills\\":\s*(\[(?:\{[^}]*\\"skillTypeCode\\"[^}]*\},?\s*)+\])',
        raw_html,
    )
    if not m:
        return []
    try:
        skills_raw = m.group(1).replace('\\"', '"')
        skills_data = json.loads(skills_raw)
        from src.normalization.skill_noise_filter import filter_skill_candidates

        return filter_skill_candidates(
            s["name"]
            for s in skills_data
            if isinstance(s, dict) and s.get("name")
        )
    except Exception:
        return []



def _extract_education_level(ld: dict[str, Any]) -> str | None:
    """학력 요건 추출. JSON-LD educationRequirements 우선 사용."""
    raw = ld.get("educationRequirements", "")
    if not raw:
        return None

    text = str(raw).strip()
    if "학력무관" in text or "무관" in text:
        return "ANY"
    if "박사" in text:
        return "DOCTOR"
    if "석사" in text:
        return "MASTER"
    # 초대졸/전문대 체크를 대졸보다 먼저 — "초대졸"에 "대졸"이 포함되므로 순서 중요
    if "초대졸" in text or "전문대" in text or "2년제" in text or "3년제" in text:
        return "ASSOCIATE"
    if "대졸" in text or "학사" in text or "4년제" in text:
        return "BACHELOR"
    if "고졸" in text or "고등학교" in text:
        return "HIGH_SCHOOL"
    return "ANY"


def _extract_expires_at(ld: dict[str, Any]) -> str | None:
    """공고 마감일 추출. JSON-LD validThrough 우선 사용."""
    val = ld.get("validThrough", "")
    if val:
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(val))
        if m:
            return m.group()
    return None


def _extract_company_extras(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """
    페이지 텍스트에서 (industry_name, size_category) 추출.

    잡코리아 기업 정보 섹션 예시:
      산업(업종)
      포털·컨텐츠·커뮤니티
      51 ~ 300명 이하
      중소기업 (비상장)
    """
    lines = [l.strip() for l in soup.get_text(separator="\n", strip=True).split("\n") if l.strip()]

    industry: str | None = None
    size_category: str | None = None

    # 산업(업종) 레이블 다음 줄 → industry_name
    for i, line in enumerate(lines):
        if "산업" in line and ("업종" in line or line == "산업"):
            if i + 1 < len(lines):
                candidate = lines[i + 1]
                if len(candidate) < 60 and "명" not in candidate and "기업" not in candidate:
                    industry = candidate
                    break

    # size_category: 명시적 기업 규모 키워드
    full_text = " ".join(lines)
    if "대기업" in full_text or "공기업" in full_text:
        size_category = "LARGE"
    elif "중견기업" in full_text:
        size_category = "MID"
    elif "중소기업" in full_text:
        size_category = "SME"
    elif "스타트업" in full_text or "벤처" in full_text:
        size_category = "STARTUP"

    # 직원 수로 보완 (규모 키워드 없을 때)
    if not size_category:
        m = re.search(r"(\d[\d,]*)\s*~\s*(\d[\d,]*)\s*명", full_text)
        if m:
            max_count = int(m.group(2).replace(",", ""))
            if max_count <= 50:
                size_category = "STARTUP"
            elif max_count <= 300:
                size_category = "SME"
            elif max_count <= 1000:
                size_category = "MID"
            else:
                size_category = "LARGE"

    return industry, size_category


def _extract_skills(description: str, page_text: str = "") -> list[str]:
    """기술 스택 키워드를 추출한다.

    잡코리아 상세 페이지는 공고 본문이 클라이언트 렌더링이므로,
    JSON-LD description 과 전체 페이지 텍스트를 합산해 스캔한다.
    """
    from src.taxonomy.skills import find_skills_in_text
    return find_skills_in_text(description + " " + page_text)


# _parse_location_text, _trim_to_district → src.normalization.location_utils (상단 alias)
