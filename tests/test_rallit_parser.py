"""
crawlers/rallit/parser.py 유닛 테스트.

JSON 파싱 / 추출 로직을 네트워크 없이 테스트한다.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.crawlers.rallit.parser import (
    _build_work_arrangement_text,
    _normalize_date,
    _parse_career,
    _parse_salary,
    _parse_location,
    _resolve_posted_at,
    _strip_html,
    extract_detail_fields,
    parse_raw_posting,
)
from src.models.schemas import SalaryInfo


# ---------------------------------------------------------------------------
# 테스트 픽스처 / 헬퍼
# ---------------------------------------------------------------------------

def _make_detail_json(
    position_id: int = 4233,
    title: str = "[미리캔버스] 시니어 백엔드 개발자",
    company_name: str = "미리디",
    description: str = "<p>회사 소개</p>",
    responsibilities: str = "<ul><li>백엔드 서비스 개발</li></ul>",
    basic_qualifications: str = "<ul><li>Java, Spring 경험 3년 이상</li></ul>",
    preferred_qualifications: str = "<ul><li>AWS 경험 우대</li></ul>",
    benefits: str = "<p>자유로운 연차 사용</p>",
    salary_type: str = "UNKNOWN_SALARY",
    minimum_salary: object = None,
    job_code: str = "BACKEND_DEVELOPER",
    job_name: str = "백엔드/서버 개발자",
    job_level: str = "IRRELEVANT",
    job_levels: list[str] | None = None,
    address_main: str = "서울 구로구 디지털로31길 12",
    address_region: dict | None = None,
    started_at: str = "1970-01-01",
    ended_at: str = "9999-12-31",
    homepage: str = "https://example.com",
    skills: list[str] | None = None,
    company_tags: list[str] | None = None,
    approved_at: str = "",
) -> dict:
    return {
        "id": position_id,
        "title": title,
        "companyName": company_name,
        "companyId": 293,
        "companyLogo": "https://cdn.rallit.com/logo.png",
        "companyRepresentativeImages": [],
        "companyTags": company_tags if company_tags is not None else ["코드 리뷰", "수평적 조직"],
        "companyDescription": "<p>좋은 회사</p>",
        "description": description,
        "responsibilities": responsibilities,
        "basicQualifications": basic_qualifications,
        "preferredQualifications": preferred_qualifications,
        "benefits": benefits,
        "additionalComments": "",
        "salaryType": salary_type,
        "minimumSalary": minimum_salary,
        "jobs": [{"code": job_code, "name": job_name}],
        "jobLevel": job_level,
        "jobLevels": job_levels if job_levels is not None else ["SENIOR", "MIDDLE"],
        "jobSkillKeywords": skills if skills is not None else ["Java", "Spring Boot", "AWS"],
        "addressMain": address_main,
        "addressDetail": "8층",
        "addressBuildingName": "빌딩",
        "addressRegion": address_region or {"code": "GURO_GASAN", "name": "구로/가산"},
        "zipCode": "",
        "startedAt": started_at,
        "endedAt": ended_at,
        "homepage": homepage,
        "latitude": 37.4853,
        "longitude": 126.8949,
        "status": {"code": "HIRING", "name": "모집 중"},
        "isAlwaysHiring": True,
        "isBookmarked": False,
        "isPartner": False,
        "partnerLogo": "",
        "joinReward": "0",
        "freeQuestions": [],
        "positionSteps": ["서류 검토", "1차인터뷰"],
        "approvedAt": approved_at,
        "bookmarkCount": 1,
        "submitStatus": "NONE",
        "content": "",
    }


def _make_raw_posting(detail_json: dict) -> dict:
    """raw_job_postings 문서 형식으로 변환."""
    return {
        "id": "test-uuid-1234",
        "source_name": "rallit",
        "source_job_id": str(detail_json["id"]),
        "original_url": f"https://www.rallit.com/positions/{detail_json['id']}",
        "raw_html": "",
        "raw_text": json.dumps(detail_json, ensure_ascii=False),
        "collected_at": "2026-07-29T00:00:00+00:00",
        "parse_status": "PENDING",
        "parsed_job_posting_id": None,
    }


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------

class TestStripHtml:
    def test_removes_simple_tags(self):
        result = _strip_html("<p>Hello World</p>")
        assert "Hello World" in result
        assert "<p>" not in result

    def test_handles_list_items(self):
        result = _strip_html("<ul><li>항목1</li><li>항목2</li></ul>")
        assert "항목1" in result
        assert "항목2" in result

    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_none_returns_empty(self):
        assert _strip_html(None) == ""

    def test_nested_tags(self):
        result = _strip_html("<p><strong>굵은글씨</strong> 일반텍스트</p>")
        assert "굵은글씨" in result
        assert "일반텍스트" in result


# ---------------------------------------------------------------------------
# _normalize_date
# ---------------------------------------------------------------------------

class TestNormalizeDate:
    def test_standard_date(self):
        assert _normalize_date("2026-07-29") == "2026-07-29"

    def test_dot_separator(self):
        assert _normalize_date("2026.07.29") == "2026-07-29"

    def test_slash_separator(self):
        assert _normalize_date("2026/07/29") == "2026-07-29"

    def test_single_digit_month_day(self):
        assert _normalize_date("2026-7-5") == "2026-07-05"

    def test_empty_string(self):
        assert _normalize_date("") == ""

    def test_no_date_pattern(self):
        assert _normalize_date("채용 시 마감") == ""


class TestResolvePostedAt:
    def test_uses_started_at_when_valid(self):
        assert _resolve_posted_at("2026-07-22", "") == "2026-07-22"

    def test_falls_back_to_approved_at_for_placeholder(self):
        assert _resolve_posted_at("1970-01-01", "2025-05-08 09:46:42") == "2025-05-08"

    def test_returns_none_when_both_missing(self):
        assert _resolve_posted_at("", "") is None


class TestBuildWorkArrangementText:
    def test_combines_tags_and_description(self):
        text = _build_work_arrangement_text(
            ["재택 근무", "유연 근무제"],
            "[복지]\n주2회 사무실 대면 출근",
        )
        assert "재택 근무" in text
        assert "주2회" in text


# ---------------------------------------------------------------------------
# _parse_career
# ---------------------------------------------------------------------------

class TestParseCareer:
    def test_senior_returns_correct_min(self):
        min_y, max_y, raw = _parse_career("SENIOR", ["SENIOR"])
        assert min_y == 7
        assert max_y is None

    def test_irrelevant_returns_none(self):
        min_y, max_y, raw = _parse_career("IRRELEVANT", ["IRRELEVANT"])
        assert min_y is None
        assert max_y is None
        assert raw == ""

    def test_multiple_levels_gives_range(self):
        min_y, max_y, raw = _parse_career("IRRELEVANT", ["JUNIOR", "MIDDLE"])
        assert min_y == 1
        assert max_y == 7
        assert "JUNIOR" in raw
        assert "MIDDLE" in raw

    def test_entry_level(self):
        min_y, max_y, raw = _parse_career("ENTRY", ["ENTRY"])
        assert min_y == 0
        assert max_y == 0

    def test_empty_levels(self):
        min_y, max_y, raw = _parse_career("", [])
        assert min_y is None
        assert max_y is None
        assert raw == ""


# ---------------------------------------------------------------------------
# _parse_salary
# ---------------------------------------------------------------------------

class TestParseSalary:
    def test_unknown_salary_returns_empty(self):
        result = _parse_salary("UNKNOWN_SALARY", None)
        assert isinstance(result, SalaryInfo)
        assert result.min_amount is None
        assert result.pay_period is None

    def test_annual_salary_type(self):
        result = _parse_salary("ANNUAL_SALARY", 5000)
        assert result.pay_period == "ANNUAL"
        assert result.min_amount == "5000"
        assert result.currency_code == "KRW"

    def test_zero_minimum_treated_as_empty(self):
        result = _parse_salary("ANNUAL_SALARY", 0)
        assert result.min_amount is None

    def test_empty_string_minimum(self):
        result = _parse_salary("UNKNOWN_SALARY", "")
        assert result.min_amount is None


# ---------------------------------------------------------------------------
# _parse_location
# ---------------------------------------------------------------------------

class TestParseLocation:
    def test_address_main_takes_priority(self):
        result = _parse_location(
            "서울 구로구 디지털로31길 12",
            {"code": "GURO_GASAN", "name": "구로/가산"},
        )
        assert result == "서울 구로구 디지털로31길 12"

    def test_falls_back_to_region_name(self):
        result = _parse_location(None, {"code": "GANGNAM", "name": "강남"})
        assert result == "강남"

    def test_both_none_returns_empty(self):
        assert _parse_location(None, None) == ""

    def test_empty_address_main_falls_back(self):
        result = _parse_location("", {"code": "SEOUL", "name": "서울"})
        assert result == "서울"


# ---------------------------------------------------------------------------
# extract_detail_fields
# ---------------------------------------------------------------------------

class TestExtractDetailFields:
    def test_extracts_title_and_company(self):
        detail = _make_detail_json(title="백엔드 개발자", company_name="테스트 회사")
        fields = extract_detail_fields(detail)
        assert fields["title"] == "백엔드 개발자"
        assert fields["company"] == "테스트 회사"

    def test_extracts_skills(self):
        detail = _make_detail_json(skills=["Python", "Django", "PostgreSQL"])
        fields = extract_detail_fields(detail)
        assert fields["skills"] == ["Python", "Django", "PostgreSQL"]

    def test_extracts_job_code(self):
        detail = _make_detail_json(job_code="FRONTEND_DEVELOPER", job_name="프론트엔드/웹퍼블리셔")
        fields = extract_detail_fields(detail)
        assert fields["job_code"] == "FRONTEND_DEVELOPER"

    def test_description_combines_all_html_fields(self):
        detail = _make_detail_json(
            description="<p>회사 소개</p>",
            responsibilities="<p>주요 업무</p>",
            basic_qualifications="<p>자격요건</p>",
        )
        fields = extract_detail_fields(detail)
        desc = fields["description"]
        assert "회사 소개" in desc
        assert "주요 업무" in desc
        assert "자격요건" in desc

    def test_always_hiring_has_no_expires_at(self):
        detail = _make_detail_json(ended_at="9999-12-31")
        fields = extract_detail_fields(detail)
        assert fields["expires_at"] is None

    def test_normal_end_date_parsed(self):
        detail = _make_detail_json(ended_at="2026-08-31")
        fields = extract_detail_fields(detail)
        assert fields["expires_at"] == "2026-08-31"

    def test_location_uses_address_main(self):
        detail = _make_detail_json(address_main="서울 강남구 테헤란로 123")
        fields = extract_detail_fields(detail)
        assert "서울 강남구" in fields["location_raw"]

    def test_company_website_extracted(self):
        detail = _make_detail_json(homepage="https://miridih.com")
        fields = extract_detail_fields(detail)
        assert fields["company_website"] == "https://miridih.com"

    def test_empty_homepage_is_none(self):
        detail = _make_detail_json(homepage="")
        fields = extract_detail_fields(detail)
        assert fields["company_website"] is None

    def test_posted_at_from_approved_at_when_started_placeholder(self):
        detail = _make_detail_json(
            started_at="1970-01-01",
            approved_at="2025-05-08 09:46:42",
        )
        fields = extract_detail_fields(detail)
        assert fields["posted_at"] == "2025-05-08"


# ---------------------------------------------------------------------------
# parse_raw_posting
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def test_returns_job_posting_dict(self):
        detail = _make_detail_json()
        raw = _make_raw_posting(detail)
        result = parse_raw_posting(raw)

        assert result is not None
        assert result["source_name"] == "rallit"
        assert result["source_job_id"] == "4233"
        assert result["title"] == "[미리캔버스] 시니어 백엔드 개발자"
        assert isinstance(result["skills"], list)
        assert isinstance(result["id"], str)

    def test_missing_raw_text_returns_none(self):
        raw = {
            "source_name": "rallit",
            "source_job_id": "9999",
            "original_url": "https://www.rallit.com/positions/9999",
            "raw_html": "",
            "raw_text": "",
        }
        result = parse_raw_posting(raw)
        assert result is None

    def test_invalid_json_returns_none(self):
        raw = {
            "source_name": "rallit",
            "source_job_id": "9999",
            "original_url": "https://www.rallit.com/positions/9999",
            "raw_html": "",
            "raw_text": "not-valid-json",
        }
        result = parse_raw_posting(raw)
        assert result is None

    def test_missing_title_returns_none(self):
        detail = _make_detail_json(title="")
        raw = _make_raw_posting(detail)
        result = parse_raw_posting(raw)
        assert result is None

    def test_job_function_resolved_from_job_code(self):
        detail = _make_detail_json(job_code="BACKEND_DEVELOPER")
        raw = _make_raw_posting(detail)
        result = parse_raw_posting(raw)
        assert result is not None
        # job_function_name 이 taxonomy 값으로 정규화되어야 함
        assert "job_function_name" in result

    def test_skills_in_output(self):
        detail = _make_detail_json(skills=["Python", "FastAPI"])
        raw = _make_raw_posting(detail)
        result = parse_raw_posting(raw)
        assert result is not None
        skill_names = [s.get("raw_text") or s.get("canonical_name") for s in result.get("skills", [])]
        assert "Python" in skill_names

    def test_frontend_developer_code(self):
        detail = _make_detail_json(
            job_code="FRONTEND_DEVELOPER",
            job_name="프론트엔드/웹퍼블리셔",
            title="프론트엔드 개발자 모집",
        )
        raw = _make_raw_posting(detail)
        result = parse_raw_posting(raw)
        assert result is not None

    def test_unknown_job_code_does_not_crash(self):
        detail = _make_detail_json(job_code="UNKNOWN_CODE_XYZ")
        raw = _make_raw_posting(detail)
        result = parse_raw_posting(raw)
        assert result is not None  # 크래시 없이 처리

    def test_company_website_in_output(self):
        detail = _make_detail_json(homepage="https://example.com")
        raw = _make_raw_posting(detail)
        result = parse_raw_posting(raw)
        assert result is not None
        company = result.get("company", {})
        assert company.get("website_url") == "https://example.com"

    def test_hybrid_work_arrangement_with_partial_office_days(self):
        detail = _make_detail_json(
            position_id=3461,
            title="Nest.js / Node.js 백엔드 개발자",
            company_name="주식회사 다이노즈",
            company_tags=["재택 근무", "유연 근무제"],
            benefits=(
                "<ul><li>개발팀은 주2회 사무실 대면 출근</li>"
                "<li>유연한 재택근무</li></ul>"
            ),
            started_at="1970-01-01",
            approved_at="2025-05-08 09:46:42",
        )
        raw = _make_raw_posting(detail)
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["posted_at"] == "2025-05-08"
        assert result["work_arrangement"] == "HYBRID"
