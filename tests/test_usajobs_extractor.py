"""
crawlers/usajobs/extractor.py 유닛 테스트.
"""
from __future__ import annotations

import json

from src.crawlers.usajobs.extractor import (
    _parse_salary,
    _parse_us_location,
    apply_detail_salary_to_job,
    extract_detail_fields,
    extract_job_fields,
    extract_salary_from_detail_html,
    parse_raw_posting,
)
from src.normalization.job_taxonomy import extract_usajobs_taxonomy_raw


def _make_job(**overrides) -> dict:
    job = {
        "DocumentID": 878397800,
        "Title": "Top Secret Security Software Engineer - DHA",
        "Agency": "Social Security Administration",
        "Department": "Other Agencies and Independent Organizations",
        "SubAgency": "Chief Information Officer (CIO)",
        "PositionURI": "https://www.usajobs.gov:443/job/878397800",
        "PositionID": "SSA-13021462-26-DHA-CIO",
        "SalaryDisplay": "Starting at $111,147 Per year (GS 13)",
        "MinimumRange": 111147,
        "WorkType": "Permanent",
        "WorkSchedule": "Full-time",
        "LocationName": "Woodlawn, Maryland",
        "LocationDisplay": "Woodlawn, Maryland + 1 location(s)",
        "Location": "Multiple Locations",
        "HiringPath": [
            {
                "Code": "public",
                "SearchDisplay": "Open to the public",
                "Tooltip": "Jobs open to U.S. Citizens",
                "IsSearchFilter": False,
            }
        ],
        "JobCategoryCode": [
            {"Name": "Information Technology Management", "Code": "2210"}
        ],
        "JobGrade": "GS",
        "LowGrade": "13",
        "HighGrade": "13",
        "PositionStartDate": "2026-07-30T00:00:00.0000",
        "PositionEndDate": "2026-08-13T23:59:59.9970",
        "DateDisplay": "Open 07/30/2026 to 08/13/2026",
        "Relocation": False,
    }
    job.update(overrides)
    return job


def _make_raw(job: dict) -> dict:
    return {
        "id": "test-uuid",
        "source_name": "usajobs",
        "source_job_id": str(job["DocumentID"]),
        "original_url": f"https://www.usajobs.gov/job/{job['DocumentID']}",
        "raw_html": "",
        "raw_text": json.dumps(job, ensure_ascii=False),
        "collected_at": "2026-07-30T00:00:00+00:00",
        "parse_status": "PENDING",
        "parsed_job_posting_id": None,
    }


class TestExtractJobFields:
    def test_basic_fields(self):
        fields = extract_job_fields(_make_job())
        assert fields["title"].startswith("Top Secret Security Software Engineer")
        assert fields["company"] == "Social Security Administration"
        assert fields["location_raw"] == "Woodlawn, Maryland"
        assert fields["employment_type_raw"] == "Permanent Full-time"
        assert "Open to the public" in fields["career_raw"]
        assert fields["salary_raw"].startswith("Starting at $111,147")
        assert fields["posted_at"] == "2026-07-30"
        assert fields["expires_at"] == "2026-08-13"
        assert fields["job_category_raw"] == "Information Technology Management"
        assert ":443" not in fields["original_url"]
        assert fields["document_id"] == "878397800"

    def test_falls_back_to_department_when_no_agency(self):
        fields = extract_job_fields(_make_job(Agency="", Department="Dept of Defense"))
        assert fields["company"] == "Dept of Defense"

    def test_does_not_expose_gs_grade_as_schema_field(self):
        fields = extract_job_fields(_make_job())
        assert "JobGrade" not in fields
        assert "LowGrade" not in fields
        assert "HighGrade" not in fields
        assert "security" not in {k.lower() for k in fields}


class TestParseSalary:
    def test_starting_at_per_year(self):
        s = _parse_salary("Starting at $111,147 Per year (GS 13)", 111147)
        assert s.min_amount == "111147"
        assert s.currency_code == "USD"
        assert s.pay_period == "ANNUAL"
        assert "GS 13" in (s.raw_text or "")

    def test_starting_at_with_maximum_range_field(self):
        s = _parse_salary(
            "Starting at $104,502 Per year (GS 12)",
            104502,
            140188,
        )
        assert s.min_amount == "104502"
        assert s.max_amount == "140188"

    def test_range(self):
        s = _parse_salary("$50,000 to $80,000 Per year", None)
        assert s.min_amount == "50000"
        assert s.max_amount == "80000"

    def test_hyphen_range_display(self):
        s = _parse_salary("$104,502 - $140,188 per year", None)
        assert s.min_amount == "104502"
        assert s.max_amount == "140188"
        assert s.pay_period == "ANNUAL"


class TestExtractSalaryFromDetailHtml:
    def test_remuneration_and_display(self):
        html = '''
        <input type="hidden" value='{"RemunerationMinimumAmount":"104502.00","RemunerationMaximumAmount":"140188.00"}'/>
        <dt>Salary</dt><dd>$104,502 - $140,188 per year</dd>
        '''
        info = extract_salary_from_detail_html(html)
        assert info["min"] == "104502"
        assert info["max"] == "140188"
        assert info["display"] == "$104,502 - $140,188 per year"

    def test_apply_detail_salary_to_job(self):
        job = {
            "SalaryDisplay": "Starting at $104,502 Per year (GS 12)",
            "MinimumRange": "104502",
        }
        html = (
            '"RemunerationMinimumAmount":"104502.00"'
            '"RemunerationMaximumAmount":"140188.00"'
            "$104,502 - $140,188 per year"
        )
        apply_detail_salary_to_job(job, html)
        assert job["MaximumRange"] == "140188"
        assert job["SalaryDisplay"] == "$104,502 - $140,188 per year"

    def test_parse_raw_uses_maximum_range(self):
        job = _make_job(
            SalaryDisplay="Starting at $104,502 Per year (GS 12)",
            MinimumRange="104502",
            MaximumRange="140188",
        )
        result = parse_raw_posting(_make_raw(job))
        assert result is not None
        assert result["salary"]["min_amount"] == "104502"
        assert result["salary"]["max_amount"] == "140188"


class TestExtractDetailFields:
    def _detail_html(self) -> str:
        payload = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Electrical Engineer",
            "description": "Summary paragraph about the EMS role.",
            "responsibilities": "Code, test, and maintain EMS applications.",
            "qualifications": "BASIC REQUIREMENT: Degree in Engineering.",
            "educationRequirements": "Degree required.",
        }
        return f"""
        <html><body>
        <script type="application/ld+json">{json.dumps(payload)}</script>
        <dt>Remote job</dt><dd>No</dd>
        <dt>Telework eligible</dt><dd>Yes</dd>
        <dt>Salary</dt><dd>$104,502 - $140,188 per year</dd>
        <input type="hidden" value='{{"RemunerationMinimumAmount":"104502.00","RemunerationMaximumAmount":"140188.00"}}'/>
        </body></html>
        """

    def test_extracts_description_and_hybrid(self):
        fields = extract_detail_fields(self._detail_html())
        assert "Summary" in fields["description"]
        assert "Duties" in fields["description"]
        assert "Qualifications" in fields["description"]
        assert fields["work_arrangement_override"] == "HYBRID"
        assert "Telework eligible: Yes" in fields["work_arrangement_text"]

    def test_parse_raw_uses_detail_html(self):
        raw = _make_raw(_make_job())
        raw["raw_html"] = self._detail_html()
        result = parse_raw_posting(raw)
        assert result is not None
        assert "EMS" in result["description"] or "Engineering" in result["description"]
        assert result["salary"]["max_amount"] == "140188"
        assert result["work_arrangement"] == "HYBRID"


class TestUsajobsTaxonomy:
    def test_software_engineer_not_security(self):
        job = {"JobCategoryCode": [{"Name": "Information Technology Management"}]}
        fr, cr = extract_usajobs_taxonomy_raw(
            job, "Top Secret Security Software Engineer - DHA",
        )
        assert fr == "software engineer"
        assert cr == "Information Technology Management"
        result = parse_raw_posting(_make_raw(_make_job(
            Title="Top Secret Security Software Engineer - DHA",
            JobCategoryCode=[{"Name": "Information Technology Management", "Code": "2210"}],
        )))
        assert result["job_function_name"] == "Software Engineer"
        assert result["job_category_name"] == "Engineering & Technology"

    def test_mechanical_not_software(self):
        job = {"JobCategoryCode": [{"Name": "Mechanical Engineering"}]}
        fr, _ = extract_usajobs_taxonomy_raw(
            job, "Mechanical Engineer (Mechanical Design)",
        )
        assert fr == "research engineer"
        result = parse_raw_posting(_make_raw(_make_job(
            Title="Mechanical Engineer (Mechanical Design)",
            JobCategoryCode=[{"Name": "Mechanical Engineering", "Code": "0830"}],
        )))
        assert result["job_function_name"] == "Research Engineer"
        assert result["job_category_name"] == "Research & Science"

    def test_bare_engineer_uses_series_not_software(self):
        """제목에 bare engineer만 있으면 series fallback — Electronics → HW."""
        fr, _ = extract_usajobs_taxonomy_raw(
            {"JobCategoryCode": [{"Name": "Electronics Engineering"}]},
            "Lead Engineer, SSC/Det 5",
        )
        assert fr == "electronics engineer"
        result = parse_raw_posting(_make_raw(_make_job(
            Title="Lead Engineer, SSC/Det 5",
            JobCategoryCode=[{"Name": "Electronics Engineering", "Code": "0855"}],
        )))
        assert result["job_function_name"] == "Embedded / Hardware Engineer"
        assert result["job_category_name"] == "Engineering & Technology"

    def test_astronautical_research_engineer(self):
        result = parse_raw_posting(_make_raw(_make_job(
            Title="ODSC Astronautical Engineer",
            JobCategoryCode=[{"Name": "Aerospace Engineering", "Code": "0861"}],
        )))
        assert result["job_function_name"] == "Research Engineer"
        assert result["job_category_name"] == "Research & Science"


class TestParseUsLocation:
    def test_city_state(self):
        city, region, country = _parse_us_location("Woodlawn, Maryland")
        assert city == "Woodlawn"
        assert region == "Maryland"
        assert country == "United States"

    def test_remote(self):
        city, region, country = _parse_us_location("Remote")
        assert city == "Remote"
        assert country == "United States"


class TestParseRawPosting:
    def test_success(self):
        result = parse_raw_posting(_make_raw(_make_job()))
        assert result is not None
        assert result["source_name"] == "usajobs"
        assert result["title"].startswith("Top Secret")
        assert result["company"]["raw_name"] == "Social Security Administration"
        assert result["salary"]["currency_code"] == "USD"
        assert result["location"]["country_name"] == "United States"
        # GS 등급은 스키마 최상위 필드로 추가되지 않음
        assert "job_grade" not in result
        assert "security_clearance" not in result

    def test_empty_raw_text(self):
        raw = _make_raw(_make_job())
        raw["raw_text"] = ""
        assert parse_raw_posting(raw) is None

    def test_missing_title(self):
        assert parse_raw_posting(_make_raw(_make_job(Title=""))) is None
