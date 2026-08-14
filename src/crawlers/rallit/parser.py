"""
랠릿 전용 추출기 / 파서.

원칙
----
- 이 파일은 raw_text(JSON 문자열) 에서 "원문 값을 뽑아내기만" 한다.
- 정규화(normalize_company_name, taxonomy 매핑 등)는 하지 않는다.
- 정규화는 공통 모듈(posting_normalizer.build_job_posting)에서 처리한다.

수집 방식
---------
랠릿은 Next.js 기반이지만 내부 JSON API가 인증 없이 공개 접근 가능하다.
  목록 API : GET https://www.rallit.com/client/api/v1/position
             파라미터: keyword, pageNumber, pageSize
  상세 API : GET https://www.rallit.com/client/api/v1/position/{id}

raw_job_postings 저장 규칙
  raw_html  : "" (API 방식 — HTML 없음)
  raw_text  : 상세 API 응답 JSON 원문을 문자열로 저장
  source_job_id : str(id) (예: "4233")

상세 API 응답 필드 (실측, 2026-07-29)
  id, title, description(HTML), salaryType, minimumSalary,
  startedAt, endedAt, homepage,
  jobs([{code, name}]), jobLevel, jobLevels,
  responsibilities(HTML), basicQualifications(HTML),
  preferredQualifications(HTML), benefits(HTML),
  additionalComments(HTML),
  jobSkillKeywords([str]),
  addressRegion({code, name}), addressMain, addressDetail,
  addressBuildingName, zipCode,
  companyId, companyName, companyDescription(HTML),
  companyTags([str]),
  submitStatus, status({code, name}),
  latitude, longitude, bookmarkCount,
  positionSteps, approvedAt, joinReward, freeQuestions,
  isAlwaysHiring, isBookmarked, isPartner, partnerLogo, content

주요 함수
---------
extract_detail_fields() — 상세 API JSON → 원시 필드 dict (정규화 없음)
parse_raw_posting()     — 단일 raw 문서 → job_postings dict
run_rallit_parse()      — 저장된 raw 파일 일괄 파싱
"""
from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from src.crawlers.parse_batch import process_raw_file
from src.crawlers.rallit.search_queries import get_function_for_job_code
from src.models.schemas import SalaryInfo
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.storage.json_writer import _BASE_DATA_DIR, iter_collection_json_files

logger = logging.getLogger(__name__)

_RAW_COLLECTION = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME = "rallit"

# ---------------------------------------------------------------------------
# HTML → 텍스트 변환 헬퍼
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    """최소한의 HTML 태그 제거기 (BeautifulSoup 없이)."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("p", "li", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._chunks.append("\n")

    def get_text(self) -> str:
        text = "".join(self._chunks)
        # 연속 공백/줄바꿈 정리
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _strip_html(html: str | None) -> str:
    """HTML 문자열에서 태그를 제거하고 텍스트를 반환한다."""
    if not html:
        return ""
    stripper = _HTMLStripper()
    try:
        stripper.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()
    return stripper.get_text()


# ---------------------------------------------------------------------------
# 급여 파싱 헬퍼
# ---------------------------------------------------------------------------

_SALARY_TYPE_MAP = {
    "ANNUAL_SALARY":   "ANNUAL",
    "MONTHLY_SALARY":  "MONTHLY",
    "HOURLY_SALARY":   "HOURLY",
    "UNKNOWN_SALARY":  None,
    "NEGOTIABLE":      None,
}


def _parse_salary(salary_type: str, minimum_salary: Any) -> SalaryInfo:
    """
    랠릿의 salaryType / minimumSalary → SalaryInfo.

    minimumSalary는 만원 단위로 추정. null / "" / 0 이면 비공개 처리.
    """
    pay_period = _SALARY_TYPE_MAP.get(salary_type or "UNKNOWN_SALARY")
    raw_text = salary_type if salary_type and salary_type != "UNKNOWN_SALARY" else None

    min_amount: str | None = None
    if minimum_salary is not None and minimum_salary not in ("", 0, "0"):
        try:
            val = int(str(minimum_salary).replace(",", "").strip())
            if val > 0:
                # 랠릿 minimumSalary가 만원 단위인지 원 단위인지 불분명하므로 원문 보존
                min_amount = str(val)
                if raw_text is None:
                    raw_text = str(minimum_salary)
        except (ValueError, TypeError):
            pass

    return SalaryInfo(
        raw_text=raw_text,
        min_amount=min_amount,
        currency_code="KRW" if min_amount else None,
        pay_period=pay_period,
    )


# ---------------------------------------------------------------------------
# 경력 파싱 헬퍼
# ---------------------------------------------------------------------------

_JOB_LEVEL_TO_YEARS: dict[str, tuple[int | None, int | None]] = {
    "ENTRY":       (0, 0),
    "JUNIOR":      (1, 3),
    "MIDDLE":      (3, 7),
    "SENIOR":      (7, None),
    "LEAD":        (10, None),
    "DIRECTOR":    (10, None),
    "IRRELEVANT":  (None, None),
}


def _parse_career(
    job_level: str,
    job_levels: list[str],
) -> tuple[int | None, int | None, str]:
    """
    jobLevel / jobLevels → (career_min_years, career_max_years, career_raw_text).

    jobLevels 가 여러 값인 경우 범위의 min~max를 사용한다.
    """
    levels = job_levels or ([job_level] if job_level else [])
    levels = [lv for lv in levels if lv and lv != "IRRELEVANT"]

    if not levels:
        return None, None, ""

    mins: list[int] = []
    maxs: list[int] = []
    for lv in levels:
        lo, hi = _JOB_LEVEL_TO_YEARS.get(lv, (None, None))
        if lo is not None:
            mins.append(lo)
        if hi is not None:
            maxs.append(hi)

    career_min = min(mins) if mins else None
    career_max = max(maxs) if maxs else None
    career_raw_text = ", ".join(levels)
    return career_min, career_max, career_raw_text


# ---------------------------------------------------------------------------
# 위치 파싱 헬퍼
# ---------------------------------------------------------------------------

def _parse_location(
    address_main: str | None,
    address_region: dict[str, str] | None,
) -> str:
    """
    addressMain / addressRegion → location_raw 문자열.

    addressMain 이 있으면 우선 사용 (parse_korean_location 에서 처리하기 좋은 형태).
    없으면 addressRegion.name 을 반환한다.
    """
    if address_main and address_main.strip():
        return address_main.strip()
    if isinstance(address_region, dict):
        return address_region.get("name", "")
    return ""


# ---------------------------------------------------------------------------
# 공개 API — 상세 JSON 추출
# ---------------------------------------------------------------------------


def extract_detail_fields(detail_json: dict[str, Any]) -> dict[str, Any]:
    """
    랠릿 상세 API JSON dict 에서 원문 필드를 추출한다.

    Parameters
    ----------
    detail_json : 상세 API 응답의 data 딕셔너리

    Returns
    -------
    dict (모두 원문값 — 정규화 전):
      title, company, description,
      location_raw,
      employment_type_raw,
      career_raw, career_levels,
      salary_type, minimum_salary,
      posted_at, expires_at,
      job_code, job_name,
      skills,
      address_main, address_region,
      company_website, company_tags
    """
    title = (detail_json.get("title") or "").strip()
    company = (detail_json.get("companyName") or "").strip()
    company_website = (detail_json.get("homepage") or "").strip() or None

    # --- 본문 구성 ---
    # 여러 HTML 필드를 결합해 하나의 description 텍스트 생성
    parts = []
    for field_name, label in [
        ("description",             "회사 소개"),
        ("responsibilities",        "주요 업무"),
        ("basicQualifications",     "자격요건"),
        ("preferredQualifications", "우대사항"),
        ("benefits",                "복지 및 혜택"),
        ("additionalComments",      "기타"),
    ]:
        html_content = detail_json.get(field_name) or ""
        text = _strip_html(html_content)
        if text:
            parts.append(f"[{label}]\n{text}")
    description = "\n\n".join(parts)

    # --- 위치 ---
    address_main: str = (detail_json.get("addressMain") or "").strip()
    address_region: dict[str, str] | None = detail_json.get("addressRegion")
    location_raw = _parse_location(address_main, address_region)

    # --- 고용 형태 ---
    # 랠릿 API에는 명시적인 employment_type 필드가 없음. 추후 구조 변경 시 추가.
    employment_type_raw = ""

    # --- 경력 ---
    job_level: str = detail_json.get("jobLevel") or "IRRELEVANT"
    job_levels: list[str] = detail_json.get("jobLevels") or []
    career_raw = job_level
    career_levels = job_levels

    # --- 날짜 ---
    started_at: str = detail_json.get("startedAt") or ""
    ended_at: str = detail_json.get("endedAt") or ""
    approved_at: str = detail_json.get("approvedAt") or ""
    posted_at = _resolve_posted_at(started_at, approved_at)
    # "9999-12-31" = 상시 채용, None으로 처리
    expires_at = _normalize_date(ended_at) if ended_at and ended_at != "9999-12-31" else None

    # --- 직무 코드 ---
    jobs: list[dict[str, str]] = detail_json.get("jobs") or []
    job_code = jobs[0].get("code", "") if jobs else ""
    job_name = jobs[0].get("name", "") if jobs else ""

    # --- 기술스택 ---
    from src.normalization.skill_noise_filter import filter_skill_candidates

    skills: list[str] = filter_skill_candidates(
        detail_json.get("jobSkillKeywords") or []
    )

    return {
        "title": title,
        "company": company,
        "description": description,
        "location_raw": location_raw,
        "employment_type_raw": employment_type_raw,
        "career_raw": career_raw,
        "career_levels": career_levels,
        "salary_type": detail_json.get("salaryType") or "",
        "minimum_salary": detail_json.get("minimumSalary"),
        "posted_at": posted_at,
        "expires_at": expires_at,
        "job_code": job_code,
        "job_name": job_name,
        "skills": skills,
        "address_main": address_main,
        "address_region": address_region,
        "company_website": company_website,
        "company_tags": detail_json.get("companyTags") or [],
    }


# ---------------------------------------------------------------------------
# 공개 API — raw → job_postings 변환 (파싱 파이프라인)
# ---------------------------------------------------------------------------


def parse_raw_posting(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    단일 raw_job_postings 문서를 job_postings 구조로 파싱한다.

    Returns
    -------
    job_postings dict, 또는 파싱 실패 시 None
    """
    source_job_id = raw.get("source_job_id", "")
    source_name = raw.get("source_name", "")
    raw_text_str = raw.get("raw_text", "")

    if not raw_text_str:
        logger.warning("[rallit] raw_text 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        detail_json: dict[str, Any] = json.loads(raw_text_str)
    except json.JSONDecodeError as exc:
        logger.error(
            "[rallit] raw_text JSON 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc,
        )
        return None

    try:
        fields = extract_detail_fields(detail_json)
    except Exception as exc:
        logger.error(
            "[rallit] extract_detail_fields 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None

    if not fields.get("title"):
        logger.warning(
            "[rallit] 제목 추출 실패 (%s/%s) — 파싱 건너뜀",
            source_name, source_job_id,
        )
        return None

    try:
        # --- 경력 파싱 ---
        career_min, career_max, career_raw_text = _parse_career(
            fields["career_raw"],
            fields["career_levels"],
        )

        # --- 급여 ---
        salary = _parse_salary(fields["salary_type"], fields["minimum_salary"])

        # --- job_function: jobs.code → taxonomy function name ---
        job_code = fields.get("job_code", "")
        job_function_raw = get_function_for_job_code(job_code) if job_code else ""

        work_arrangement_text = _build_work_arrangement_text(
            fields.get("company_tags") or [],
            fields["description"],
        )

        extracted = RawExtractedFields(
            title=fields["title"],
            company_raw=fields["company"],
            description=fields["description"],
            location_raw=fields["location_raw"],
            employment_type_raw=fields["employment_type_raw"],
            career_raw_text=career_raw_text,
            career_min_years=career_min,
            career_max_years=career_max,
            work_arrangement_text=work_arrangement_text,
            job_function_raw=job_function_raw,
            skills=fields["skills"],
            salary=salary,
            posted_at=fields.get("posted_at") or None,
            expires_at=fields.get("expires_at"),
            company_website=fields.get("company_website"),
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[rallit] build_job_posting 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# 공개 API — 저장된 raw 파일 일괄 파싱
# ---------------------------------------------------------------------------


def run_rallit_parse(
    crawl_date: str | None = None,
    base_dir: str | None = None,
    reparse: bool = False,
) -> None:
    """
    저장된 raw_job_postings 문서를 일괄 파싱한다.

    Parameters
    ----------
    crawl_date : 특정 날짜 폴더만 처리. None 이면 전체.
    base_dir   : data 루트 경로. None 이면 프로젝트 기본값.
    reparse    : True 이면 parse_status='PARSED' 인 것도 재파싱.
    """
    _data_root = Path(base_dir) if base_dir else _BASE_DATA_DIR
    raw_root = _data_root / _RAW_COLLECTION

    if not raw_root.exists():
        logger.warning("[rallit] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="rallit",
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
        "[rallit] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
        total_parsed,
        total_failed,
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
    return process_raw_file(
        json_file=json_file,
        date_label=date_label,
        base_dir=base_dir,
        parse_fn=parse_raw_posting,
        source_name=_SOURCE_NAME if reparse else None,
        reparse=reparse,
        log_prefix="[rallit]",
    )


# ---------------------------------------------------------------------------
# 내부: 날짜 정규화 헬퍼
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_PLACEHOLDER_START_DATES = frozenset({"1970-01-01"})


def _normalize_date(raw: str) -> str:
    """
    날짜 원문에서 YYYY-MM-DD 형식을 추출한다.
    파싱 실패 시 빈 문자열 반환.
    """
    if not raw:
        return ""
    m = _DATE_RE.search(raw)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        return f"{y}-{mo}-{d}"
    return ""


def _resolve_posted_at(started_at: str, approved_at: str) -> str | None:
    """
    posted_at 결정.

    startedAt 이 1970-01-01 등 placeholder 이면 approvedAt(승인일)을 사용한다.
    """
    posted = _normalize_date(started_at)
    if posted and posted not in _PLACEHOLDER_START_DATES:
        return posted
    approved = _normalize_date(approved_at)
    return approved or None


def _build_work_arrangement_text(company_tags: list[str], description: str) -> str:
    """companyTags(재택 근무 등) + 본문을 근무 형태 탐지 입력으로 합친다."""
    tag_text = " ".join(t.strip() for t in company_tags if t and str(t).strip())
    if tag_text and description:
        return f"{tag_text}\n{description}"
    return tag_text or description
