"""
4개 컬렉션 문서 구조를 dataclass로 정의.
JSON 직렬화/역직렬화는 to_dict() / from_dict()로 처리한다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. raw_job_postings
# ---------------------------------------------------------------------------

@dataclass
class RawJobPosting:
    source_name: str
    source_job_id: str
    original_url: str
    raw_html: str
    raw_text: str
    id: str = field(default_factory=_new_id)
    collected_at: str = field(default_factory=_now_iso)
    parse_status: str = "PENDING"          # PENDING / PARSED / FAILED
    parsed_job_posting_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RawJobPosting":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# 2. job_postings  (표준화된 채용공고)
# ---------------------------------------------------------------------------

@dataclass
class CompanyInfo:
    name: str
    raw_name: str
    registered_name: str | None = None
    industry_name: str | None = None
    size_category: str | None = None
    headquarters_country: str | None = None
    headquarters_region: str | None = None
    headquarters_city: str | None = None
    website_url: str | None = None


@dataclass
class CareerLevel:
    label: str
    min_years: int | None = None
    max_years: int | None = None


@dataclass
class LocationInfo:
    country_name: str
    city_name: str
    raw_text: str
    region_name: str | None = None


@dataclass
class SkillTag:
    raw_text: str
    canonical_name: str
    category_name: str | None = None


@dataclass
class SalaryInfo:
    raw_text: str | None = None
    min_amount: str | None = None   # Decimal을 JSON 직렬화 가능한 str로 보관
    max_amount: str | None = None
    currency_code: str | None = None
    pay_period: str | None = None   # HOURLY / MONTHLY / ANNUAL


@dataclass
class SourceRef:
    source_name: str
    source_job_id: str
    original_url: str
    collected_at: str


@dataclass
class JobPosting:
    source_name: str
    source_job_id: str
    original_url: str
    title: str
    normalized_title: str
    description: str
    company: CompanyInfo
    job_category_name: str
    job_function_name: str
    career_level: CareerLevel
    employment_type_name: str
    location: LocationInfo
    skills: list[SkillTag]
    salary: SalaryInfo
    source_refs: list[SourceRef]
    posted_at: str                       # ISO date string
    first_collected_at: str
    last_seen_at: str
    created_at: str
    updated_at: str
    id: str = field(default_factory=_new_id)
    education_level: str | None = None
    work_arrangement: str | None = None  # ONSITE / REMOTE / HYBRID
    expires_at: str | None = None
    crawl_status: str = "ACTIVE"         # ACTIVE / EXPIRED / DELETED / BLOCKED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobPosting":
        d = dict(d)
        d["company"] = CompanyInfo(**d["company"])
        d["career_level"] = CareerLevel(**d["career_level"])
        d["location"] = LocationInfo(**d["location"])
        d["skills"] = [SkillTag(**s) for s in d.get("skills", [])]
        d["salary"] = SalaryInfo(**d["salary"])
        d["source_refs"] = [SourceRef(**r) for r in d.get("source_refs", [])]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# 3. crawl_sources
# ---------------------------------------------------------------------------

@dataclass
class CrawlSource:
    source_name: str
    base_url: str
    id: str = field(default_factory=_new_id)
    source_type: str = "WEB_CRAWLING"
    robots_txt_url: str | None = None
    legal_risk_level: str = "MEDIUM"     # LOW / MEDIUM / HIGH
    rate_limit_policy: str = ""
    user_agent: str = ""
    last_crawled_at: str | None = None
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CrawlSource":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# 4. normalization_aliases
# ---------------------------------------------------------------------------

@dataclass
class NormalizationAlias:
    alias_type: str          # COMPANY / SKILL / LOCATION
    raw_text: str
    canonical_name: str
    id: str = field(default_factory=_new_id)
    source_name: str | None = None
    match_method: str = "MANUAL"   # EXACT / FUZZY / MANUAL / EMBEDDING

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NormalizationAlias":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
