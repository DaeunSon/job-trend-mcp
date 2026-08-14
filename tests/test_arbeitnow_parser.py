"""
crawlers/arbeitnow/parser.py 유닛 테스트.
"""
from __future__ import annotations

import json

from src.crawlers.arbeitnow.parser import (
    _extract_career_raw_text,
    _extract_company_name,
    _extract_description,
    _extract_employment_type_raw,
    _extract_location_raw,
    _extract_posted_at,
    _extract_salary,
    _extract_skill_names,
    _extract_title,
    _normalize_country,
    parse_raw_posting,
)
from src.normalization.job_taxonomy import extract_arbeitnow_taxonomy_raw


# ---------------------------------------------------------------------------
# 테스트 픽스처
# ---------------------------------------------------------------------------

def _make_job(
    slug: str = "senior-backend-1",
    title: str = "Senior Backend Engineer",
    company_name: str = "Tech Corp",
    location: str = "Berlin",
    remote: bool = False,
    tags: list | None = None,
    job_types: list | None = None,
    description: str | None = None,
    created_at: int = 1785391025,
) -> dict:
    if description is None:
        description = (
            "&lt;p&gt;We need a &lt;strong&gt;Python&lt;/strong&gt; "
            "and Go developer with 5+ years experience. "
            "Salary €70,000 - €90,000.&lt;/p&gt;"
        )
    return {
        "slug": slug,
        "company_name": company_name,
        "title": title,
        "description": description,
        "remote": remote,
        "url": f"https://www.arbeitnow.com/jobs/companies/techcorp/{slug}",
        "tags": tags if tags is not None else ["Engineering", "python"],
        "job_types": job_types if job_types is not None else ["Full time", "Mid"],
        "location": location,
        "created_at": created_at,
    }


def _make_raw(job: dict | None = None, parse_status: str = "PENDING") -> dict:
    job = job or _make_job()
    return {
        "id": "test-raw-uuid",
        "source_name": "arbeitnow",
        "source_job_id": job["slug"],
        "original_url": job["url"],
        "raw_html": "",
        "raw_text": json.dumps(job, ensure_ascii=False),
        "collected_at": "2026-07-30T10:00:00+00:00",
        "parse_status": parse_status,
    }


# ---------------------------------------------------------------------------
# 필드 추출
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_returns_title(self):
        assert _extract_title(_make_job(title="Data Scientist")) == "Data Scientist"

    def test_empty_when_missing(self):
        assert _extract_title({}) == ""


class TestExtractCompanyName:
    def test_returns_company(self):
        assert _extract_company_name(_make_job(company_name="Acme")) == "Acme"

    def test_empty_when_missing(self):
        assert _extract_company_name({}) == ""


class TestExtractLocation:
    def test_location(self):
        assert _extract_location_raw(_make_job(location="Munich")) == "Munich"

    def test_empty(self):
        assert _extract_location_raw({"location": ""}) == ""


class TestExtractDescription:
    def test_unescapes_and_strips_html(self):
        job = {"description": "&lt;p&gt;Hello &lt;strong&gt;World&lt;/strong&gt;&lt;/p&gt;"}
        result = _extract_description(job)
        assert "Hello" in result
        assert "World" in result
        assert "<" not in result

    def test_empty(self):
        assert _extract_description({}) == ""


class TestExtractEmploymentType:
    def test_full_time(self):
        assert _extract_employment_type_raw({"job_types": ["Full time"]}) == "full time"

    def test_fulltime_permanent(self):
        assert _extract_employment_type_raw(
            {"job_types": ["fulltime permanent"]}
        ) == "full time"

    def test_part_time(self):
        assert _extract_employment_type_raw({"job_types": ["Part time"]}) == "part time"

    def test_freelance(self):
        assert _extract_employment_type_raw({"job_types": ["Freelance"]}) == "freelance"

    def test_career_only_falls_back_to_join(self):
        result = _extract_employment_type_raw({"job_types": ["Mid", "Experienced"]})
        assert "Mid" in result

    def test_empty(self):
        assert _extract_employment_type_raw({"job_types": []}) == ""


class TestExtractCareer:
    def test_includes_job_types(self):
        job = _make_job(job_types=["Mid", "Full time"])
        text = _extract_career_raw_text(job, "some description")
        assert "Mid" in text
        assert "Full time" in text


class TestExtractSkills:
    def test_tags_and_description(self):
        job = _make_job(tags=["Engineering", "Remote", "Terraform"])
        skills = _extract_skill_names(job, "We use Python and Docker daily.")
        assert "Engineering" not in skills  # 직무 노이즈 필터
        assert "Remote" not in skills
        assert "Terraform" in skills
        assert "python" in skills
        assert "docker" in skills

    def test_filters_place_and_german_noise(self):
        job = _make_job(tags=["Hamburg", "Werkstudent", "python"])
        skills = _extract_skill_names(job, "")
        assert "Hamburg" not in skills
        assert "Werkstudent" not in skills
        assert "python" in skills


class TestExtractPostedAt:
    def test_unix_timestamp(self):
        from datetime import datetime, timezone
        job = _make_job(created_at=1785391025)
        result = _extract_posted_at(job, _make_raw(job))
        expected = datetime.fromtimestamp(1785391025, tz=timezone.utc).date().isoformat()
        assert result == expected

    def test_fallback_collected_at(self):
        raw = _make_raw()
        result = _extract_posted_at({"created_at": "bad"}, raw)
        assert result == "2026-07-30"


class TestExtractSalary:
    def test_euro_range(self):
        info = _extract_salary("Salary €70,000 - €90,000 per year.")
        assert info.min_amount == "70000"
        assert info.max_amount == "90000"
        assert info.currency_code == "EUR"

    def test_empty(self):
        assert _extract_salary("").raw_text is None


class TestNormalizeCountry:
    def test_berlin(self):
        assert _normalize_country("Berlin") == "Germany"

    def test_remote(self):
        assert _normalize_country("Remote") == "Global"

    def test_unknown_city_passthrough(self):
        assert _normalize_country("Gotham") == "Gotham"


class TestTaxonomy:
    def test_tag_as_category(self):
        job = _make_job(tags=["Engineering", "Sales"])
        function_raw, category_raw = extract_arbeitnow_taxonomy_raw(
            job, "Senior Backend Engineer",
        )
        assert category_raw == "Engineering"
        assert function_raw  # title keyword match


# ---------------------------------------------------------------------------
# parse_raw_posting 통합
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def test_success(self):
        result = parse_raw_posting(_make_raw())
        assert result is not None
        assert result["title"]
        assert result["source_name"] == "arbeitnow"
        assert result["company"]["raw_name"] == "Tech Corp"
        assert result["location"]["city_name"] or result["location"]["raw_text"]

    def test_remote_override(self):
        job = _make_job(remote=True, location="")
        result = parse_raw_posting(_make_raw(job))
        assert result is not None
        assert result["work_arrangement"] == "REMOTE"

    def test_html_description_cleaned(self):
        result = parse_raw_posting(_make_raw())
        assert result is not None
        assert "<" not in result["description"]
        assert "Python" in result["description"]

    def test_invalid_json_returns_none(self):
        raw = _make_raw()
        raw["raw_text"] = "not-json"
        assert parse_raw_posting(raw) is None

    def test_empty_raw_text_returns_none(self):
        raw = _make_raw()
        raw["raw_text"] = ""
        assert parse_raw_posting(raw) is None

    def test_employment_type_normalized(self):
        job = _make_job(job_types=["fulltime permanent"])
        result = parse_raw_posting(_make_raw(job))
        assert result is not None
        assert result["employment_type_name"] == "Full-time"
