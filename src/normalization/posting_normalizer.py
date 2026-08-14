"""
사이트별 추출 결과 → 표준 job_postings 문서 변환.

원칙: 사이트 파서는 RawExtractedFields 로 값만 추출하고,
      이 모듈에서 taxonomy·alias·정규화를 일괄 적용한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from src.models.schemas import (
    CareerLevel,
    CompanyInfo,
    JobPosting,
    LocationInfo,
    SalaryInfo,
    SkillTag,
    SourceRef,
)
from src.normalization.alias_resolver import resolve
from src.normalization.company_utils import normalize_company_name, normalize_job_title
from src.normalization.job_taxonomy import normalize_job_taxonomy
from src.normalization.location_utils import parse_korean_location
from src.normalization.work_arrangement import detect_work_arrangement
from src.taxonomy.career_levels import normalize_career_level
from src.taxonomy.employment_types import normalize_employment_type


@dataclass
class RawExtractedFields:
    """사이트 파서가 원문에서 추출한 비정규화 필드 묶음."""

    title: str
    company_raw: str
    description: str
    location_raw: str
    employment_type_raw: str = ""
    career_raw_text: str = ""
    career_min_years: int | None = None
    career_max_years: int | None = None
    work_arrangement_text: str = ""
    work_arrangement_override: str | None = None
    education_level: str | None = None
    job_category_raw: str = ""
    job_function_raw: str = ""
    skills: list[str] = field(default_factory=list)
    salary: SalaryInfo = field(default_factory=SalaryInfo)
    posted_at: str | None = None
    expires_at: str | None = None
    # 회사 부가 정보 (선택)
    company_industry: str | None = None
    company_size: str | None = None
    company_website: str | None = None
    # 해외 location (Remotive 등 — location_raw 파싱 방식이 다를 때)
    location_country: str | None = None
    location_region: str | None = None
    location_city: str | None = None
    use_korean_location_parser: bool = True


def build_job_posting(
    extracted: RawExtractedFields,
    raw: dict[str, Any],
) -> dict[str, Any]:
    """
    RawExtractedFields + raw 메타데이터 → job_postings dict.

    모든 사이트 파서의 parse_raw_posting() 마지막 단계에서 호출한다.
    """
    source_name = raw.get("source_name", "")
    source_job_id = raw.get("source_job_id", "")
    original_url = raw.get("original_url", "")

    # --- 제목 / 회사 ---
    normalized_title = normalize_job_title(extracted.title)
    company_clean = normalize_company_name(extracted.company_raw) if extracted.company_raw else ""
    company_canonical = (
        resolve("COMPANY", company_clean, source_name) if company_clean else ""
    )

    company = CompanyInfo(
        name=company_canonical or company_clean or extracted.company_raw,
        raw_name=extracted.company_raw,
        industry_name=extracted.company_industry,
        size_category=extracted.company_size,
        website_url=extracted.company_website,
    )

    # --- location ---
    if extracted.use_korean_location_parser:
        city, region, country = parse_korean_location(extracted.location_raw)
        city_canonical = resolve("LOCATION", city, source_name) if city else ""
        location = LocationInfo(
            country_name=country,
            region_name=region,
            city_name=city_canonical or city,
            raw_text=extracted.location_raw,
        )
    else:
        city = extracted.location_city or ""
        city_canonical = resolve("LOCATION", city, source_name) if city else ""
        location = LocationInfo(
            country_name=extracted.location_country or "",
            region_name=extracted.location_region,
            city_name=city_canonical or city,
            raw_text=extracted.location_raw,
        )

    # --- employment / career / work_arrangement ---
    employment_type_name = normalize_employment_type(extracted.employment_type_raw)
    career_level = normalize_career_level(
        raw_text=extracted.career_raw_text,
        min_years=extracted.career_min_years,
        max_years=extracted.career_max_years,
    )

    if extracted.work_arrangement_override is not None:
        work_arrangement = extracted.work_arrangement_override
    else:
        work_arrangement = detect_work_arrangement(extracted.work_arrangement_text)

    job_function_name, job_category_name = normalize_job_taxonomy(
        extracted.job_function_raw,
        extracted.job_category_raw,
        source_name,
    )

    # --- skills ---
    skill_tags = [
        SkillTag(
            raw_text=s,
            canonical_name=resolve("SKILL", s, source_name),
        )
        for s in extracted.skills
    ]

    now_iso = datetime.now(timezone.utc).isoformat()
    collected_at = raw.get("collected_at", now_iso)

    job = JobPosting(
        source_name=source_name,
        source_job_id=source_job_id,
        original_url=original_url,
        title=extracted.title,
        normalized_title=normalized_title,
        description=extracted.description,
        company=company,
        job_category_name=job_category_name,
        job_function_name=job_function_name,
        career_level=career_level,
        education_level=extracted.education_level,
        employment_type_name=employment_type_name,
        work_arrangement=work_arrangement,
        location=location,
        skills=skill_tags,
        salary=extracted.salary,
        source_refs=[
            SourceRef(
                source_name=source_name,
                source_job_id=source_job_id,
                original_url=original_url,
                collected_at=collected_at,
            )
        ],
        posted_at=extracted.posted_at or date.today().isoformat(),
        expires_at=extracted.expires_at,
        first_collected_at=collected_at,
        last_seen_at=collected_at,
        created_at=now_iso,
        updated_at=now_iso,
    )
    return job.to_dict()
