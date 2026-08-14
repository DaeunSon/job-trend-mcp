"""
점핏 raw_job_postings (parse_status: PENDING) → job_postings 파싱.

주요 함수:
  parse_raw_posting()   — 단일 RawJobPosting dict → JobPosting dict 변환
  run_jumpit_parse()    — 저장된 raw 파일을 일괄 파싱하는 오케스트레이터

파싱 전략:
  - raw_text 필드에 저장된 상세 API 응답 JSON 원문을 파싱한다.
  - alias_resolver로 회사명·지역명 표준화
  - 파싱 성공 → parse_status: PARSED, parsed_job_posting_id 연결
  - 파싱 실패 → parse_status: FAILED (부분 실패 허용)

점핏 상세 API 응답 구조 (https://jumpit-api.saramin.co.kr/api/position/{id}, 2026-07-28 확인):
  result dict (raw_text에 저장됨):
  {
    "id": int,
    "title": str,                       # 공고 제목
    "companyName": str,                 # 회사명
    "companyId": int,
    "companyHashId": str,               # Base64 인코딩된 회사 ID
    "companyLogo": str,                 # 회사 로고 URL
    "repImage": str,                    # 대표 이미지 URL
    "images": [{"sort": int, "imageUrl": str}, ...],
    "tags": [{"id": int, "name": str, "imageUrl": str}, ...],   # 기술스택
    "mainTask": str,                    # 주요업무
    "qualification": str,              # 자격요건
    "preferredPoint": str,             # 우대사항
    "benefit": str,                    # 복지 및 혜택
    "applicationProcess": str,         # 채용절차 (스키마 없음, 무시)
    "employment": bool,                # 신입 여부 (true=신입 가능)
    "minCareer": int | null,           # 최소 경력 연수
    "maxCareer": int | null,           # 최대 경력 연수
    "location": str,                   # 근무지역 전체 주소
    "locationCode": int,               # 지역 코드
    "openedAt": str | null,            # 공고 등록일 (ISO format 또는 "YYYY-MM-DD HH:MM:SS")
    "closedAt": str | null,            # 마감일 (ISO format)
    "companyWebsite": str | null,      # 회사 홈페이지
    "salary": int | null,              # 연봉 (만원 단위, 0이면 미공개)
    "education": str | null,           # 학력 요건 (예: "무관", "대학교(4년)")
    "categories": [{"id": int, "name": str}, ...],   # 직무 카테고리
    "companyFoundedAt": str | null,    # 회사 설립 정보 (예: "1997년 7월 설립")
    "closed": bool,                    # 마감 여부
    "scrap": bool,                     # 스크랩 여부 (무시)
    "reward": bool,                    # 취업축하금 여부 (스키마 없음, 무시)
    ...
  }

스키마에 없는 필드는 저장하지 않는다:
  - applicationProcess (채용절차)
  - reward (취업축하금)
  - scrap, likeCount, companyHashId 등
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

from src.models.schemas import (
    SalaryInfo,
    SkillTag,
)
from src.crawlers.parse_batch import process_raw_file
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.normalization.job_taxonomy import extract_jumpit_taxonomy_raw
from src.normalization.work_arrangement import detect_work_arrangement
from src.storage.json_writer import (
    _BASE_DATA_DIR,
    iter_collection_json_files,
)

logger = logging.getLogger(__name__)

_RAW_COLLECTION    = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME       = "jumpit"


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
        logger.warning("[jumpit] raw_text 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[jumpit] raw_text JSON 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc,
        )
        return None

    if not isinstance(data, dict):
        logger.warning(
            "[jumpit] raw_text가 dict가 아님 (%s/%s): %s",
            source_name, source_job_id, type(data),
        )
        return None

    try:
        title             = _extract_title(data)
        company_raw       = (data.get("companyName") or "").strip()
        location_raw      = (data.get("location") or "").strip()
        description       = _extract_description(data)
        career_min        = data.get("minCareer")
        career_max        = data.get("maxCareer")
        employment_type_raw = _extract_employment_type_raw(data)
        education_level   = _extract_education(data)
        skills            = _extract_skills(data)
        salary_info       = _extract_salary(data)
        posted_at         = _extract_posted_at(data, raw)
        expires_at        = _extract_expires_at(data)
        function_raw, category_raw = extract_jumpit_taxonomy_raw(data)
        website           = (data.get("companyUrl") or data.get("companyWebsite") or None)
        if website:
            website = website.strip() or None

        extracted = RawExtractedFields(
            title=title,
            company_raw=company_raw,
            description=description,
            location_raw=location_raw,
            employment_type_raw=employment_type_raw,
            career_min_years=int(career_min) if career_min is not None else None,
            career_max_years=int(career_max) if career_max is not None else None,
            career_raw_text=_career_hint_text(data),
            work_arrangement_text=description,
            education_level=education_level,
            job_category_raw=category_raw,
            job_function_raw=function_raw,
            skills=skills,
            salary=salary_info,
            posted_at=posted_at,
            expires_at=expires_at,
            company_website=website,
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[jumpit] 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_jumpit_parse(
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
        logger.warning("[jumpit] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="jumpit",
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
        "[jumpit] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
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
        log_prefix="[jumpit]",
    )


# ---------------------------------------------------------------------------
# 필드별 파서
# ---------------------------------------------------------------------------

def _extract_title(data: dict[str, Any]) -> str:
    return (data.get("title") or "").strip()


def _extract_company(
    data: dict[str, Any],
    source_name: str,
):
    """회사 정보 추출 (테스트·하위 호환 — 정규화는 posting_normalizer)."""
    from src.models.schemas import CompanyInfo
    from src.normalization.company_utils import normalize_company_name
    from src.normalization.alias_resolver import resolve

    raw_name = (data.get("companyName") or "").strip()
    website = (data.get("companyWebsite") or None)
    if website:
        website = website.strip() or None
    clean = normalize_company_name(raw_name) if raw_name else ""
    canonical = resolve("COMPANY", clean, source_name) if clean else ""
    return CompanyInfo(
        name=canonical or clean or raw_name,
        raw_name=raw_name,
        website_url=website,
    )


def _extract_location(data: dict[str, Any], source_name: str):
    """위치 추출 (테스트·하위 호환 — 정규화는 posting_normalizer)."""
    from src.models.schemas import LocationInfo
    from src.normalization.location_utils import parse_korean_location
    from src.normalization.alias_resolver import resolve

    full_address = (data.get("location") or "").strip()
    city, region, country = parse_korean_location(full_address)
    city_canonical = resolve("LOCATION", city, source_name) if city else ""
    return LocationInfo(
        country_name=country,
        region_name=region,
        city_name=city_canonical or city,
        raw_text=full_address,
    )


def _first_str(data: dict[str, Any], *keys: str) -> str:
    """여러 후보 키 중 첫 번째 비어 있지 않은 문자열 값."""
    for key in keys:
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _career_hint_text(data: dict[str, Any]) -> str:
    """API 숫자 경력 외 텍스트 힌트 (newcomer/employment=true → 신입 가능)."""
    is_newcomer = data.get("newcomer") is True or data.get("employment") is True
    if is_newcomer and data.get("minCareer") is None:
        return "신입"
    return ""


def _extract_career_level(data: dict[str, Any]):
    """경력 수준 (테스트·하위 호환)."""
    from src.models.schemas import CareerLevel
    from src.taxonomy.career_levels import normalize_career_level

    min_c = data.get("minCareer")
    max_c = data.get("maxCareer")
    return normalize_career_level(
        raw_text=_career_hint_text(data),
        min_years=int(min_c) if min_c is not None else None,
        max_years=int(max_c) if max_c is not None else None,
    )


def _extract_employment_type_raw(data: dict[str, Any]) -> str:
    """점핏 API — description에서 고용형태 힌트 추출 (원문)."""
    texts = " ".join([
        _first_str(data, "responsibility", "mainTask"),
        _first_str(data, "qualifications", "qualification"),
        _first_str(data, "welfares", "benefit"),
    ]).lower()

    if "인턴" in texts or "intern" in texts:
        return "인턴십"
    if "계약직" in texts or "프리랜서" in texts or "freelance" in texts:
        return "계약직"
    if "파트타임" in texts or "part-time" in texts:
        return "파트타임"
    if "정규직" in texts or "full-time" in texts:
        return "정규직"
    return ""


def _extract_employment_type(data: dict[str, Any]) -> str:
    """고용형태 (테스트·하위 호환 — 정규화 전 원문)."""
    raw = _extract_employment_type_raw(data)
    return raw or "정규직"


def _extract_work_arrangement(description: str) -> str | None:
    """근무 형태 (공통 정책 위임)."""
    return detect_work_arrangement(description)


def _extract_skills(data: dict[str, Any], source_name: str = "") -> list[str]:
    """API techStacks → skill 이름 목록 (정규화는 posting_normalizer).

    2026-07 API 변경: tags 는 회사 정보 태그, techStacks 가 실제 기술스택.
    """
    from src.normalization.skill_noise_filter import filter_skill_candidates

    tech_stacks = data.get("techStacks") or []
    if tech_stacks:
        skills: list[str] = []
        seen: set[str] = set()
        for item in tech_stacks:
            name = (item.get("stack") or item.get("name") or "").strip()
            if name and name not in seen:
                seen.add(name)
                skills.append(name)
        return filter_skill_candidates(skills)

    # 구 API: tags 가 기술스택
    tags_raw = data.get("tags") or []
    skills = []
    seen: set[str] = set()
    for tag in tags_raw:
        name = (tag.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            skills.append(name)
    return filter_skill_candidates(skills)


def _extract_description(data: dict[str, Any]) -> str:
    """주요업무 + 자격요건 + 우대사항 + 복지를 합쳐 description을 생성한다."""
    sections = [
        ("주요업무", _first_str(data, "responsibility", "mainTask")),
        ("자격요건", _first_str(data, "qualifications", "qualification")),
        ("우대사항", _first_str(data, "preferredRequirements", "preferredPoint")),
        ("복지 및 혜택", _first_str(data, "welfares", "benefit")),
    ]
    parts: list[str] = []
    for label, text in sections:
        if text:
            parts.append(f"[{label}]\n{text}")
    return "\n\n".join(parts)


def _extract_education(data: dict[str, Any]) -> str | None:
    edu_name = (data.get("educationName") or "").strip()
    if edu_name:
        return edu_name

    edu = data.get("education")
    if edu is None or edu == "":
        return None
    if isinstance(edu, str):
        return edu.strip() or None
    if isinstance(edu, int) and edu == 0:
        return "무관"
    return None



def _extract_salary(data: dict[str, Any]) -> SalaryInfo:
    salary_val = data.get("salary")
    if salary_val and isinstance(salary_val, int) and salary_val > 0:
        # 점핏 salary는 만원 단위로 추정 (예: 500 → 5,000만원)
        raw_text = f"{salary_val}만원"
        return SalaryInfo(
            raw_text=raw_text,
            currency_code="KRW",
            pay_period="ANNUAL",
        )
    return SalaryInfo(raw_text=None)


def _extract_posted_at(data: dict[str, Any], raw: dict[str, Any]) -> str:
    opened_at = data.get("publishedAt") or data.get("openedAt")
    if opened_at:
        try:
            dt = datetime.fromisoformat(
                str(opened_at).replace("Z", "+00:00").replace(" ", "T")
            )
            return dt.date().isoformat()
        except (ValueError, TypeError):
            pass

    # fallback: raw 문서의 collected_at
    collected_at = raw.get("collected_at", "")
    if collected_at:
        try:
            dt = datetime.fromisoformat(collected_at)
            return dt.date().isoformat()
        except ValueError:
            pass
    return date.today().isoformat()


def _extract_expires_at(data: dict[str, Any]) -> str | None:
    closed_at = data.get("closedAt")
    if not closed_at:
        return None
    try:
        dt = datetime.fromisoformat(
            str(closed_at).replace("Z", "+00:00").replace(" ", "T")
        )
        return dt.isoformat()
    except (ValueError, TypeError):
        return str(closed_at)
