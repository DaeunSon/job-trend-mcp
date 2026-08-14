"""
crawlers/remotive/parser.py 유닛 테스트.
"""
from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from src.crawlers.remotive.parser import (
    _extract_career_level,
    _extract_company,
    _extract_description,
    _extract_employment_type,
    _extract_location,
    _extract_posted_at,
    _extract_salary,
    _extract_skills,
    _extract_title,
    _extract_work_arrangement,
    _normalize_country,
    parse_raw_posting,
    run_remotive_parse,
)
from src.normalization.job_taxonomy import (
    extract_remotive_taxonomy_raw,
    normalize_job_taxonomy,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처
# ---------------------------------------------------------------------------

def _make_job(
    job_id: int = 1,
    title: str = "Senior Backend Developer",
    company_name: str = "Remote Corp",
    category: str = "Software Development",
    job_type: str = "full_time",
    location: str = "Worldwide",
    salary: str = "$80,000 - $100,000",
    description: str = "<p>We need a <strong>Python</strong> and Go developer with 5+ years experience.</p>",
    tags: list | None = None,
    pub_date: str = "2026-07-27T09:00:00",
) -> dict:
    return {
        "id": job_id,
        "url": f"https://remotive.com/remote-jobs/software-development/backend-{job_id}",
        "title": title,
        "company_name": company_name,
        "company_logo": "",
        "category": category,
        "job_type": job_type,
        "publication_date": pub_date,
        "candidate_required_location": location,
        "salary": salary,
        "description": description,
        "tags": tags if tags is not None else ["python", "go", "backend"],
    }


def _make_raw(
    job: dict | None = None,
    parse_status: str = "PENDING",
) -> dict:
    job = job or _make_job()
    return {
        "id": "test-raw-uuid",
        "source_name": "remotive",
        "source_job_id": str(job["id"]),
        "original_url": job.get("url", ""),
        "raw_html": "",
        "raw_text": json.dumps(job, ensure_ascii=False),
        "collected_at": "2026-07-27T10:00:00+00:00",
        "parse_status": parse_status,
        "parsed_job_posting_id": None,
    }


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_basic(self):
        assert _extract_title({"title": "  Backend Developer  "}) == "Backend Developer"

    def test_empty(self):
        assert _extract_title({}) == ""

    def test_none_value(self):
        assert _extract_title({"title": None}) == ""


# ---------------------------------------------------------------------------
# _extract_company
# ---------------------------------------------------------------------------

class TestExtractCompany:
    def test_basic(self):
        with patch("src.normalization.alias_resolver.resolve", return_value="Remote Corp"):
            info = _extract_company({"company_name": "Remote Corp"}, "remotive")
        assert info.raw_name == "Remote Corp"
        assert info.name == "Remote Corp"

    def test_empty_company_name(self):
        info = _extract_company({"company_name": ""}, "remotive")
        assert info.raw_name == ""


# ---------------------------------------------------------------------------
# _normalize_country
# ---------------------------------------------------------------------------

class TestNormalizeCountry:
    @pytest.mark.parametrize("raw,expected", [
        ("worldwide", "Global"),
        ("Worldwide", "Global"),
        ("usa", "United States"),
        ("USA", "United States"),
        ("uk", "United Kingdom"),
        ("EU", "Europe"),
        ("Canada", "Canada"),
        ("Germany", "Germany"),
        ("SomeUnknownRegion", "SomeUnknownRegion"),
    ])
    def test_mapping(self, raw, expected):
        assert _normalize_country(raw) == expected


# ---------------------------------------------------------------------------
# _extract_location
# ---------------------------------------------------------------------------

class TestExtractLocation:
    def test_worldwide(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            loc = _extract_location({"candidate_required_location": "Worldwide"}, "remotive")
        assert loc.raw_text == "Worldwide"
        assert loc.country_name == "Global"

    def test_usa_only(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            loc = _extract_location({"candidate_required_location": "USA"}, "remotive")
        assert loc.country_name == "United States"

    def test_comma_separated(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            loc = _extract_location({"candidate_required_location": "USA, Canada"}, "remotive")
        assert "USA" in loc.raw_text

    def test_empty_defaults_to_worldwide(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            loc = _extract_location({}, "remotive")
        assert loc.raw_text == "Worldwide"


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------

class TestExtractDescription:
    def test_strips_html_tags(self):
        html = "<p>Hello <strong>World</strong></p>"
        result = _extract_description({"description": html})
        assert "<p>" not in result
        assert "<strong>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_empty_description(self):
        assert _extract_description({"description": ""}) == ""
        assert _extract_description({}) == ""

    def test_preserves_text_content(self):
        html = "<ul><li>Python</li><li>Go</li></ul>"
        result = _extract_description({"description": html})
        assert "Python" in result
        assert "Go" in result


# ---------------------------------------------------------------------------
# _extract_career_level
# ---------------------------------------------------------------------------

class TestExtractCareerLevel:
    def test_senior(self):
        cl = _extract_career_level("We are looking for a Senior engineer with 7+ years")
        assert "Senior" in cl.label
        assert cl.min_years is not None

    def test_junior(self):
        cl = _extract_career_level("Entry level position for junior developers")
        assert "Junior" in cl.label

    def test_years_mentioned(self):
        cl = _extract_career_level("Requires 3+ years of experience in backend development")
        assert cl.min_years == 3

    def test_no_level_info(self):
        cl = _extract_career_level("We are looking for a developer to join our team")
        assert cl.label == "Any"

    def test_mid_level(self):
        cl = _extract_career_level("Mid-level software engineer needed")
        assert "Mid" in cl.label


# ---------------------------------------------------------------------------
# _extract_employment_type
# ---------------------------------------------------------------------------

class TestExtractEmploymentType:
    @pytest.mark.parametrize("job_type,expected", [
        ("full_time",  "full_time"),
        ("contract",   "contract"),
        ("part_time",  "part_time"),
        ("freelance",  "freelance"),
        ("internship", "internship"),
    ])
    def test_known_types(self, job_type, expected):
        assert _extract_employment_type({"job_type": job_type}) == expected

    def test_unknown_type_returns_original(self):
        result = _extract_employment_type({"job_type": "some_new_type"})
        assert result == "some_new_type"

    def test_missing_field_defaults_fulltime(self):
        result = _extract_employment_type({})
        assert result == "full_time"


# ---------------------------------------------------------------------------
# _extract_work_arrangement
# ---------------------------------------------------------------------------

class TestExtractWorkArrangement:
    def test_worldwide_is_remote(self):
        assert _extract_work_arrangement({"candidate_required_location": "Worldwide"}) == "REMOTE"

    def test_anywhere_is_remote(self):
        assert _extract_work_arrangement({"candidate_required_location": "Anywhere"}) == "REMOTE"

    def test_specific_country_still_remote(self):
        # Remotive는 리모트 전문 플랫폼
        assert _extract_work_arrangement({"candidate_required_location": "USA"}) == "REMOTE"


# ---------------------------------------------------------------------------
# _extract_salary
# ---------------------------------------------------------------------------

class TestExtractSalary:
    def test_dollar_range(self):
        si = _extract_salary({"salary": "$80,000 - $100,000"})
        assert si.raw_text == "$80,000 - $100,000"
        assert si.currency_code == "USD"
        assert si.min_amount is not None
        assert si.max_amount is not None

    def test_euro_value(self):
        si = _extract_salary({"salary": "€50,000 - €70,000"})
        assert si.currency_code == "EUR"

    def test_empty_salary(self):
        si = _extract_salary({"salary": ""})
        assert si.raw_text is None
        assert si.min_amount is None

    def test_no_salary_field(self):
        si = _extract_salary({})
        assert si.raw_text is None

    def test_unparseable_salary_stores_raw(self):
        si = _extract_salary({"salary": "Competitive salary"})
        assert si.raw_text == "Competitive salary"
        assert si.min_amount is None

    def test_pay_period_annual_detected(self):
        si = _extract_salary({"salary": "$100,000 per year"})
        assert si.pay_period == "ANNUAL"

    def test_pay_period_hourly_detected(self):
        si = _extract_salary({"salary": "$50/hour"})
        assert si.pay_period == "HOURLY"


# ---------------------------------------------------------------------------
# _extract_skills
# ---------------------------------------------------------------------------

class TestExtractSkills:
    def test_extracts_from_tags(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            skills = _extract_skills(
                {"tags": ["python", "react"]},
                "",
                "remotive",
            )
        raw_texts = [s.raw_text for s in skills]
        assert "python" in raw_texts
        assert "react" in raw_texts

    def test_deduplicates_tags(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            skills = _extract_skills(
                {"tags": ["python", "python", "go"]},
                "",
                "remotive",
            )
        raw_texts = [s.raw_text for s in skills]
        assert raw_texts.count("python") == 1

    def test_extracts_from_description(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            skills = _extract_skills(
                {"tags": []},
                "We use React and Node.js for our frontend stack",
                "remotive",
            )
        raw_texts = [s.raw_text for s in skills]
        assert "react" in raw_texts or "node.js" in raw_texts

    def test_empty_tags(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            skills = _extract_skills({"tags": []}, "", "remotive")
        assert isinstance(skills, list)

    def test_filters_generic_and_soft_noise(self):
        with patch("src.normalization.alias_resolver.resolve", side_effect=lambda t, r, s: r):
            skills = _extract_skills(
                {
                    "tags": [
                        "backend",
                        "documentation",
                        "people management",
                        "python",
                        "Kubernetes",
                    ]
                },
                "",
                "remotive",
            )
        raw_texts = [s.raw_text for s in skills]
        assert "backend" not in raw_texts
        assert "documentation" not in raw_texts
        assert "people management" not in raw_texts
        assert "python" in raw_texts
        assert "Kubernetes" in raw_texts


# ---------------------------------------------------------------------------
# _extract_posted_at
# ---------------------------------------------------------------------------

class TestExtractPostedAt:
    def test_uses_publication_date(self):
        job = {"publication_date": "2026-07-27T09:00:00"}
        raw = {"collected_at": "2026-07-27T10:00:00+00:00"}
        result = _extract_posted_at(job, raw)
        assert result == "2026-07-27"

    def test_falls_back_to_collected_at(self):
        job = {}
        raw = {"collected_at": "2026-07-20T10:00:00+00:00"}
        result = _extract_posted_at(job, raw)
        assert result == "2026-07-20"

    def test_falls_back_to_today(self):
        result = _extract_posted_at({}, {})
        assert result == date.today().isoformat()


# ---------------------------------------------------------------------------
# _infer_category
# ---------------------------------------------------------------------------

class TestInferCategory:
    @pytest.mark.parametrize("category,expected", [
        ("Software Development", "Engineering & Technology"),
        ("Devops", "Engineering & Technology"),
        ("Artificial Intelligence", "Data & Analytics"),
        ("Data and Analytics", "Data & Analytics"),
        ("Design", "Product & Design"),
        ("Marketing", "Marketing & Growth"),
        ("Finance", "Finance & Accounting"),
        ("Human Resources", "Human Resources"),
        ("Legal", "Legal & Compliance"),
        ("Research", "Research & Science"),
        ("Customer Service", "Customer Success"),
        ("Unknown Category", "Other"),
    ])
    def test_category_mapping(self, category, expected):
        func_raw, cat_raw = extract_remotive_taxonomy_raw({"category": category}, "")
        _, job_category = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_category == expected


# ---------------------------------------------------------------------------
# _infer_function
# ---------------------------------------------------------------------------

class TestInferFunction:
    @pytest.mark.parametrize("title,expected", [
        ("Senior Backend Developer", "Backend Engineer"),
        ("Frontend Engineer React", "Frontend Engineer"),
        ("Full Stack Developer", "Full Stack Engineer"),
        ("Data Scientist Python", "Data Scientist"),
        ("Data Engineer Spark", "Data Engineer"),
        ("Machine Learning Engineer", "Machine Learning Engineer"),
        ("DevOps Engineer Kubernetes", "DevOps / Platform Engineer"),
        ("Product Manager", "Product Manager"),
        ("UX Designer Figma", "UX Designer"),
        ("Financial Analyst FP&A", "Financial Analyst"),
        ("Recruiter Talent", "Recruiter"),
        ("Legal Counsel", "Legal Counsel"),
        ("Research Scientist NLP", "Research Scientist"),
        ("Customer Success Manager", "Customer Success Manager"),
        ("Unknown Role XYZ", ""),
    ])
    def test_function_inference(self, title, expected):
        func_raw, cat_raw = extract_remotive_taxonomy_raw({"tags": []}, title)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == expected


# ---------------------------------------------------------------------------
# parse_raw_posting (통합)
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def test_returns_job_posting_dict(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, r, s: r):
            result = parse_raw_posting(raw)

        assert result is not None
        assert result["source_name"] == "remotive"
        assert result["source_job_id"] == "1"
        assert result["title"] == "Senior Backend Developer"

    def test_returns_none_for_empty_raw_text(self):
        raw = _make_raw()
        raw["raw_text"] = ""
        result = parse_raw_posting(raw)
        assert result is None

    def test_returns_none_for_invalid_json(self):
        raw = _make_raw()
        raw["raw_text"] = "this is not json {"
        result = parse_raw_posting(raw)
        assert result is None

    def test_all_required_fields_present(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, r, s: r):
            result = parse_raw_posting(raw)

        assert result is not None
        required = [
            "id", "source_name", "source_job_id", "original_url",
            "title", "normalized_title", "description",
            "company", "location", "skills", "salary",
            "employment_type_name", "career_level",
            "posted_at", "created_at", "updated_at",
            "source_refs",
        ]
        for field in required:
            assert field in result, f"필드 누락: {field}"

    def test_work_arrangement_is_remote(self):
        raw = _make_raw(_make_job(location="Worldwide"))
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, r, s: r):
            result = parse_raw_posting(raw)

        assert result is not None
        assert result["work_arrangement"] == "REMOTE"

    def test_source_refs_populated(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, r, s: r):
            result = parse_raw_posting(raw)

        assert result is not None
        refs = result["source_refs"]
        assert len(refs) == 1
        assert refs[0]["source_name"] == "remotive"

    def test_salary_parsed(self):
        raw = _make_raw(_make_job(salary="$90,000 - $120,000"))
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, r, s: r):
            result = parse_raw_posting(raw)

        assert result is not None
        salary = result["salary"]
        assert salary["raw_text"] == "$90,000 - $120,000"
        assert salary["currency_code"] == "USD"

    def test_description_has_no_html_tags(self):
        raw = _make_raw(_make_job(description="<p>Hello <strong>World</strong></p>"))
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, r, s: r):
            result = parse_raw_posting(raw)

        assert result is not None
        assert "<p>" not in result["description"]
        assert "Hello" in result["description"]


# ---------------------------------------------------------------------------
# run_remotive_parse (통합)
# ---------------------------------------------------------------------------

class TestRunRemotiveParse:
    def test_processes_pending_files(self, tmp_path):
        raw_dir = tmp_path / "raw_job_postings" / "2026-07-27"
        raw_dir.mkdir(parents=True)

        job = _make_job()
        raw_doc = _make_raw(job)

        import json as _json
        raw_file = raw_dir / "remotive_software-development.json"
        raw_file.write_text(_json.dumps([raw_doc], ensure_ascii=False))

        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, r, s: r), \
             patch("src.crawlers.parse_batch.save_documents") as mock_save:
            run_remotive_parse(crawl_date="2026-07-27", base_dir=str(tmp_path))

        mock_save.assert_called_once()
        saved = mock_save.call_args[1]["documents"]
        assert len(saved) == 1

    def test_skips_non_pending(self, tmp_path):
        raw_dir = tmp_path / "raw_job_postings" / "2026-07-27"
        raw_dir.mkdir(parents=True)

        raw_doc = _make_raw(parse_status="PARSED")
        import json as _json
        raw_file = raw_dir / "remotive_data.json"
        raw_file.write_text(_json.dumps([raw_doc], ensure_ascii=False))

        with patch("src.crawlers.parse_batch.save_documents") as mock_save:
            run_remotive_parse(crawl_date="2026-07-27", base_dir=str(tmp_path))

        mock_save.assert_not_called()

    def test_handles_missing_directory(self, tmp_path):
        # 디렉토리가 없어도 예외 없이 종료
        run_remotive_parse(crawl_date="2026-07-27", base_dir=str(tmp_path))
