"""
USAJobs 전용 추출기 / 파서.

원칙
----
- raw_text : ExecuteSearch Jobs[] 항목 JSON (급여 보강 필드 포함 가능)
- raw_html : 공고 상세 페이지 HTML (본문·근무형태·교육 등)
- 정규화는 공통 모듈(posting_normalizer.build_job_posting)에서 처리한다.
- JobGrade / LowGrade / HighGrade 등 GS 등급은 스키마에 없으므로
  별도 필드로 저장하지 않는다 (SalaryDisplay 원문에 포함된 경우는 그대로 둠).

수집 방식
---------
1) POST /Search/ExecuteSearch → Jobs[] 목록
2) GET  /job/{DocumentID}     → 상세 HTML 을 raw_html 에 저장
   - 급여: RemunerationMaximumAmount / "$X - $Y per year" → job JSON 주입
   - 본문: JSON-LD JobPosting (description/responsibilities/qualifications)
   - 근무형태: Overview 의 Remote job / Telework eligible

실측 검색 필드 (2026-07-30):
  Title, Agency, Department, SubAgency,
  SalaryDisplay, MinimumRange,
  WorkType, WorkSchedule,
  LocationName, LocationDisplay, Location,
  PositionURI, DocumentID, PositionID,
  HiringPath, JobCategoryCode,
  PositionStartDate, PositionEndDate, DateDisplay, PostedDateDisplay,
  Relocation, ...

주요 함수
---------
extract_job_fields() — Jobs[] 항목 dict → 원시 필드 dict (정규화 없음)
extract_detail_fields() — 상세 HTML → description/education/work_arrangement 등
parse_raw_posting()  — 단일 raw 문서 → job_postings dict
run_usajobs_parse()  — 저장된 raw 파일 일괄 파싱
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.crawlers.parse_batch import process_raw_file
from src.models.schemas import SalaryInfo
from src.normalization.job_taxonomy import extract_usajobs_taxonomy_raw
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.storage.json_writer import _BASE_DATA_DIR, iter_collection_json_files

logger = logging.getLogger(__name__)

_RAW_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "usajobs"

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# "Starting at $111,147 Per year (GS 13)" / "$50,000 to $80,000 Per year"
_SALARY_AMOUNT_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)",
)
_PER_YEAR_RE = re.compile(r"per\s+year", re.IGNORECASE)
_PER_HOUR_RE = re.compile(r"per\s+hour", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 공개 API — Jobs[] 항목 추출
# ---------------------------------------------------------------------------


def extract_job_fields(job: dict[str, Any]) -> dict[str, Any]:
    """
    USAJobs ExecuteSearch Jobs[] 항목에서 원문 필드를 추출한다.

    Returns
    -------
    dict (정규화 전 원문값):
      title, company, description, location_raw,
      employment_type_raw, career_raw,
      salary_raw, salary_min, salary_max,
      posted_at, expires_at,
      job_category_raw, work_arrangement_text,
      original_url, document_id
    """
    title = (job.get("Title") or "").strip()
    agency = (job.get("Agency") or "").strip()
    department = (job.get("Department") or "").strip()
    company = agency or department

    location_raw = (
        (job.get("LocationName") or "").strip()
        or (job.get("LocationDisplay") or "").strip()
        or (job.get("Location") or "").strip()
    )

    work_type = (job.get("WorkType") or "").strip()
    work_schedule = (job.get("WorkSchedule") or "").strip()
    employment_parts = [p for p in (work_type, work_schedule) if p]
    employment_type_raw = " ".join(employment_parts)

    career_raw = _hiring_path_raw(job.get("HiringPath"))
    salary_raw = (job.get("SalaryDisplay") or "").strip()
    salary_min = job.get("MinimumRange")
    salary_max = job.get("MaximumRange")

    posted_at = _normalize_iso_date(job.get("PositionStartDate") or "")
    expires_at = _normalize_iso_date(job.get("PositionEndDate") or "") or None

    job_category_raw = _job_category_raw(job.get("JobCategoryCode"))

    work_arrangement_text = _build_work_arrangement_text(
        location_raw=location_raw,
        location_display=(job.get("LocationDisplay") or ""),
        relocation=job.get("Relocation"),
    )

    description = _build_description(job, career_raw=career_raw)

    uri = (job.get("PositionURI") or "").replace(":443", "").strip()
    document_id = job.get("DocumentID")
    if not uri and document_id is not None:
        uri = f"https://www.usajobs.gov/job/{document_id}"

    return {
        "title": title,
        "company": company,
        "description": description,
        "location_raw": location_raw,
        "employment_type_raw": employment_type_raw,
        "career_raw": career_raw,
        "salary_raw": salary_raw,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "posted_at": posted_at or None,
        "expires_at": expires_at,
        "job_category_raw": job_category_raw,
        "work_arrangement_text": work_arrangement_text,
        "original_url": uri,
        "document_id": str(document_id) if document_id is not None else "",
    }


# ---------------------------------------------------------------------------
# 공개 API — raw → job_postings
# ---------------------------------------------------------------------------


def parse_raw_posting(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    단일 raw_job_postings 문서를 job_postings 구조로 파싱한다.
    실패 시 None.

    raw_html 이 있으면 상세 페이지에서 본문·교육·근무형태·급여를 보강한다.
    """
    source_job_id = raw.get("source_job_id", "")
    source_name = raw.get("source_name", "")
    raw_text_str = raw.get("raw_text", "")
    raw_html = raw.get("raw_html") or ""

    if not raw_text_str:
        logger.warning("[usajobs] raw_text 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        job: dict[str, Any] = json.loads(raw_text_str)
    except json.JSONDecodeError as exc:
        logger.error(
            "[usajobs] raw_text JSON 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc,
        )
        return None

    # 상세 HTML 이 있으면 job JSON 급여 필드도 보강 (과거 raw 재파싱 대비)
    if raw_html:
        apply_detail_salary_to_job(job, raw_html)

    try:
        fields = extract_job_fields(job)
    except Exception as exc:
        logger.error(
            "[usajobs] extract_job_fields 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None

    if not fields.get("title"):
        logger.warning(
            "[usajobs] 제목 추출 실패 (%s/%s) — 파싱 건너뜀",
            source_name, source_job_id,
        )
        return None

    detail = extract_detail_fields(raw_html) if raw_html else {}
    description = (detail.get("description") or "").strip() or fields["description"]
    education_level = detail.get("education_level")
    work_arrangement_override = detail.get("work_arrangement_override")
    work_arrangement_text = " ".join(
        p for p in [
            fields.get("work_arrangement_text") or "",
            detail.get("work_arrangement_text") or "",
        ] if p
    ).strip()

    function_raw, category_raw = extract_usajobs_taxonomy_raw(
        job, fields["title"], description,
    )

    try:
        salary = _parse_salary(
            fields.get("salary_raw") or "",
            fields.get("salary_min"),
            fields.get("salary_max"),
        )
        city, region, country = _parse_us_location(fields.get("location_raw") or "")

        extracted = RawExtractedFields(
            title=fields["title"],
            company_raw=fields["company"],
            description=description,
            location_raw=fields["location_raw"],
            employment_type_raw=fields["employment_type_raw"],
            career_raw_text=fields["career_raw"],
            work_arrangement_text=work_arrangement_text,
            work_arrangement_override=work_arrangement_override,
            education_level=education_level,
            job_category_raw=category_raw,
            job_function_raw=function_raw,
            salary=salary,
            posted_at=fields.get("posted_at"),
            expires_at=fields.get("expires_at"),
            location_country=country,
            location_region=region,
            location_city=city,
            use_korean_location_parser=False,
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[usajobs] build_job_posting 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_usajobs_parse(
    crawl_date: str | None = None,
    base_dir: str | None = None,
    reparse: bool = False,
) -> None:
    """저장된 raw_job_postings 문서를 일괄 파싱한다."""
    data_root = Path(base_dir) if base_dir else _BASE_DATA_DIR
    raw_root = data_root / _RAW_COLLECTION

    if not raw_root.exists():
        logger.warning("[usajobs] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="usajobs",
    ):
        n_ok, n_fail = process_raw_file(
            json_file=json_file,
            date_label=date_label,
            base_dir=base_dir,
            parse_fn=parse_raw_posting,
            source_name=_SOURCE_NAME if reparse else None,
            reparse=reparse,
            log_prefix="[usajobs]",
        )
        total_parsed += n_ok
        total_failed += n_fail

    logger.info(
        "[usajobs] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
        total_parsed,
        total_failed,
        " (재파싱)" if reparse else "",
    )


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _hiring_path_raw(hiring_path: Any) -> str:
    if not isinstance(hiring_path, list):
        return ""
    labels: list[str] = []
    for item in hiring_path:
        if not isinstance(item, dict):
            continue
        label = (
            (item.get("SearchDisplay") or "").strip()
            or (item.get("Tooltip") or "").strip()
            or (item.get("Code") or "").strip()
        )
        if label and label not in labels:
            labels.append(label)
    return "; ".join(labels)


def _job_category_raw(categories: Any) -> str:
    if not isinstance(categories, list) or not categories:
        return ""
    first = categories[0]
    if isinstance(first, dict):
        return (first.get("Name") or "").strip()
    return ""


def _build_description(job: dict[str, Any], career_raw: str) -> str:
    """목록 API에 본문이 없으므로 가용 메타데이터로 요약 텍스트를 구성한다."""
    parts: list[str] = []
    for label, key in [
        ("Department", "Department"),
        ("Agency", "Agency"),
        ("SubAgency", "SubAgency"),
        ("Work type", "WorkType"),
        ("Work schedule", "WorkSchedule"),
        ("Location", "LocationDisplay"),
        ("Salary", "SalaryDisplay"),
        ("Dates", "DateDisplay"),
        ("Announcement", "PositionID"),
    ]:
        val = (job.get(key) or "")
        if isinstance(val, str) and val.strip():
            parts.append(f"{label}: {val.strip()}")
    if career_raw:
        parts.append(f"Hiring path: {career_raw}")
    cats = _job_category_raw(job.get("JobCategoryCode"))
    if cats:
        parts.append(f"Occupational series: {cats}")
    return "\n".join(parts)


def _build_work_arrangement_text(
    location_raw: str,
    location_display: str,
    relocation: Any,
) -> str:
    chunks = [location_raw, location_display]
    if relocation is True:
        chunks.append("relocation")
    elif relocation is False:
        chunks.append("no relocation")
    return " ".join(c.strip() for c in chunks if c and str(c).strip())


def _normalize_iso_date(raw: str) -> str:
    if not raw:
        return ""
    m = _DATE_RE.search(str(raw))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


_REMUNERATION_MIN_RE = re.compile(
    r'"RemunerationMinimumAmount"\s*:\s*"([\d.]+)"',
)
_REMUNERATION_MAX_RE = re.compile(
    r'"RemunerationMaximumAmount"\s*:\s*"([\d.]+)"',
)
_SALARY_RANGE_DISPLAY_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*[-–]\s*\$\s*([\d,]+(?:\.\d+)?)"
    r"(?:\s*per\s+(year|hour))?",
    re.IGNORECASE,
)


def extract_detail_fields(html: str) -> dict[str, Any]:
    """
    공고 상세 HTML 에서 본문·교육·근무형태 힌트를 추출한다.

    Returns
    -------
    description, education_level, work_arrangement_text, work_arrangement_override
    """
    if not html:
        return {}

    jsonld = _extract_jobposting_jsonld(html)
    overview = _extract_overview_fields(html)

    description = _build_detail_description(jsonld, html)
    education_level = _html_to_text(jsonld.get("educationRequirements") or "") or None
    if education_level and len(education_level) > 300:
        education_level = education_level[:300].rstrip() + "…"

    remote_raw = (overview.get("Remote job") or "").strip()
    telework_raw = (overview.get("Telework eligible") or "").strip()
    work_bits = []
    if remote_raw:
        work_bits.append(f"Remote job: {remote_raw}")
    if telework_raw:
        work_bits.append(f"Telework eligible: {telework_raw}")
    work_arrangement_text = " ".join(work_bits)

    work_arrangement_override: str | None = None
    remote_yes = _is_yes(remote_raw)
    telework_yes = _is_yes(telework_raw)
    if remote_yes:
        work_arrangement_override = "REMOTE"
    elif telework_yes:
        work_arrangement_override = "HYBRID"
    elif remote_raw or telework_raw:
        # Remote/Telework 가 명시적으로 No 인 경우
        if _is_no(remote_raw) and (not telework_raw or _is_no(telework_raw)):
            work_arrangement_override = "ONSITE"

    return {
        "description": description,
        "education_level": education_level,
        "work_arrangement_text": work_arrangement_text,
        "work_arrangement_override": work_arrangement_override,
        "overview": overview,
    }


def extract_salary_from_detail_html(html: str) -> dict[str, str | None]:
    """
    공고 상세 HTML 에서 급여 min/max/표시문을 추출한다.

    Returns
    -------
    {"min": "111147"|None, "max": "158322"|None, "display": "$111,147 - $158,322 per year"|None}
    """
    if not html:
        return {"min": None, "max": None, "display": None}

    min_amount: str | None = None
    max_amount: str | None = None
    display: str | None = None

    m_min = _REMUNERATION_MIN_RE.search(html)
    m_max = _REMUNERATION_MAX_RE.search(html)
    if m_min:
        min_amount = _normalize_amount(m_min.group(1))
    if m_max:
        max_amount = _normalize_amount(m_max.group(1))

    m_disp = _SALARY_RANGE_DISPLAY_RE.search(html)
    if m_disp:
        disp_min = _normalize_amount(m_disp.group(1))
        disp_max = _normalize_amount(m_disp.group(2))
        period = (m_disp.group(3) or "year").lower()
        if disp_min and disp_max:
            display = (
                f"${int(disp_min):,} - ${int(disp_max):,} per {period}"
            )
            min_amount = min_amount or disp_min
            max_amount = max_amount or disp_max

    return {"min": min_amount, "max": max_amount, "display": display}


def apply_detail_salary_to_job(job: dict[str, Any], html: str) -> dict[str, Any]:
    """상세 HTML 급여를 job dict 에 MaximumRange / SalaryDisplay 등으로 주입한다."""
    info = extract_salary_from_detail_html(html)
    if info.get("max"):
        job["MaximumRange"] = info["max"]
    if info.get("min") and _is_empty_amount(job.get("MinimumRange")):
        job["MinimumRange"] = info["min"]
    if info.get("display"):
        job["SalaryDisplay"] = info["display"]
    return job


def _extract_jobposting_jsonld(html: str) -> dict[str, Any]:
    """application/ld+json JobPosting 객체를 반환한다."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _extract_jobposting_jsonld_regex(html)

    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    return item
    return {}


def _extract_jobposting_jsonld_regex(html: str) -> dict[str, Any]:
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return {}


def _extract_overview_fields(html: str) -> dict[str, str]:
    """Overview dt/dd 쌍을 label → value 로 추출한다."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    overview: dict[str, str] = {}
    for dt in soup.find_all("dt"):
        label = dt.get_text(" ", strip=True)
        if not label or label in overview:
            continue
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        value = dd.get_text(" ", strip=True)
        # Salary dd 에 부가 설명이 붙는 경우가 있어 첫 문장만 유지
        if label.lower() == "salary":
            m = _SALARY_RANGE_DISPLAY_RE.search(value)
            if m:
                period = (m.group(3) or "year").lower()
                value = (
                    f"${int(_normalize_amount(m.group(1)) or 0):,} - "
                    f"${int(_normalize_amount(m.group(2)) or 0):,} per {period}"
                )
        overview[label] = value
    return overview


def _build_detail_description(jsonld: dict[str, Any], html: str) -> str:
    """JSON-LD + 섹션 텍스트로 본문을 구성한다."""
    parts: list[str] = []

    summary = _html_to_text(jsonld.get("description") or "")
    duties = _html_to_text(jsonld.get("responsibilities") or "")
    quals = _html_to_text(jsonld.get("qualifications") or "")
    education = _html_to_text(jsonld.get("educationRequirements") or "")

    # JSON-LD 가 짧으면 HTML 섹션으로 보강
    if len(summary) < 200:
        summary = _extract_section_text(html, "Summary") or summary
    if len(duties) < 200:
        duties = _extract_section_text(html, "Duties") or duties
    if len(quals) < 200:
        quals = (
            _extract_section_text(html, "Qualifications")
            or _extract_section_text(html, "Requirements")
            or quals
        )

    if summary:
        parts.append("Summary\n" + summary)
    if duties:
        parts.append("Duties\n" + duties)
    if quals:
        parts.append("Qualifications\n" + quals)
    if education:
        parts.append("Education\n" + education)

    return "\n\n".join(parts).strip()


def _extract_section_text(html: str, heading: str, limit: int = 8000) -> str:
    """h2/h3 헤딩 아래 본문을 다음 헤딩 전까지 모은다."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    target = None
    for h in soup.find_all(["h2", "h3"]):
        if h.get_text(" ", strip=True).lower() == heading.lower():
            target = h
            break
    if target is None:
        return ""

    chunks: list[str] = []
    for sib in target.next_siblings:
        name = getattr(sib, "name", None)
        if name in ("h2", "h3"):
            break
        if not name:
            continue
        if name in ("script", "style", "nav"):
            continue
        text = sib.get_text("\n", strip=True) if hasattr(sib, "get_text") else ""
        if text:
            chunks.append(text)
        if sum(len(c) for c in chunks) >= limit:
            break
    return "\n".join(chunks).strip()[:limit]


def _html_to_text(raw: str) -> str:
    if not raw:
        return ""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
    except ImportError:
        text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()


def _is_yes(raw: str) -> bool:
    return raw.strip().lower() in {"yes", "y", "true"}


def _is_no(raw: str) -> bool:
    return raw.strip().lower() in {"no", "n", "false"}


def _normalize_amount(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text or text == "0":
        return None
    try:
        return str(int(float(text)))
    except (ValueError, TypeError):
        return None


def _is_empty_amount(raw: Any) -> bool:
    return _normalize_amount(raw) is None


def _parse_salary(
    salary_raw: str,
    salary_min: Any = None,
    salary_max: Any = None,
) -> SalaryInfo:
    amounts = _SALARY_AMOUNT_RE.findall(salary_raw or "")
    min_amount: str | None = None
    max_amount: str | None = None
    if amounts:
        min_amount = amounts[0].replace(",", "")
        if len(amounts) > 1:
            max_amount = amounts[1].replace(",", "")

    if not min_amount:
        min_amount = _normalize_amount(salary_min)
    if not max_amount:
        max_amount = _normalize_amount(salary_max)

    pay_period: str | None = None
    if _PER_YEAR_RE.search(salary_raw or ""):
        pay_period = "ANNUAL"
    elif _PER_HOUR_RE.search(salary_raw or ""):
        pay_period = "HOURLY"
    elif min_amount:
        pay_period = "ANNUAL"

    return SalaryInfo(
        raw_text=salary_raw or None,
        min_amount=min_amount,
        max_amount=max_amount,
        currency_code="USD" if (min_amount or max_amount or salary_raw) else None,
        pay_period=pay_period,
    )


def _parse_us_location(location_raw: str) -> tuple[str, str, str]:
    """
    'Woodlawn, Maryland' / 'Washington, DC' / 'Remote' → (city, region, country).
    """
    text = (location_raw or "").strip()
    if not text:
        return "", "", "United States"
    lower = text.lower()
    if "remote" in lower or "telework" in lower:
        return "Remote", "", "United States"
    if "," in text:
        city, region = [p.strip() for p in text.split(",", 1)]
        return city, region, "United States"
    return text, "", "United States"
