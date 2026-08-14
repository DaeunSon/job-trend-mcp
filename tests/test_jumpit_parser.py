"""
crawlers/jumpit/parser.py 유닛 테스트.
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, timezone, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.crawlers.jumpit.parser import (
    _extract_career_level,
    _extract_company,
    _extract_description,
    _extract_education,
    _extract_employment_type,
    _extract_expires_at,
    _extract_location,
    _extract_posted_at,
    _extract_salary,
    _extract_skills,
    _extract_title,
    _extract_work_arrangement,
    parse_raw_posting,
    run_jumpit_parse,
)
from src.normalization.job_taxonomy import (
    extract_jumpit_taxonomy_raw,
    normalize_job_taxonomy,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처
# ---------------------------------------------------------------------------

def _make_detail_data(overrides: dict | None = None) -> dict:
    """상세 API result 딕셔너리 기본값."""
    base = {
        "id": 54447955,
        "title": "시니어 백엔드 개발자",
        "companyName": "점핏테크",
        "companyId": 1234567890,
        "companyHashId": "MTIzNDU2Nzg5MA==",
        "companyLogo": "https://cdn.jumpit.co.kr/logo.png",
        "repImage": "https://cdn.jumpit.co.kr/rep.png",
        "images": [],
        "tags": [
            {"id": 1, "name": "Python"},
            {"id": 2, "name": "Django"},
            {"id": 3, "name": "PostgreSQL"},
        ],
        "mainTask": "• Django 기반 백엔드 API 개발\n• 성능 최적화 및 코드 리뷰",
        "qualification": "• Python 실무 경험 5년 이상\n• Django 프레임워크 사용 경험",
        "preferredPoint": "• AWS 클라우드 경험 우대\n• MSA 경험 우대",
        "benefit": "• 자유로운 연차 사용\n• 재택근무 주 2회",
        "applicationProcess": "서류 → 기술 면접 → 최종 면접",
        "employment": False,
        "minCareer": 5,
        "maxCareer": 10,
        "location": "서울 강남구 테헤란로 123",
        "locationCode": 101010,
        "openedAt": "2026-07-01 00:00:00",
        "closedAt": "2026-08-31T23:59:59",
        "companyWebsite": "https://jumpit-tech.example.com",
        "salary": 700,
        "education": "무관",
        "categories": [{"id": 1, "name": "서버/백엔드 개발자"}],
        "companyFoundedAt": "2015년 3월 설립",
        "closed": False,
        "scrap": False,
        "reward": False,
    }
    if overrides:
        base.update(overrides)
    return base


def _make_raw_doc(detail_data: dict | None = None, overrides: dict | None = None) -> dict:
    """raw_job_postings 문서 딕셔너리."""
    data = detail_data or _make_detail_data()
    raw = {
        "id": "test-uuid-1234",
        "source_name": "jumpit",
        "source_job_id": str(data.get("id", 54447955)),
        "original_url": f"https://jumpit.saramin.co.kr/position/{data.get('id', 54447955)}",
        "raw_html": "",
        "raw_text": json.dumps(data, ensure_ascii=False),
        "collected_at": "2026-07-28T03:00:00+00:00",
        "parse_status": "PENDING",
        "parsed_job_posting_id": None,
    }
    if overrides:
        raw.update(overrides)
    return raw


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_extracts_title(self):
        assert _extract_title({"title": "백엔드 개발자"}) == "백엔드 개발자"

    def test_strips_whitespace(self):
        assert _extract_title({"title": "  백엔드  "}) == "백엔드"

    def test_missing_title_returns_empty(self):
        assert _extract_title({}) == ""

    def test_none_title_returns_empty(self):
        assert _extract_title({"title": None}) == ""


# ---------------------------------------------------------------------------
# _extract_company
# ---------------------------------------------------------------------------

class TestExtractCompany:
    def test_extracts_company_name(self):
        company = _extract_company({"companyName": "점핏테크"}, "jumpit")
        assert company.raw_name == "점핏테크"
        assert company.name == "점핏테크"  # alias 없으면 원문 그대로

    def test_extracts_website(self):
        company = _extract_company(
            {"companyName": "테스트", "companyWebsite": "https://test.com"},
            "jumpit",
        )
        assert company.website_url == "https://test.com"

    def test_none_website_stored_as_none(self):
        company = _extract_company({"companyName": "테스트", "companyWebsite": None}, "jumpit")
        assert company.website_url is None

    def test_empty_website_stored_as_none(self):
        company = _extract_company({"companyName": "테스트", "companyWebsite": ""}, "jumpit")
        assert company.website_url is None


# ---------------------------------------------------------------------------
# _extract_location
# ---------------------------------------------------------------------------

class TestExtractLocation:
    def test_extracts_city_and_region(self):
        loc = _extract_location({"location": "서울 강남구 테헤란로 123"}, "jumpit")
        assert loc.city_name == "서울 강남구"
        assert loc.region_name == "서울"
        assert loc.country_name == "대한민국"
        assert "서울" in loc.raw_text

    def test_handles_empty_location(self):
        loc = _extract_location({"location": ""}, "jumpit")
        assert loc.country_name == "대한민국"
        assert loc.raw_text == ""

    def test_missing_location_key(self):
        loc = _extract_location({}, "jumpit")
        assert loc.country_name == "대한민국"

    def test_single_word_location(self):
        loc = _extract_location({"location": "서울"}, "jumpit")
        assert loc.city_name == "서울"
        assert loc.region_name == "서울"


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------

class TestExtractDescription:
    def test_combines_all_sections(self):
        data = _make_detail_data()
        desc = _extract_description(data)
        assert "[주요업무]" in desc
        assert "[자격요건]" in desc
        assert "[우대사항]" in desc
        assert "[복지 및 혜택]" in desc
        assert "Django" in desc

    def test_skips_empty_sections(self):
        data = _make_detail_data({"preferredPoint": "", "benefit": None})
        desc = _extract_description(data)
        assert "[주요업무]" in desc
        assert "[우대사항]" not in desc
        assert "[복지 및 혜택]" not in desc

    def test_excludes_application_process(self):
        data = _make_detail_data({"applicationProcess": "서류 → 면접 → 합격"})
        desc = _extract_description(data)
        assert "채용절차" not in desc
        assert "서류 → 면접 → 합격" not in desc

    def test_empty_data_returns_empty_string(self):
        desc = _extract_description({})
        assert desc == ""


# ---------------------------------------------------------------------------
# _extract_career_level
# ---------------------------------------------------------------------------

class TestExtractCareerLevel:
    def test_career_range(self):
        career = _extract_career_level({"minCareer": 3, "maxCareer": 7, "employment": False})
        assert career.min_years == 3
        assert career.max_years == 7
        assert career.label == "Mid"

    def test_min_only(self):
        career = _extract_career_level({"minCareer": 5, "maxCareer": None})
        assert career.min_years == 5
        assert career.max_years is None
        assert career.label == "Senior"

    def test_entry_level_employment_true(self):
        career = _extract_career_level({"minCareer": None, "maxCareer": None, "employment": True})
        assert career.label == "Entry"
        assert career.min_years == 0

    def test_no_career_info(self):
        career = _extract_career_level({"minCareer": None, "maxCareer": None, "employment": False})
        assert career.label == "Any"

    def test_zero_min_career(self):
        career = _extract_career_level({"minCareer": 0, "maxCareer": 3})
        assert career.min_years == 0
        assert career.label == "Entry"


# ---------------------------------------------------------------------------
# _extract_employment_type
# ---------------------------------------------------------------------------

class TestExtractEmploymentType:
    def test_defaults_to_full_time(self):
        assert _extract_employment_type(_make_detail_data()) == "정규직"

    def test_detects_intern(self):
        data = _make_detail_data({"mainTask": "인턴십 업무를 수행합니다."})
        assert _extract_employment_type(data) == "인턴십"

    def test_detects_contract(self):
        data = _make_detail_data({"mainTask": "계약직으로 근무합니다."})
        assert _extract_employment_type(data) == "계약직"


# ---------------------------------------------------------------------------
# _extract_work_arrangement
# ---------------------------------------------------------------------------

class TestExtractWorkArrangement:
    def test_on_site_by_default(self):
        desc = "일반적인 회사 업무입니다."
        assert _extract_work_arrangement(desc) is None

    def test_detects_remote(self):
        desc = "재택근무 가능합니다."
        assert _extract_work_arrangement(desc) == "REMOTE"

    def test_detects_hybrid(self):
        desc = "하이브리드 근무 방식입니다."
        assert _extract_work_arrangement(desc) == "HYBRID"

    def test_remote_and_hybrid_returns_hybrid(self):
        desc = "재택근무 주 3일, 하이브리드 근무입니다."
        assert _extract_work_arrangement(desc) == "HYBRID"


# ---------------------------------------------------------------------------
# _extract_education
# ---------------------------------------------------------------------------

class TestExtractEducation:
    def test_moogwan_string_returns_moogwan(self):
        assert _extract_education({"education": "무관"}) == "무관"

    def test_education_name_moogwan(self):
        assert _extract_education({"education": 0, "educationName": "무관"}) == "무관"

    def test_education_code_zero_without_name(self):
        assert _extract_education({"education": 0}) == "무관"

    def test_education_name_specific(self):
        assert _extract_education({"education": 8, "educationName": "대학교졸업(4년) 이상"}) == "대학교졸업(4년) 이상"

    def test_none_returns_none(self):
        assert _extract_education({"education": None}) is None

    def test_empty_returns_none(self):
        assert _extract_education({"education": ""}) is None

    def test_specific_education_returned(self):
        assert _extract_education({"education": "대학교(4년)"}) == "대학교(4년)"


# ---------------------------------------------------------------------------
# _extract_skills
# ---------------------------------------------------------------------------

class TestExtractSkills:
    def test_extracts_all_tags(self):
        data = _make_detail_data()
        skills = _extract_skills(data, "jumpit")
        assert "Python" in skills
        assert "Django" in skills
        assert "PostgreSQL" in skills

    def test_deduplicates_tags(self):
        data = _make_detail_data({
            "tags": [
                {"id": 1, "name": "Python"},
                {"id": 1, "name": "Python"},
            ]
        })
        skills = _extract_skills(data, "jumpit")
        assert skills.count("Python") == 1

    def test_empty_tags_returns_empty(self):
        data = _make_detail_data({"tags": []})
        assert _extract_skills(data, "jumpit") == []

    def test_missing_tags_returns_empty(self):
        data = _make_detail_data()
        del data["tags"]
        assert _extract_skills(data, "jumpit") == []

    def test_prefers_tech_stacks_over_company_tags(self):
        data = {
            "techStacks": [
                {"stack": "Python"},
                {"stack": "Docker"},
            ],
            "tags": [
                {"id": "com_100", "name": "2,000억 이상 투자유치"},
                {"id": "281", "name": "급성장중"},
            ],
        }
        skills = _extract_skills(data, "jumpit")
        assert skills == ["Python", "Docker"]
        assert "급성장중" not in skills


# ---------------------------------------------------------------------------
# _extract_salary
# ---------------------------------------------------------------------------

class TestExtractSalary:
    def test_nonzero_salary_creates_salary_info(self):
        salary = _extract_salary({"salary": 700})
        assert salary.raw_text == "700만원"
        assert salary.currency_code == "KRW"
        assert salary.pay_period == "ANNUAL"

    def test_zero_salary_returns_empty(self):
        salary = _extract_salary({"salary": 0})
        assert salary.raw_text is None

    def test_none_salary_returns_empty(self):
        salary = _extract_salary({"salary": None})
        assert salary.raw_text is None

    def test_missing_salary_returns_empty(self):
        salary = _extract_salary({})
        assert salary.raw_text is None


# ---------------------------------------------------------------------------
# _extract_posted_at
# ---------------------------------------------------------------------------

class TestExtractPostedAt:
    def test_uses_opened_at(self):
        data = {"openedAt": "2026-07-01 00:00:00"}
        raw = {}
        assert _extract_posted_at(data, raw) == "2026-07-01"

    def test_falls_back_to_collected_at(self):
        data = {}
        raw = {"collected_at": "2026-07-28T03:00:00+00:00"}
        assert _extract_posted_at(data, raw) == "2026-07-28"

    def test_falls_back_to_today(self):
        data = {}
        raw = {}
        result = _extract_posted_at(data, raw)
        assert result == date.today().isoformat()


# ---------------------------------------------------------------------------
# _extract_expires_at
# ---------------------------------------------------------------------------

class TestExtractExpiresAt:
    def test_parses_iso_datetime(self):
        data = {"closedAt": "2026-08-31T23:59:59"}
        result = _extract_expires_at(data)
        assert result is not None
        assert "2026-08-31" in result

    def test_parses_datetime_with_space(self):
        data = {"closedAt": "2026-08-31 23:59:59"}
        result = _extract_expires_at(data)
        assert result is not None
        assert "2026-08-31" in result

    def test_none_returns_none(self):
        assert _extract_expires_at({"closedAt": None}) is None

    def test_missing_returns_none(self):
        assert _extract_expires_at({}) is None


# ---------------------------------------------------------------------------
# _infer_category
# ---------------------------------------------------------------------------

class TestInferCategory:
    def test_backend_maps_to_engineering(self):
        data = {"categories": [{"id": 1, "name": "서버/백엔드 개발자"}]}
        func_raw, cat_raw = extract_jumpit_taxonomy_raw(data)
        _, job_category = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_category == "Engineering & Technology"

    def test_ai_maps_to_data_analytics(self):
        data = {"categories": [{"id": 8, "name": "인공지능/머신러닝"}]}
        func_raw, cat_raw = extract_jumpit_taxonomy_raw(data)
        _, job_category = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_category == "Data & Analytics"

    def test_empty_categories_returns_empty(self):
        func_raw, cat_raw = extract_jumpit_taxonomy_raw({"categories": []})
        _, job_category = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_category == ""

    def test_missing_categories_returns_empty(self):
        func_raw, cat_raw = extract_jumpit_taxonomy_raw({})
        _, job_category = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_category == ""


# ---------------------------------------------------------------------------
# _infer_function
# ---------------------------------------------------------------------------

class TestInferFunction:
    def test_backend_category_maps_to_backend_engineer(self):
        data = {"categories": [{"id": 1, "name": "서버/백엔드 개발자"}], "title": ""}
        func_raw, cat_raw = extract_jumpit_taxonomy_raw(data)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "Backend Engineer"

    def test_ai_category_maps_to_ml_engineer(self):
        data = {"categories": [{"id": 8, "name": "인공지능/머신러닝"}], "title": ""}
        func_raw, cat_raw = extract_jumpit_taxonomy_raw(data)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "Machine Learning Engineer"

    def test_fallback_by_title(self):
        data = {
            "categories": [],
            "title": "프론트엔드 개발자",
            "mainTask": "", "qualification": "",
            "preferredPoint": "", "benefit": "",
        }
        func_raw, cat_raw = extract_jumpit_taxonomy_raw(data)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "Frontend Engineer"

    def test_devops_title_fallback(self):
        data = {
            "categories": [],
            "title": "DevOps 엔지니어",
            "mainTask": "", "qualification": "",
            "preferredPoint": "", "benefit": "",
        }
        func_raw, cat_raw = extract_jumpit_taxonomy_raw(data)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "DevOps / Platform Engineer"

    def test_empty_returns_empty_string(self):
        data = {
            "categories": [],
            "title": "알수없는 직종",
            "mainTask": "", "qualification": "",
            "preferredPoint": "", "benefit": "",
        }
        func_raw, cat_raw = extract_jumpit_taxonomy_raw(data)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == ""


# ---------------------------------------------------------------------------
# parse_raw_posting (통합)
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def test_returns_job_posting_dict(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)

        assert result is not None
        assert result["source_name"] == "jumpit"
        assert result["source_job_id"] == "54447955"
        assert result["title"] == "시니어 백엔드 개발자"
        assert "company" in result
        assert result["company"]["raw_name"] == "점핏테크"

    def test_skills_populated(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        skill_names = [s["raw_text"] for s in result["skills"]]
        assert "Python" in skill_names
        assert "Django" in skill_names

    def test_career_level_populated(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        career = result["career_level"]
        assert career["min_years"] == 5
        assert career["max_years"] == 10

    def test_location_populated(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        loc = result["location"]
        assert loc["city_name"] == "서울 강남구"
        assert loc["country_name"] == "대한민국"

    def test_salary_populated(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["salary"]["raw_text"] == "700만원"

    def test_education_moogwan_preserved(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["education_level"] == "무관"

    def test_expires_at_populated(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["expires_at"] is not None
        assert "2026-08-31" in result["expires_at"]

    def test_application_process_not_in_description(self):
        """채용절차는 스키마에 없으므로 description에 포함되지 않아야 한다."""
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        assert "서류 →" not in result["description"]

    def test_returns_none_for_empty_raw_text(self):
        raw = _make_raw_doc(overrides={"raw_text": ""})
        result = parse_raw_posting(raw)
        assert result is None

    def test_returns_none_for_invalid_json(self):
        raw = _make_raw_doc(overrides={"raw_text": "not valid json"})
        result = parse_raw_posting(raw)
        assert result is None

    def test_job_function_from_categories(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["job_function_name"] == "Backend Engineer"

    def test_job_category_from_categories(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["job_category_name"] == "Engineering & Technology"

    def test_source_refs_populated(self):
        raw = _make_raw_doc()
        result = parse_raw_posting(raw)
        assert result is not None
        refs = result["source_refs"]
        assert len(refs) == 1
        assert refs[0]["source_name"] == "jumpit"

    def test_work_arrangement_hybrid_for_remote_mention(self):
        detail_data = _make_detail_data({"benefit": "재택근무 주 2회 하이브리드 근무"})
        raw = _make_raw_doc(detail_data=detail_data)
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["work_arrangement"] == "HYBRID"


# ---------------------------------------------------------------------------
# run_jumpit_parse (파일 기반 통합)
# ---------------------------------------------------------------------------

class TestRunJumpitParse:
    def test_parses_pending_files(self):
        detail_data = _make_detail_data()
        raw_doc = _make_raw_doc(detail_data=detail_data)
        raw_doc["parse_status"] = "PENDING"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            raw_dir = tmp_path / "raw_job_postings" / "2026-07-28"
            raw_dir.mkdir(parents=True)
            raw_file = raw_dir / "jumpit_Backend_Engineer.json"
            raw_file.write_text(
                json.dumps([raw_doc], ensure_ascii=False),
                encoding="utf-8",
            )

            run_jumpit_parse(crawl_date="2026-07-28", base_dir=tmpdir)

            # raw 파일의 parse_status가 PARSED로 업데이트됐는지 확인
            # (단건이면 dict로 다시 쓸 수 있음 — _read_json_list 로 정규화)
            from src.storage.json_writer import _read_json_list, build_document_path

            updated = _read_json_list(raw_file)
            assert updated[0]["parse_status"] == "PARSED"
            assert updated[0]["parsed_job_posting_id"] is not None

            # job_postings: {job_function}/{source}/{date}_{source_job_id}.json
            parsed_path = build_document_path(
                collection_name="job_postings",
                job_function_name="Backend Engineer",
                source_name="jumpit",
                crawl_date="2026-07-28",
                source_job_id="54447955",
                base_dir=tmpdir,
            )
            assert parsed_path.exists()

    def test_skips_already_parsed(self):
        detail_data = _make_detail_data()
        raw_doc = _make_raw_doc(detail_data=detail_data)
        raw_doc["parse_status"] = "PARSED"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            raw_dir = tmp_path / "raw_job_postings" / "2026-07-28"
            raw_dir.mkdir(parents=True)
            raw_file = raw_dir / "jumpit_test.json"
            raw_file.write_text(
                json.dumps([raw_doc], ensure_ascii=False),
                encoding="utf-8",
            )

            run_jumpit_parse(crawl_date="2026-07-28", base_dir=tmpdir)

            # job_postings 파일이 생성되지 않아야 한다
            parsed_dir = tmp_path / "job_postings"
            assert not parsed_dir.exists()

    def test_handles_failed_parse_gracefully(self):
        """파싱 실패 시 FAILED로 업데이트되고 배치는 계속된다."""
        bad_raw_doc = _make_raw_doc(overrides={"raw_text": "invalid json"})
        bad_raw_doc["parse_status"] = "PENDING"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            raw_dir = tmp_path / "raw_job_postings" / "2026-07-28"
            raw_dir.mkdir(parents=True)
            raw_file = raw_dir / "jumpit_test.json"
            raw_file.write_text(
                json.dumps([bad_raw_doc], ensure_ascii=False),
                encoding="utf-8",
            )

            run_jumpit_parse(crawl_date="2026-07-28", base_dir=tmpdir)

            from src.storage.json_writer import _read_json_list

            updated = _read_json_list(raw_file)
            assert updated[0]["parse_status"] == "FAILED"
