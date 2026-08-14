"""
원티드 raw_job_postings (parse_status: PENDING) → job_postings 파싱.

주요 함수:
  parse_raw_posting()   — 단일 RawJobPosting dict → JobPosting dict 변환
  run_wanted_parse()    — 저장된 raw 파일을 일괄 파싱하는 오케스트레이터

파싱 전략:
  - raw_text 필드에 저장된 상세 API 응답 JSON 원문을 파싱한다.
  - alias_resolver로 회사명·지역명 표준화
  - 파싱 성공 → parse_status: PARSED, parsed_job_posting_id 연결
  - 파싱 실패 → parse_status: FAILED (부분 실패 허용)

원티드 상세 API 응답 구조 (2026-07-27 확인):
  {
    "job": {
      "id": int,
      "position": str,                    # 공고 제목
      "status": "active" | "closed",
      "company": {
        "id": int,
        "name": str,
        "industry_name": str,
      },
      "address": {
        "location": str,                  # 시/도 (예: "서울")
        "district": str,                  # 구 (예: "강남구")
        "country": str,                   # 국가명 (예: "한국")
        "full_location": str,             # 상세 주소
        "location_key": str,              # 정규화된 지역 키 (예: "seoul")
        "district_key": str,
      },
      "annual_from": int | null,          # 최소 경력 연수
      "annual_to":   int | null,          # 최대 경력 연수
      "due_time": str | null,             # 마감일 (ISO 형식 또는 null)
      "skill_tags": [{"id": int, "title": str}, ...],
      "category_tags": [{"parent_id": int, "id": int}, ...],
      "company_tags": [{"id": int, "title": str, "kind_title": str}, ...],
      "detail": {
        "intro": str,
        "main_tasks": str,
        "requirements": str,
        "preferred_points": str,
        "benefits": str,
      },
      "logo_img": {"origin": str, "thumb": str},
      "title_img": {"origin": str, "thumb": str},
      "reward": {...},
      "like_count": int,
      "is_like": bool,
      ...
    },
    "application": null | {...}
  }
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
from src.normalization.job_taxonomy import extract_wanted_taxonomy_raw
from src.normalization.work_arrangement import detect_work_arrangement
from src.storage.json_writer import (
    _BASE_DATA_DIR,
    iter_collection_json_files,
)

logger = logging.getLogger(__name__)

_RAW_COLLECTION    = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME       = "wanted"

# 원티드 industry_name → 표준 job_category 매핑은 job_taxonomy_seed + resolve() 로 처리

# 공고 직무를 나타내는 skill_tag title → 표준 직무 카테고리 힌트 (보조용)
_KNOWN_TECH_SKILLS = {
    "python", "java", "javascript", "typescript", "react", "vue", "angular",
    "node.js", "spring", "django", "flask", "go", "golang", "kotlin", "swift",
    "c++", "c#", "ruby", "php", "rust", "scala",
    "aws", "gcp", "azure", "kubernetes", "docker", "terraform",
    "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    "pytorch", "tensorflow", "sklearn", "scikit-learn",
    "spark", "hadoop", "kafka", "airflow",
    "git", "linux", "nginx",
}


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
        logger.warning("[wanted] raw_text 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        api_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "[wanted] raw_text JSON 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc,
        )
        return None

    job = api_data.get("job", {})
    if not job:
        logger.warning("[wanted] 'job' 키 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        title          = _extract_title(job)
        company        = job.get("company") or {}
        company_raw    = (company.get("name") or "").strip()
        industry       = (company.get("industry_name") or "").strip() or None
        address        = job.get("address") or {}
        location_raw   = (address.get("full_location") or "").strip()
        if not location_raw:
            location_raw = " ".join(
                p for p in [
                    address.get("country", ""),
                    address.get("location", ""),
                    address.get("district", ""),
                ] if p
            ).strip()
        description    = _extract_description(job)
        employment_type_raw = _extract_employment_type_raw(job)
        skills         = _extract_skill_names(job, description)
        salary_info    = _extract_salary(job)
        posted_at      = _extract_posted_at(raw)
        # expires_at: 원티드 API due_time — 상시채용 공고는 null (정상 동작)
        expires_at     = _extract_expires_at(job)
        function_raw, category_raw = extract_wanted_taxonomy_raw(job)

        annual_from = job.get("annual_from")
        annual_to   = job.get("annual_to")

        extracted = RawExtractedFields(
            title=title,
            company_raw=company_raw,
            description=description,
            location_raw=location_raw,
            employment_type_raw=employment_type_raw,
            career_min_years=int(annual_from) if annual_from is not None else None,
            career_max_years=int(annual_to) if annual_to is not None else None,
            work_arrangement_text=description,
            # education_level: 원티드 API가 학력 정보 미제공 (정상 동작)
            education_level=None,
            job_category_raw=category_raw,
            job_function_raw=function_raw,
            skills=skills,
            salary=salary_info,
            posted_at=posted_at,
            expires_at=expires_at,
            company_industry=industry,
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[wanted] 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_wanted_parse(
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
        logger.warning("[wanted] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="wanted",
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
        "[wanted] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
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
        log_prefix="[wanted]",
    )


# ---------------------------------------------------------------------------
# 필드별 파서
# ---------------------------------------------------------------------------

def _extract_title(job: dict[str, Any]) -> str:
    return (job.get("position") or "").strip()


def _extract_company(job: dict[str, Any], source_name: str):
    """회사 정보 (테스트·하위 호환)."""
    from src.models.schemas import CompanyInfo
    from src.normalization.company_utils import normalize_company_name
    from src.normalization.alias_resolver import resolve

    company = job.get("company") or {}
    raw_name = (company.get("name") or "").strip()
    industry = (company.get("industry_name") or "").strip()
    clean = normalize_company_name(raw_name) if raw_name else ""
    canonical = resolve("COMPANY", clean, source_name) if clean else ""
    return CompanyInfo(
        name=canonical or clean or raw_name,
        raw_name=raw_name,
        industry_name=industry or None,
    )


def _extract_location(job: dict[str, Any], source_name: str):
    """위치 (테스트·하위 호환)."""
    from src.models.schemas import LocationInfo
    from src.normalization.location_utils import parse_korean_location
    from src.normalization.alias_resolver import resolve

    address = job.get("address") or {}
    full_loc = (address.get("full_location") or "").strip()
    if not full_loc:
        full_loc = " ".join(
            p for p in [
                address.get("country", ""),
                address.get("location", ""),
                address.get("district", ""),
            ] if p
        ).strip()
    city, region, country = parse_korean_location(full_loc)
    city_canonical = resolve("LOCATION", city, source_name) if city else ""
    return LocationInfo(
        country_name=country,
        region_name=region,
        city_name=city_canonical or city,
        raw_text=full_loc,
    )


def _extract_description(job: dict[str, Any]) -> str:
    detail = job.get("detail") or {}
    parts = [
        detail.get("intro") or "",
        detail.get("main_tasks") or "",
        detail.get("requirements") or "",
        detail.get("preferred_points") or "",
        detail.get("benefits") or "",
    ]
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _extract_career_level(job: dict[str, Any]):
    """경력 수준 (테스트·하위 호환)."""
    from src.taxonomy.career_levels import normalize_career_level

    annual_from = job.get("annual_from")
    annual_to = job.get("annual_to")
    return normalize_career_level(
        min_years=int(annual_from) if annual_from is not None else None,
        max_years=int(annual_to) if annual_to is not None else None,
    )


def _extract_employment_type_raw(job: dict[str, Any]) -> str:
    """원티드 API — company_tags에서 고용형태 힌트 (원문)."""
    for tag in job.get("company_tags") or []:
        title = (tag.get("title") or "").lower()
        if "인턴" in title or "intern" in title:
            return "인턴십"
        if "파견" in title or "계약" in title:
            return "계약직"
    return ""


def _extract_employment_type(job: dict[str, Any]) -> str:
    raw = _extract_employment_type_raw(job)
    return raw or "정규직"


def _extract_work_arrangement(description: str) -> str | None:
    return detect_work_arrangement(description)


def _extract_skill_names(job: dict[str, Any], description: str) -> list[str]:
    """skill_tags + description 키워드 → skill 이름 목록."""
    from src.normalization.skill_noise_filter import filter_skill_candidates, is_skill_noise

    skill_tags_raw = job.get("skill_tags") or []
    skills: list[str] = []
    seen: set[str] = set()

    for tag in skill_tags_raw:
        raw_text = (tag.get("title") or "").strip()
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
    # 원티드 API는 explicit 급여 필드를 제공하지 않음
    # reward 필드는 채용 보상금(referral reward)이므로 급여와 무관
    return SalaryInfo(raw_text=None)


def _extract_posted_at(raw: dict[str, Any]) -> str:
    collected_at = raw.get("collected_at", "")
    if collected_at:
        try:
            dt = datetime.fromisoformat(collected_at)
            return dt.date().isoformat()
        except ValueError:
            pass
    return date.today().isoformat()


def _extract_expires_at(job: dict[str, Any]) -> str | None:
    due_time = job.get("due_time")
    if not due_time:
        return None
    try:
        dt = datetime.fromisoformat(str(due_time).replace("Z", "+00:00"))
        return dt.isoformat()
    except (ValueError, TypeError):
        return str(due_time)
