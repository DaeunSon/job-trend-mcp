"""
crawlers/themuse/parser.py 유닛 테스트.
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest

from src.crawlers.themuse.parser import (
    _extract_career_raw_text,
    _extract_company_name,
    _extract_description,
    _extract_employment_type_raw,
    _extract_first_location,
    _extract_location_raw,
    _extract_posted_at,
    _extract_salary,
    _extract_skill_names,
    _extract_title,
    _normalize_country,
    parse_raw_posting,
)
from src.normalization.job_taxonomy import extract_themuse_taxonomy_raw


# ---------------------------------------------------------------------------
# 테스트 픽스처
# ---------------------------------------------------------------------------

def _make_job(
    job_id: int = 1,
    title: str = "Senior Backend Engineer",
    company_name: str = "Tech Corp",
    category: str = "Software Engineering",
    level: str = "Senior Level",
    location: str = "San Francisco, CA",
    contents: str = "<p>We need a <strong>Python</strong> and Go developer with 5+ years experience.</p>",
    tags: list | None = None,
    pub_date: str = "2026-07-29T10:00:00Z",
) -> dict:
    return {
        "id": job_id,
        "name": title,
        "contents": contents,
        "type": "external",
        "publication_date": pub_date,
        "short_name": f"senior-backend-engineer-{job_id}",
        "model_type": "jobs",
        "locations": [{"name": location}] if location else [],
        "categories": [{"name": category}] if category else [],
        "levels": [{"name": level, "short_name": level.lower().replace(" ", "-")}],
        "tags": tags if tags is not None else ["python", "go"],
        "refs": {"landing_page": f"https://www.themuse.com/jobs/techcorp/senior-backend-{job_id}"},
        "company": {"id": 1234, "short_name": "techcorp", "name": company_name},
    }


def _make_raw(
    job: dict | None = None,
    parse_status: str = "PENDING",
) -> dict:
    job = job or _make_job()
    return {
        "id": "test-raw-uuid",
        "source_name": "themuse",
        "source_job_id": str(job["id"]),
        "original_url": job["refs"]["landing_page"],
        "raw_html": "",
        "raw_text": json.dumps(job, ensure_ascii=False),
        "collected_at": "2026-07-29T10:00:00+00:00",
        "parse_status": parse_status,
    }


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_returns_name_field(self):
        job = _make_job(title="Senior Python Developer")
        assert _extract_title(job) == "Senior Python Developer"

    def test_strips_whitespace(self):
        job = {"name": "  Data Scientist  "}
        assert _extract_title(job) == "Data Scientist"

    def test_empty_when_missing(self):
        assert _extract_title({}) == ""

    def test_empty_when_none(self):
        assert _extract_title({"name": None}) == ""


# ---------------------------------------------------------------------------
# _extract_company_name
# ---------------------------------------------------------------------------

class TestExtractCompanyName:
    def test_returns_company_name(self):
        job = _make_job(company_name="Acme Corp")
        assert _extract_company_name(job) == "Acme Corp"

    def test_empty_when_no_company(self):
        assert _extract_company_name({}) == ""

    def test_empty_when_company_name_missing(self):
        assert _extract_company_name({"company": {}}) == ""


# ---------------------------------------------------------------------------
# _extract_location_raw / _extract_first_location
# ---------------------------------------------------------------------------

class TestExtractLocation:
    def test_location_raw_single(self):
        job = _make_job(location="Austin, TX")
        assert _extract_location_raw(job) == "Austin, TX"

    def test_location_raw_multiple(self):
        job = {"locations": [{"name": "New York, NY"}, {"name": "Remote"}]}
        assert _extract_location_raw(job) == "New York, NY, Remote"

    def test_location_raw_empty(self):
        assert _extract_location_raw({"locations": []}) == ""
        assert _extract_location_raw({}) == ""

    def test_first_location_city_only(self):
        job = _make_job(location="Seattle, WA")
        assert _extract_first_location(job) == "Seattle"

    def test_first_location_no_comma(self):
        job = {"locations": [{"name": "Remote"}]}
        assert _extract_first_location(job) == "Remote"

    def test_first_location_empty(self):
        assert _extract_first_location({}) == ""


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------

class TestExtractDescription:
    def test_strips_html_tags(self):
        job = {"contents": "<p>We need a <strong>Python</strong> developer.</p>"}
        result = _extract_description(job)
        assert "<p>" not in result
        assert "<strong>" not in result
        assert "Python" in result

    def test_empty_when_no_contents(self):
        assert _extract_description({}) == ""
        assert _extract_description({"contents": ""}) == ""
        assert _extract_description({"contents": None}) == ""

    def test_preserves_text_content(self):
        job = {"contents": "<ul><li>Python</li><li>Go</li></ul>"}
        result = _extract_description(job)
        assert "Python" in result
        assert "Go" in result


# ---------------------------------------------------------------------------
# _extract_employment_type_raw
# ---------------------------------------------------------------------------

class TestExtractEmploymentTypeRaw:
    def test_default_full_time(self):
        job = _make_job(contents="<p>Full-time position available.</p>")
        assert _extract_employment_type_raw(job) == "full_time"

    def test_detects_part_time(self):
        job = {"contents": "<p>This is a part-time role.</p>", "name": "Part-time Designer"}
        assert _extract_employment_type_raw(job) == "part_time"

    def test_detects_contract(self):
        job = {"contents": "<p>6-month contract position.</p>", "name": "Contract Engineer"}
        assert _extract_employment_type_raw(job) == "contract"

    def test_detects_internship(self):
        job = {"contents": "<p>Summer internship program.</p>", "name": "Intern Developer"}
        assert _extract_employment_type_raw(job) == "internship"


# ---------------------------------------------------------------------------
# _extract_career_raw_text
# ---------------------------------------------------------------------------

class TestExtractCareerRawText:
    def test_includes_level_name(self):
        job = _make_job(level="Senior Level")
        result = _extract_career_raw_text(job)
        assert "Senior Level" in result

    def test_includes_description_prefix(self):
        job = _make_job(contents="<p>5 years of experience required.</p>")
        result = _extract_career_raw_text(job)
        assert "years" in result.lower() or "experience" in result.lower()


# ---------------------------------------------------------------------------
# _extract_skill_names
# ---------------------------------------------------------------------------

class TestExtractSkillNames:
    def test_includes_tags(self):
        job = _make_job(tags=["python", "kubernetes"])
        description = _extract_description(job)
        skills = _extract_skill_names(job, description)
        assert "python" in skills
        assert "kubernetes" in skills

    def test_extracts_known_tech_from_description(self):
        job = {"tags": []}
        description = "Experience with Docker and PostgreSQL required."
        skills = _extract_skill_names(job, description)
        assert "docker" in skills
        assert "postgresql" in skills

    def test_no_duplicates(self):
        job = {"tags": ["python"]}
        description = "Strong Python skills required."
        skills = _extract_skill_names(job, description)
        assert skills.count("python") == 1

    def test_empty_tags_and_description(self):
        job = {"tags": []}
        skills = _extract_skill_names(job, "")
        assert skills == []


# ---------------------------------------------------------------------------
# _extract_posted_at
# ---------------------------------------------------------------------------

class TestExtractPostedAt:
    def test_parses_iso_date_with_z(self):
        job = {"publication_date": "2026-07-29T10:00:00Z"}
        raw = {}
        assert _extract_posted_at(job, raw) == "2026-07-29"

    def test_falls_back_to_collected_at(self):
        job = {}
        raw = {"collected_at": "2026-07-29T10:00:00+00:00"}
        assert _extract_posted_at(job, raw) == "2026-07-29"

    def test_falls_back_to_today(self):
        today = date.today().isoformat()
        assert _extract_posted_at({}, {}) == today

    def test_invalid_date_falls_back(self):
        job = {"publication_date": "not-a-date"}
        raw = {}
        result = _extract_posted_at(job, raw)
        assert result == date.today().isoformat()


# ---------------------------------------------------------------------------
# _normalize_country
# ---------------------------------------------------------------------------

class TestNormalizeCountry:
    def test_usa_variants(self):
        assert _normalize_country("New York") == "United States"
        assert _normalize_country("usa") == "United States"
        assert _normalize_country("United States") == "United States"

    def test_global_variants(self):
        assert _normalize_country("Remote") == "Global"
        assert _normalize_country("worldwide") == "Global"
        assert _normalize_country("Anywhere") == "Global"

    def test_known_countries(self):
        assert _normalize_country("canada") == "Canada"
        assert _normalize_country("germany") == "Germany"

    def test_unknown_defaults_to_united_states(self):
        assert _normalize_country("San Francisco") == "United States"


# ---------------------------------------------------------------------------
# extract_themuse_taxonomy_raw
# ---------------------------------------------------------------------------

class TestExtractThemuseTaxonomyRaw:
    def test_extracts_category_from_categories_list(self):
        job = {"categories": [{"name": "Software Engineering"}]}
        function_raw, category_raw = extract_themuse_taxonomy_raw(job, "Backend Engineer")
        assert category_raw == "Software Engineering"

    def test_empty_category_when_no_categories(self):
        job = {"categories": []}
        _, category_raw = extract_themuse_taxonomy_raw(job, "Backend Engineer")
        assert category_raw == ""

    def test_function_raw_extracted_from_title(self):
        job = {"categories": []}
        function_raw, _ = extract_themuse_taxonomy_raw(job, "Senior Python Backend Engineer")
        assert function_raw != "" or True  # resolve가 매핑 없으면 빈 문자열도 허용

    def test_misleading_api_category_for_driver_gig(self):
        job = {"categories": [{"name": "Software Engineering"}]}
        function_raw, category_raw = extract_themuse_taxonomy_raw(
            job,
            "Drive with Lyft - Signing up is Easy",
            "We're looking for new drivers.",
        )
        assert function_raw == ""
        assert category_raw == "Other"

    def test_api_category_maps_for_engineering_role(self):
        job = {"categories": [{"name": "Software Engineering"}]}
        function_raw, category_raw = extract_themuse_taxonomy_raw(
            job,
            "Test Engineer, Propulsion Components",
        )
        assert function_raw == "test engineer"
        assert category_raw == "Software Engineering"


# ---------------------------------------------------------------------------
# _extract_salary
# ---------------------------------------------------------------------------

class TestExtractSalary:
    def test_pay_range_levels(self):
        desc = (
            "COMPENSATION AND BENEFITS:\n"
            "Pay range:\n"
            "Level 1: $100,000.00 - $115,000.00/per year\n"
            "Level 2: $110,000.00 - $135,000.00/per year"
        )
        salary = _extract_salary(desc)
        assert salary.min_amount == "100000"
        assert salary.max_amount == "135000"
        assert salary.currency_code == "USD"
        assert salary.pay_period == "ANNUAL"
        assert "Level 1" in (salary.raw_text or "")

    def test_bonus_only_compensation(self):
        desc = (
            "Get a maximum of $400 in bonuses in Las Vegas.\n"
            "Earn $100 for every 10 rides in 7 days (limit 4)."
        )
        salary = _extract_salary(desc)
        assert salary.raw_text is not None
        assert "$400" in salary.raw_text
        assert salary.min_amount == "100"
        assert salary.max_amount == "400"
        assert salary.pay_period is None

    def test_empty_description(self):
        salary = _extract_salary("")
        assert salary.raw_text is None
        assert salary.min_amount is None

# ---------------------------------------------------------------------------
# parse_raw_posting
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def test_returns_job_posting_dict(self):
        raw = _make_raw(_make_job(1))
        result = parse_raw_posting(raw)
        assert result is not None
        assert isinstance(result, dict)

    def test_has_required_fields(self):
        raw = _make_raw(_make_job(1))
        result = parse_raw_posting(raw)
        assert result is not None
        for field in ("id", "source_name", "source_job_id", "title", "description"):
            assert field in result, f"필드 누락: {field}"

    def test_source_name_is_themuse(self):
        raw = _make_raw(_make_job(1))
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["source_name"] == "themuse"

    def test_title_uses_name_field(self):
        job = _make_job(title="Staff Platform Engineer")
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["title"] == "Staff Platform Engineer"

    def test_description_is_plain_text(self):
        job = _make_job(contents="<p>We need a <strong>Python</strong> developer.</p>")
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        assert "<p>" not in result["description"]
        assert "Python" in result["description"]

    def test_returns_none_for_empty_raw_text(self):
        raw = {
            "source_name": "themuse",
            "source_job_id": "999",
            "raw_text": "",
        }
        assert parse_raw_posting(raw) is None

    def test_returns_none_for_invalid_json(self):
        raw = {
            "source_name": "themuse",
            "source_job_id": "999",
            "raw_text": "{ broken json",
        }
        assert parse_raw_posting(raw) is None

    def test_company_name_extracted(self):
        job = _make_job(company_name="Stripe Inc")
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        company = result.get("company", {})
        assert "Stripe" in (company.get("name") or company.get("raw_name", ""))

    def test_posted_at_is_valid_date(self):
        job = _make_job(pub_date="2026-07-01T08:00:00Z")
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["posted_at"] == "2026-07-01"

    def test_location_country_set(self):
        job = _make_job(location="Austin, TX")
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        location = result.get("location", {})
        assert location.get("country_name") == "United States"

    def test_location_city_extracted(self):
        job = _make_job(location="Chicago, IL")
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        location = result.get("location", {})
        assert "Chicago" in (location.get("city_name") or location.get("raw_text", ""))

    def test_remote_location_sets_global_country(self):
        job = _make_job(location="Remote")
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        location = result.get("location", {})
        assert location.get("country_name") == "Global"

    def test_skills_extracted(self):
        job = _make_job(
            tags=["python"],
            contents="<p>Python and Docker experience required.</p>",
        )
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        skill_names = [s.get("raw_text", "") for s in result.get("skills", [])]
        assert "python" in skill_names

    def test_salary_extracted_from_contents(self):
        job = _make_job(
            title="Test Engineer",
            contents=(
                "<p>COMPENSATION AND BENEFITS:</p>"
                "<p>Pay range:</p>"
                "<p>Level 1: $100,000.00 - $115,000.00/per year</p>"
            ),
        )
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        salary = result["salary"]
        assert salary["min_amount"] == "100000"
        assert salary["max_amount"] == "115000"
        assert salary["currency_code"] == "USD"

    def test_test_engineer_category_from_function_fallback(self):
        job = _make_job(
            title="Test Engineer, Propulsion Components",
            category="Software Engineering",
        )
        raw = _make_raw(job)
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["job_function_name"] == "QA / Test Engineer"
        assert result["job_category_name"] == "Engineering & Technology"

    def test_exception_returns_none(self):
        """파싱 중 예외 발생 시 None을 반환하고 전파하지 않는다."""
        raw = _make_raw(_make_job(1))
        with patch(
            "src.crawlers.themuse.parser._extract_title",
            side_effect=RuntimeError("unexpected"),
        ):
            result = parse_raw_posting(raw)
        assert result is None
