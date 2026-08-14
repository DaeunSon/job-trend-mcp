"""
Arbeitnow raw_job_postings (parse_status: PENDING) → job_postings 파싱.

주요 함수:
  parse_raw_posting()     — 단일 RawJobPosting dict → JobPosting dict 변환
  run_arbeitnow_parse()   — 저장된 raw 파일을 일괄 파싱하는 오케스트레이터

파싱 전략:
  - raw_text 필드에 저장된 Arbeitnow API 응답 JSON 원문을 파싱한다.
  - description 필드는 HTML 엔티티 디코딩 후 BeautifulSoup으로 태그 제거
  - alias_resolver / job_taxonomy 공통 경로로 회사명·지역·직무·직군 표준화
  - build_job_posting()으로 최종 문서 생성
  - 파싱 성공 → parse_status: PARSED, parsed_job_posting_id 연결
  - 파싱 실패 → parse_status: FAILED (부분 실패 허용)

Arbeitnow API 응답 필드 (2026-07-30 실제 호출 확인):
  {
    "slug": str,
    "company_name": str,
    "title": str,
    "description": str,       # HTML 엔티티 인코딩된 HTML
    "remote": bool,
    "url": str,
    "tags": list[str],
    "job_types": list[str],   # 고용형태·경력 혼재
    "location": str,
    "created_at": int         # Unix timestamp (초)
  }

이용약관 요약:
  - arbeitnow.com 백링크 의무 (source_name·original_url로 충족)
  - 제3자 채용 사이트 재게시 금지
  - API as-is — 필드 누락·형식 이상을 관대하게 처리
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
from src.normalization.job_taxonomy import extract_arbeitnow_taxonomy_raw
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.storage.json_writer import _BASE_DATA_DIR, iter_collection_json_files

logger = logging.getLogger(__name__)

_RAW_COLLECTION    = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME       = "arbeitnow"

_CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₩": "KRW",
}

_SALARY_RANGE_RE = re.compile(
    r"([A-Z]{0,2}[\$€£¥₩])\s*([\d,]+\.?\d*)\s*[kK]?"
    r"(?:\s*[-–~]\s*[A-Z]{0,2}[\$€£¥₩]?\s*([\d,]+\.?\d*)\s*[kK]?)?",
    re.IGNORECASE,
)

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

# job_types 에서 고용형태를 고를 때 사용하는 힌트는 _extract_employment_type_raw 내부 로직 참고


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
        logger.warning("[arbeitnow] raw_text 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        job = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[arbeitnow] raw_text JSON 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc,
        )
        return None

    if not isinstance(job, dict):
        logger.warning(
            "[arbeitnow] raw_text 가 dict가 아님 (%s/%s): %s",
            source_name, source_job_id, type(job),
        )
        return None

    try:
        title               = _extract_title(job)
        company_raw         = _extract_company_name(job)
        location_raw        = _extract_location_raw(job)
        description         = _extract_description(job)
        employment_type_raw = _extract_employment_type_raw(job)
        career_raw_text     = _extract_career_raw_text(job, description)
        skill_names         = _extract_skill_names(job, description)
        posted_at           = _extract_posted_at(job, raw)
        salary_info         = _extract_salary(description)
        function_raw, category_raw = extract_arbeitnow_taxonomy_raw(
            job, title, description,
        )

        is_remote = bool(job.get("remote"))
        city = location_raw.split(",")[0].strip() if location_raw else ""
        if city.lower() in ("remote", "worldwide", "anywhere", "global"):
            city = ""
        country = _normalize_country(location_raw or ("Remote" if is_remote else ""))

        work_arrangement_override = "REMOTE" if is_remote else None
        work_arrangement_text = ""
        if not is_remote:
            work_arrangement_text = f"{location_raw} {description[:200]}"

        extracted = RawExtractedFields(
            title=title,
            company_raw=company_raw,
            description=description,
            location_raw=location_raw or ("Remote" if is_remote else ""),
            employment_type_raw=employment_type_raw,
            career_raw_text=career_raw_text,
            work_arrangement_text=work_arrangement_text,
            work_arrangement_override=work_arrangement_override,
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
            "[arbeitnow] 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_arbeitnow_parse(
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
        logger.warning("[arbeitnow] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="arbeitnow",
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
        "[arbeitnow] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
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
        log_prefix="[arbeitnow]",
    )


# ---------------------------------------------------------------------------
# 필드별 파서
# ---------------------------------------------------------------------------

def _extract_title(job: dict[str, Any]) -> str:
    return (job.get("title") or "").strip()


def _extract_company_name(job: dict[str, Any]) -> str:
    return (job.get("company_name") or "").strip()


def _extract_location_raw(job: dict[str, Any]) -> str:
    return (job.get("location") or "").strip()


def _extract_description(job: dict[str, Any]) -> str:
    """
    description 필드에서 HTML 엔티티를 디코딩한 뒤 태그를 제거하고 텍스트만 반환한다.
    Arbeitnow는 엔티티 인코딩(&lt;div&gt;...)된 HTML을 내려주는 경우가 많다.
    """
    from src.crawlers.common.http_utils import html_description_to_text

    return html_description_to_text(
        job.get("description") or "",
        unescape_entities=True,
    )


def _extract_employment_type_raw(job: dict[str, Any]) -> str:
    """
    job_types 목록에서 고용형태에 가까운 항목을 골라 원문 그대로 반환한다.
    정규화는 posting_normalizer → normalize_employment_type 에 위임한다.
    """
    job_types: list[str] = [
        str(jt).strip() for jt in (job.get("job_types") or []) if jt
    ]
    if not job_types:
        return ""

    for jt in job_types:
        lower = jt.lower().replace("-", " ").replace("_", " ")
        compact = lower.replace(" ", "")
        if "freelance" in compact:
            return "freelance"
        if "internship" in compact or compact == "intern" or "intern " in lower:
            return "internship"
        if "contract" in compact:
            return "contract"
        if "parttime" in compact or "teilzeit" in compact:
            return "part time"
        if "fulltime" in compact or "vollzeit" in compact or "permanent" in compact:
            return "full time"

    return " ".join(job_types)


def _extract_career_raw_text(job: dict[str, Any], description: str) -> str:
    """job_types(경력 힌트) + description 일부를 career_level 추론에 사용한다."""
    job_types = " ".join(
        str(jt).strip() for jt in (job.get("job_types") or []) if jt
    )
    return f"{job_types} {description[:300]}".strip()


def _extract_skill_names(job: dict[str, Any], description: str) -> list[str]:
    """tags + description 기술 키워드 → skill 이름 목록."""
    from src.normalization.skill_noise_filter import filter_skill_candidates, is_skill_noise

    tags: list[str] = job.get("tags") or []
    skills: list[str] = []
    seen: set[str] = set()

    for raw_text in tags:
        raw_text = str(raw_text).strip()
        if not raw_text or raw_text.lower() == "remote":
            continue
        if is_skill_noise(raw_text):
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
    """created_at(Unix timestamp) → ISO date 문자열."""
    created_at = job.get("created_at")
    if created_at is not None:
        try:
            ts = int(created_at)
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError, OverflowError):
            logger.debug("[arbeitnow] created_at 파싱 실패: %r", created_at)

    collected_at = raw.get("collected_at", "")
    if collected_at:
        try:
            dt = datetime.fromisoformat(collected_at)
            return dt.date().isoformat()
        except ValueError:
            pass

    return date.today().isoformat()


def _extract_salary(description: str) -> SalaryInfo:
    """본문에서 급여 표기를 추출한다. 없으면 빈 SalaryInfo."""
    if not description:
        return SalaryInfo()

    match = _SALARY_RANGE_RE.search(description)
    if not match:
        return SalaryInfo()

    currency_sym = match.group(1) or ""
    currency_code: str | None = None
    for sym, code in _CURRENCY_SYMBOLS.items():
        if currency_sym.endswith(sym) or currency_sym == sym:
            currency_code = code
            break

    def _parse_amount(raw_amt: str | None) -> str | None:
        if not raw_amt:
            return None
        cleaned = raw_amt.replace(",", "")
        try:
            val = float(cleaned)
            if re.search(re.escape(raw_amt.strip()) + r"\s*[kK]", description):
                val *= 1000
            return str(int(val))
        except ValueError:
            return None

    min_amount = _parse_amount(match.group(2))
    max_amount = _parse_amount(match.group(3))
    raw_text = match.group(0)

    pay_period: str | None = None
    lower = description.lower()
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


def _normalize_country(raw: str) -> str:
    """도시/지역 표기를 국가명으로 정규화한다. 유럽 중심."""
    text = (raw or "").strip()
    if not text:
        return ""

    first = text.split(",")[0].strip()
    lower = first.lower()

    _MAP: dict[str, str] = {
        "worldwide": "Global",
        "anywhere": "Global",
        "remote": "Global",
        "global": "Global",
        "europe": "Europe",
        "eu": "Europe",
        "emea": "Europe",
        "germany": "Germany",
        "deutschland": "Germany",
        "berlin": "Germany",
        "munich": "Germany",
        "münchen": "Germany",
        "hamburg": "Germany",
        "frankfurt": "Germany",
        "cologne": "Germany",
        "köln": "Germany",
        "stuttgart": "Germany",
        "düsseldorf": "Germany",
        "dusseldorf": "Germany",
        "austria": "Austria",
        "österreich": "Austria",
        "vienna": "Austria",
        "wien": "Austria",
        "switzerland": "Switzerland",
        "schweiz": "Switzerland",
        "zurich": "Switzerland",
        "zürich": "Switzerland",
        "netherlands": "Netherlands",
        "amsterdam": "Netherlands",
        "france": "France",
        "paris": "France",
        "uk": "United Kingdom",
        "united kingdom": "United Kingdom",
        "london": "United Kingdom",
        "spain": "Spain",
        "madrid": "Spain",
        "barcelona": "Spain",
        "portugal": "Portugal",
        "lisbon": "Portugal",
        "lisboa": "Portugal",
        "italy": "Italy",
        "milan": "Italy",
        "roma": "Italy",
        "rome": "Italy",
        "poland": "Poland",
        "warsaw": "Poland",
        "ireland": "Ireland",
        "dublin": "Ireland",
        "belgium": "Belgium",
        "brussels": "Belgium",
        "sweden": "Sweden",
        "stockholm": "Sweden",
        "denmark": "Denmark",
        "copenhagen": "Denmark",
        "norway": "Norway",
        "oslo": "Norway",
        "finland": "Finland",
        "helsinki": "Finland",
        "czech": "Czech Republic",
        "prague": "Czech Republic",
        "usa": "United States",
        "united states": "United States",
        "canada": "Canada",
    }
    return _MAP.get(lower, first)
