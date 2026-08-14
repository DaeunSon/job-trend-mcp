"""
The Muse raw_job_postings (parse_status: PENDING) → job_postings 파싱.

주요 함수:
  parse_raw_posting()    — 단일 RawJobPosting dict → JobPosting dict 변환
  run_themuse_parse()    — 저장된 raw 파일을 일괄 파싱하는 오케스트레이터

파싱 전략:
  - raw_text 필드에 저장된 The Muse API 응답 JSON 원문을 파싱한다.
  - contents 필드(HTML) → 텍스트 변환 (BeautifulSoup)
  - alias_resolver로 회사명·지역명·직무·직군 표준화
  - 파싱 성공 → parse_status: PARSED, parsed_job_posting_id 연결
  - 파싱 실패 → parse_status: FAILED (부분 실패 허용)

The Muse API 응답 필드 (2026-07-29 실제 호출 확인):
  {
    "id": int,
    "name": str,                         # 공고 제목 (title에 해당)
    "contents": str,                     # HTML 설명
    "type": str,                         # "external" 등
    "publication_date": str,             # ISO datetime (예: "2025-03-09T10:29:29Z")
    "short_name": str,                   # URL slug
    "model_type": str,                   # "jobs"
    "locations": [{"name": str}],        # 지역 목록 (예: [{"name": "New York, NY"}])
    "categories": [{"name": str}],       # 카테고리 목록 (예: [{"name": "Software Engineering"}])
    "levels": [{"name": str, "short_name": str}],  # 레벨 목록
    "tags": list[str],                   # 태그 (종종 비어 있음)
    "refs": {"landing_page": str},       # 원문 URL
    "company": {"id": int, "short_name": str, "name": str}
  }
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.crawlers.parse_batch import process_raw_file
from src.models.schemas import SalaryInfo
from src.normalization.job_taxonomy import extract_themuse_taxonomy_raw
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.storage.json_writer import _BASE_DATA_DIR, iter_collection_json_files

logger = logging.getLogger(__name__)

_RAW_COLLECTION    = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME       = "themuse"

# The Muse level.name → career_level 원문 (정규화는 posting_normalizer)
_LEVEL_RAW: dict[str, str] = {
    "entry level":  "entry level",
    "mid level":    "mid level",
    "senior level": "senior level",
}

# 잘 알려진 기술 스택 키워드 (description 보조 추출용)
_CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₩": "KRW",
}

# "$100,000.00 - $115,000.00" / "€30k - €40k"
_SALARY_RANGE_RE = re.compile(
    r"([A-Z]{0,2}[\$€£¥₩])\s*([\d,]+\.?\d*)\s*[kK]?"
    r"(?:\s*[-–~]\s*[A-Z]{0,2}[\$€£¥₩]?\s*([\d,]+\.?\d*)\s*[kK]?)?",
    re.IGNORECASE,
)

# 본문에서 급여·보상 관련 구간 탐색
_SALARY_SECTION_RE = re.compile(
    r"(?:COMPENSATION(?:\s+AND\s+BENEFITS)?|Pay range|Salary range|Base salary)"
    r"[^\n]*(?:\n(?![A-Z]{2,}(?:\s+[A-Z]{2,})*:)[^\n]+)*",
    re.IGNORECASE,
)

# API category가 실제 직무와 어긋날 때 무시할 제목 키워드 — job_taxonomy.extract_themuse_taxonomy_raw 참고

_KNOWN_TECH_SKILLS: frozenset[str] = frozenset({
    "python", "java", "javascript", "typescript", "react", "vue", "angular",
    "node.js", "spring", "django", "flask", "go", "golang", "kotlin", "swift",
    "c++", "c#", "ruby", "php", "rust", "scala",
    "aws", "gcp", "azure", "kubernetes", "docker", "terraform",
    "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "pytorch", "tensorflow", "sklearn", "scikit-learn",
    "spark", "hadoop", "kafka", "airflow",
    "git", "linux", "nginx",
})


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
    source_name   = raw.get("source_name", "")
    raw_text      = raw.get("raw_text", "")

    if not raw_text:
        logger.warning("[themuse] raw_text 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        job = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[themuse] raw_text JSON 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc,
        )
        return None

    try:
        title               = _extract_title(job)
        company_raw         = _extract_company_name(job)
        location_raw        = _extract_location_raw(job)
        description         = _extract_description(job)
        employment_type_raw = _extract_employment_type_raw(job)
        career_raw_text     = _extract_career_raw_text(job)
        skill_names         = _extract_skill_names(job, description)
        posted_at           = _extract_posted_at(job, raw)
        salary_info         = _extract_salary(description)
        function_raw, category_raw = extract_themuse_taxonomy_raw(job, title, description)

        first_location = _extract_first_location(job)
        country   = _normalize_country(first_location)
        city      = first_location if first_location.lower() not in ("remote", "worldwide", "") else ""

        extracted = RawExtractedFields(
            title=title,
            company_raw=company_raw,
            description=description,
            location_raw=location_raw,
            employment_type_raw=employment_type_raw,
            career_raw_text=career_raw_text,
            work_arrangement_text=location_raw + " " + description[:200],
            education_level=None,
            job_category_raw=category_raw,
            job_function_raw=function_raw,
            skills=skill_names,
            salary=salary_info,
            posted_at=posted_at,
            expires_at=None,
            use_korean_location_parser=False,
            location_country=country,
            location_city=city,
            location_region=None,
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[themuse] 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_themuse_parse(
    crawl_date: str | None = None,
    base_dir: str | None = None,
    reparse: bool = False,
) -> None:
    """
    저장된 raw_job_postings 문서를 일괄 파싱한다.

    reparse=False (기본): parse_status='PENDING'인 것만 파싱
    reparse=True       : 파일 내 모든 문서를 다시 파싱 (PARSED 포함)
    """
    _data_root = Path(base_dir) if base_dir else _BASE_DATA_DIR
    raw_root   = _data_root / _RAW_COLLECTION

    if not raw_root.exists():
        logger.warning("[themuse] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="themuse",
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
        "[themuse] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
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
        source_name=_SOURCE_NAME if reparse else None,
        reparse=reparse,
        log_prefix="[themuse]",
    )


# ---------------------------------------------------------------------------
# 필드별 파서
# ---------------------------------------------------------------------------

def _extract_title(job: dict[str, Any]) -> str:
    """공고 제목 — The Muse는 'name' 필드 사용 ('title' 아님)."""
    return (job.get("name") or "").strip()


def _extract_company_name(job: dict[str, Any]) -> str:
    """회사명 — company.name 필드."""
    company = job.get("company") or {}
    return (company.get("name") or "").strip()


def _extract_location_raw(job: dict[str, Any]) -> str:
    """지역명 원문 — locations 목록의 첫 번째 name."""
    locations: list[dict] = job.get("locations") or []
    if not locations:
        return ""
    return ", ".join(loc.get("name", "") for loc in locations if loc.get("name"))


def _extract_first_location(job: dict[str, Any]) -> str:
    """locations 목록의 첫 번째 도시·지역명을 반환한다."""
    locations: list[dict] = job.get("locations") or []
    if not locations:
        return ""
    raw = (locations[0].get("name") or "").strip()
    # "New York, NY" → "New York"
    return raw.split(",")[0].strip()


def _extract_description(job: dict[str, Any]) -> str:
    """
    contents 필드(HTML)에서 태그를 제거하고 텍스트만 반환한다.
    The Muse는 'description'이 아니라 'contents' 필드를 사용한다.
    """
    from src.crawlers.common.http_utils import html_description_to_text

    return html_description_to_text(job.get("contents") or "")


def _extract_employment_type_raw(job: dict[str, Any]) -> str:
    """
    The Muse API는 별도 고용형태 필드를 제공하지 않는다.
    description에서 full-time / part-time 등을 추출하거나 기본값("full_time")을 반환한다.
    """
    description = _extract_description(job)
    lower = description.lower()
    if "part-time" in lower or "part time" in lower:
        return "part_time"
    if "contract" in lower:
        return "contract"
    if "internship" in lower or "intern " in lower:
        return "internship"
    return "full_time"


def _extract_career_raw_text(job: dict[str, Any]) -> str:
    """levels 필드 + description 원문을 career_level 추론에 사용한다."""
    levels: list[dict] = job.get("levels") or []
    level_text = " ".join(lv.get("name", "") for lv in levels)
    description = _extract_description(job)
    return f"{level_text} {description[:300]}"


def _extract_skill_names(job: dict[str, Any], description: str) -> list[str]:
    """tags + description 키워드 → skill 이름 목록."""
    from src.normalization.skill_noise_filter import filter_skill_candidates, is_skill_noise

    tags: list[str] = job.get("tags") or []
    skills: list[str] = []
    seen: set[str] = set()

    for tag in tags:
        if isinstance(tag, dict):
            raw_text = (tag.get("name") or tag.get("value") or "").strip()
        elif isinstance(tag, str):
            raw_text = tag.strip()
        else:
            continue
        if not raw_text or is_skill_noise(raw_text):
            continue
        if raw_text not in seen:
            seen.add(raw_text)
            skills.append(raw_text)

    for kw in _KNOWN_TECH_SKILLS:
        pattern = re.compile(
            r"(?<![a-zA-Z0-9])" + re.escape(kw) + r"(?![a-zA-Z0-9])",
            re.IGNORECASE,
        )
        if pattern.search(description) and kw not in seen:
            seen.add(kw)
            skills.append(kw)

    return filter_skill_candidates(skills)


def _extract_posted_at(job: dict[str, Any], raw: dict[str, Any]) -> str:
    """publication_date → ISO date 문자열."""
    pub_date = job.get("publication_date") or ""
    if pub_date:
        try:
            dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            return dt.date().isoformat()
        except (ValueError, TypeError):
            pass

    collected_at = raw.get("collected_at", "")
    if collected_at:
        try:
            dt = datetime.fromisoformat(collected_at)
            return dt.date().isoformat()
        except ValueError:
            pass

    return date.today().isoformat()


def _extract_salary(description: str) -> SalaryInfo:
    """
    본문에서 급여·보상 정보를 추출한다.

    - Pay range / Level N: $X - $Y/per year → min/max 집계
    - 보너스·수당 문구만 있는 경우 → raw_text 저장
    """
    if not description:
        return SalaryInfo()

    section_match = _SALARY_SECTION_RE.search(description)
    section = section_match.group(0).strip() if section_match else description

    ranges: list[tuple[str | None, str | None, str | None, str]] = []
    for match in _SALARY_RANGE_RE.finditer(section):
        currency_sym = match.group(1) or ""
        low_raw = match.group(2)
        high_raw = match.group(3)
        if not low_raw:
            continue
        currency_code: str | None = None
        for sym, code in _CURRENCY_SYMBOLS.items():
            if currency_sym.endswith(sym) or currency_sym == sym:
                currency_code = code
                break
        low = _parse_salary_amount(low_raw, section)
        high = _parse_salary_amount(high_raw, section) if high_raw else low
        if low is not None:
            ranges.append((low, high, currency_code, match.group(0)))

    if ranges:
        mins = [int(r[0]) for r in ranges if r[0]]
        maxs = [int(r[1]) for r in ranges if r[1]]
        currency_code = next((r[2] for r in ranges if r[2]), None)
        if section_match:
            raw_text = section_match.group(0).strip()
        else:
            raw_text = "\n".join(dict.fromkeys(r[3] for r in ranges))
        pay_period = _infer_pay_period(raw_text)
        return SalaryInfo(
            raw_text=raw_text,
            min_amount=str(min(mins)) if mins else None,
            max_amount=str(max(maxs)) if maxs else None,
            currency_code=currency_code,
            pay_period=pay_period,
        )

    # 구조화된 range 없음 — $ 포함 보상 문장 추출 (보너스·수당 등)
    comp_lines = [
        line.strip()
        for line in description.splitlines()
        if "$" in line or "€" in line or "£" in line
    ]
    if not comp_lines:
        return SalaryInfo()

    raw_text = "\n".join(comp_lines[:3])
    currency_code = "USD" if "$" in raw_text else None
    amounts: list[int] = []
    for match in _SALARY_RANGE_RE.finditer(raw_text):
        val = _parse_salary_amount(match.group(2), raw_text)
        if val is not None:
            amounts.append(int(val))
        if match.group(3):
            val = _parse_salary_amount(match.group(3), raw_text)
            if val is not None:
                amounts.append(int(val))

    return SalaryInfo(
        raw_text=raw_text,
        min_amount=str(min(amounts)) if amounts else None,
        max_amount=str(max(amounts)) if len(amounts) > 1 else None,
        currency_code=currency_code,
        pay_period=_infer_pay_period(raw_text),
    )


def _parse_salary_amount(raw: str | None, context: str) -> str | None:
    if not raw:
        return None
    cleaned = raw.replace(",", "")
    try:
        val = float(cleaned)
        if re.search(re.escape(raw.strip()) + r"\s*[kK]", context):
            val *= 1000
        return str(int(val))
    except ValueError:
        return None


def _infer_pay_period(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"(?:/year|/yr|per year|annual|yearly)", lower):
        return "ANNUAL"
    if re.search(r"(?:/month|/mo|per month|monthly)", lower):
        return "MONTHLY"
    if re.search(r"(?:/hour|/hr|per hour)(?!\s+requirement)", lower):
        return "HOURLY"
    if re.search(r"\bhourly\b(?!\s+requirement)", lower):
        return "HOURLY"
    return None


def _normalize_country(raw: str) -> str:
    """도시/지역 표기를 국가명으로 정규화한다."""
    _MAP: dict[str, str] = {
        "worldwide": "Global",
        "anywhere": "Global",
        "remote": "Global",
        "global": "Global",
        "united states": "United States",
        "usa": "United States",
        "us": "United States",
        "uk": "United Kingdom",
        "united kingdom": "United Kingdom",
        "eu": "Europe",
        "europe": "Europe",
        "canada": "Canada",
        "australia": "Australia",
        "germany": "Germany",
        "france": "France",
        "india": "India",
        "brazil": "Brazil",
        "korea": "South Korea",
        "south korea": "South Korea",
    }
    return _MAP.get(raw.lower(), "United States")
