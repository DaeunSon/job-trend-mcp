"""
Remotive raw_job_postings (parse_status: PENDING) → job_postings 파싱.

주요 함수:
  parse_raw_posting()    — 단일 RawJobPosting dict → JobPosting dict 변환
  run_remotive_parse()   — 저장된 raw 파일을 일괄 파싱하는 오케스트레이터

파싱 전략:
  - raw_text 필드에 저장된 Remotive API 응답 JSON 원문을 파싱한다.
  - description 필드는 HTML → 텍스트 변환 (BeautifulSoup)
  - salary 문자열 → SalaryInfo (정규식으로 min/max/currency 파싱 시도)
  - alias_resolver로 회사명·기술 스택·지역명 표준화
  - 파싱 성공 → parse_status: PARSED, parsed_job_posting_id 연결
  - 파싱 실패 → parse_status: FAILED (부분 실패 허용)

Remotive API 응답 필드 (공식 문서 기준):
  {
    "id": int,
    "url": str,
    "title": str,
    "company_name": str,
    "company_logo": str,
    "category": str,                     # "Software Development" 등
    "job_type": str,                     # "full_time" | "contract" | "part_time" | "freelance"
    "publication_date": str,             # ISO datetime (예: "2020-02-15T10:23:26")
    "candidate_required_location": str,  # "Worldwide" | "USA" | "Europe" 등
    "salary": str,                       # "$40,000 - $50,000" 등 (비어있을 수 있음)
    "description": str,                  # HTML
    "tags": list[str]                    # ["python", "senior"] 등
  }
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.models.schemas import (
    SalaryInfo,
    SkillTag,
)
from src.crawlers.parse_batch import process_raw_file
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.normalization.job_taxonomy import extract_remotive_taxonomy_raw
from src.storage.json_writer import (
    _BASE_DATA_DIR,
    iter_collection_json_files,
)

logger = logging.getLogger(__name__)

_RAW_COLLECTION    = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME       = "remotive"

# Remotive category / job_type 매핑은 job_taxonomy_seed + resolve() 로 처리

# Remotive job_type → 원문 고용형태 (정규화는 posting_normalizer)
_JOB_TYPE_RAW: dict[str, str] = {
    "full_time":  "full_time",
    "contract":   "contract",
    "part_time":  "part_time",
    "freelance":  "freelance",
    "internship": "internship",
}

# 급여 통화 기호 → ISO 코드
_CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₩": "KRW",
    "CA$": "CAD",
    "AU$": "AUD",
    "A$":  "AUD",
    "C$":  "CAD",
}

# 연봉 패턴: "$40,000 - $50,000" / "€30k - €40k" / "$100k+"
_SALARY_RANGE_RE = re.compile(
    r"([A-Z]{0,2}[\$€£¥₩])\s*([\d,]+\.?\d*)\s*[kK]?"
    r"(?:\s*[-–~]\s*[A-Z]{0,2}[\$€£¥₩]?\s*([\d,]+\.?\d*)\s*[kK]?)?",
    re.IGNORECASE,
)

# 잘 알려진 기술 스택 키워드 (description 보조 추출용)
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
    original_url  = raw.get("original_url", "")
    raw_text      = raw.get("raw_text", "")

    if not raw_text:
        logger.warning("[remotive] raw_text 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        job = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[remotive] raw_text JSON 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc,
        )
        return None

    try:
        title           = _extract_title(job)
        company_raw     = (job.get("company_name") or "").strip()
        location_raw    = (job.get("candidate_required_location") or "Worldwide").strip()
        description     = _extract_description(job)
        employment_type_raw = _extract_employment_type_raw(job)
        skill_names     = _extract_skill_names(job, description)
        salary_info     = _extract_salary(job)
        posted_at       = _extract_posted_at(job, raw)
        function_raw, category_raw = extract_remotive_taxonomy_raw(job, title)

        first_token = location_raw.split(",")[0].strip()
        country = _normalize_country(first_token)

        extracted = RawExtractedFields(
            title=title,
            company_raw=company_raw,
            description=description,
            location_raw=location_raw,
            employment_type_raw=employment_type_raw,
            career_raw_text=description,
            # work_arrangement: 사이트 성격상 예외 — Remotive는 원격 근무 전용 플랫폼
            work_arrangement_override="REMOTE",
            # education_level / expires_at: Remotive API 미제공·상시채용 (정상 동작)
            education_level=None,
            job_category_raw=category_raw,
            job_function_raw=function_raw,
            skills=skill_names,
            salary=salary_info,
            posted_at=posted_at,
            expires_at=None,
            use_korean_location_parser=False,
            location_country=country,
            location_city=first_token,
            location_region=None,
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[remotive] 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_remotive_parse(
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
        logger.warning("[remotive] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="remotive",
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
        "[remotive] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
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
        log_prefix="[remotive]",
    )


# ---------------------------------------------------------------------------
# 필드별 파서
# ---------------------------------------------------------------------------

def _extract_title(job: dict[str, Any]) -> str:
    return (job.get("title") or "").strip()


def _extract_company(job: dict[str, Any], source_name: str):
    """회사 정보 (테스트·하위 호환)."""
    from src.models.schemas import CompanyInfo
    from src.normalization.company_utils import normalize_company_name
    from src.normalization.alias_resolver import resolve

    raw_name = (job.get("company_name") or "").strip()
    clean = normalize_company_name(raw_name) if raw_name else ""
    canonical = resolve("COMPANY", clean, source_name) if clean else ""
    return CompanyInfo(
        name=canonical or clean or raw_name,
        raw_name=raw_name,
    )


def _extract_location(job: dict[str, Any], source_name: str):
    """위치 (테스트·하위 호환)."""
    from src.models.schemas import LocationInfo
    from src.normalization.alias_resolver import resolve

    raw_location = (job.get("candidate_required_location") or "Worldwide").strip()
    first_token = raw_location.split(",")[0].strip()
    country = _normalize_country(first_token)
    canonical_city = resolve("LOCATION", first_token, source_name)
    return LocationInfo(
        country_name=country,
        city_name=canonical_city,
        raw_text=raw_location,
        region_name=None,
    )


def _normalize_country(raw: str) -> str:
    """공통 지역 표기를 국가명으로 정규화한다."""
    _MAP: dict[str, str] = {
        "worldwide": "Global",
        "anywhere": "Global",
        "remote": "Global",
        "global": "Global",
        "usa": "United States",
        "us": "United States",
        "united states": "United States",
        "uk": "United Kingdom",
        "united kingdom": "United Kingdom",
        "eu": "Europe",
        "europe": "Europe",
        "canada": "Canada",
        "ca": "Canada",
        "australia": "Australia",
        "germany": "Germany",
        "france": "France",
        "brazil": "Brazil",
        "india": "India",
        "korea": "South Korea",
        "south korea": "South Korea",
    }
    return _MAP.get(raw.lower(), raw)


def _extract_description(job: dict[str, Any]) -> str:
    """description 필드(HTML)에서 태그를 제거하고 텍스트만 반환한다."""
    from src.crawlers.common.http_utils import html_description_to_text

    return html_description_to_text(job.get("description") or "")


def _extract_career_level(description: str):
    """경력 수준 (테스트·하위 호환)."""
    from src.taxonomy.career_levels import normalize_career_level

    return normalize_career_level(raw_text=description)


def _extract_employment_type_raw(job: dict[str, Any]) -> str:
    job_type = (job.get("job_type") or "full_time").lower().strip()
    return _JOB_TYPE_RAW.get(job_type, job_type)


def _extract_employment_type(job: dict[str, Any]) -> str:
    """고용형태 (테스트·하위 호환 — 정규화 전)."""
    return _extract_employment_type_raw(job)


def _extract_work_arrangement(job: dict[str, Any]) -> str | None:
    """사이트 성격상 예외: Remotive는 항상 REMOTE."""
    return "REMOTE"


def _extract_skill_names(job: dict[str, Any], description: str) -> list[str]:
    """tags + description 키워드 → skill 이름 목록."""
    from src.normalization.skill_noise_filter import filter_skill_candidates, is_skill_noise

    tags: list[str] = job.get("tags") or []
    skills: list[str] = []
    seen: set[str] = set()

    for raw_text in tags:
        raw_text = raw_text.strip()
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


def _extract_skills(
    job: dict[str, Any],
    description: str,
    source_name: str,
) -> list[SkillTag]:
    """스킬 태그 (테스트·하위 호환)."""
    from src.normalization.alias_resolver import resolve

    names = _extract_skill_names(job, description)
    return [
        SkillTag(raw_text=n, canonical_name=resolve("SKILL", n, source_name))
        for n in names
    ]


def _extract_salary(job: dict[str, Any]) -> SalaryInfo:
    """
    salary 문자열(예: "$40,000 - $50,000", "€50k")에서
    min/max/currency를 정규식으로 파싱한다.
    파싱 실패 시 raw_text만 저장하고 min/max/currency는 None으로 둔다.
    """
    raw_text = (job.get("salary") or "").strip() or None

    if not raw_text:
        return SalaryInfo(raw_text=None)

    match = _SALARY_RANGE_RE.search(raw_text)
    if not match:
        return SalaryInfo(raw_text=raw_text)

    currency_sym = match.group(1) or ""
    currency_code: str | None = None
    for sym, code in _CURRENCY_SYMBOLS.items():
        if currency_sym.endswith(sym) or currency_sym == sym:
            currency_code = code
            break

    def _parse_amount(raw: str | None) -> str | None:
        if not raw:
            return None
        cleaned = raw.replace(",", "")
        try:
            val = float(cleaned)
            # "40k" → 40000 처리 (원문에 k가 있으면 1000 곱하기)
            if re.search(r"[kK]", raw_text):
                val *= 1000
            return str(int(val))
        except ValueError:
            return None

    min_amount = _parse_amount(match.group(2))
    max_amount = _parse_amount(match.group(3))

    # pay_period 추론
    pay_period: str | None = None
    lower = raw_text.lower()
    if any(kw in lower for kw in ["/year", "/yr", "annual", "per year", "yearly"]):
        pay_period = "ANNUAL"
    elif any(kw in lower for kw in ["/month", "/mo", "monthly"]):
        pay_period = "MONTHLY"
    elif any(kw in lower for kw in ["/hour", "/hr", "hourly"]):
        pay_period = "HOURLY"
    elif min_amount and int(min_amount) > 5000:
        pay_period = "ANNUAL"

    return SalaryInfo(
        raw_text=raw_text,
        min_amount=min_amount,
        max_amount=max_amount,
        currency_code=currency_code,
        pay_period=pay_period,
    )


def _extract_posted_at(job: dict[str, Any], raw: dict[str, Any]) -> str:
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
