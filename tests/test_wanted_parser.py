"""
crawlers/wanted/parser.py 유닛 테스트.
"""
from __future__ import annotations

import json
import pytest
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

from src.crawlers.wanted.parser import (
    parse_raw_posting,
    run_wanted_parse,
    _extract_title,
    _extract_company,
    _extract_location,
    _extract_description,
    _extract_career_level,
    _extract_employment_type,
    _extract_work_arrangement,
    _extract_skills,
    _extract_salary,
    _extract_expires_at,
)
from src.normalization.job_taxonomy import (
    extract_wanted_taxonomy_raw,
    normalize_job_taxonomy,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처
# ---------------------------------------------------------------------------

def _make_job(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 12345,
        "position": "백엔드 개발자 (Python/Django)",
        "status": "active",
        "company": {
            "id": 1,
            "name": "테스트컴퍼니",
            "industry_name": "IT, 컨텐츠",
        },
        "address": {
            "location": "서울",
            "district": "강남구",
            "country": "한국",
            "full_location": "서울 강남구 테헤란로 123",
            "location_key": "seoul",
            "district_key": "seoul.gangnam-gu",
        },
        "annual_from": 3,
        "annual_to": 7,
        "due_time": "2026-08-31T23:59:59+09:00",
        "skill_tags": [
            {"id": 1, "title": "Python"},
            {"id": 2, "title": "Django"},
            {"id": 3, "title": "PostgreSQL"},
        ],
        "category_tags": [{"parent_id": 518, "id": 872}],
        "company_tags": [],
        "detail": {
            "intro": "우리는 좋은 회사입니다.",
            "main_tasks": "백엔드 서버 개발 및 운영",
            "requirements": "Python 3년 이상, Django 경험",
            "preferred_points": "AWS 경험자 우대",
            "benefits": "4대 보험, 점심 제공",
        },
        "reward": {"formatted_total": "100만원"},
        "like_count": 5,
        "is_like": False,
    }
    if overrides:
        base.update(overrides)
    return base


def _make_raw(
    job: dict[str, Any] | None = None,
    source_job_id: str = "12345",
    parse_status: str = "PENDING",
) -> dict[str, Any]:
    if job is None:
        job = _make_job()
    api_response = {"job": job, "application": None}
    return {
        "id": "raw-uuid-001",
        "source_name": "wanted",
        "source_job_id": source_job_id,
        "original_url": f"https://www.wanted.co.kr/wd/{source_job_id}",
        "raw_html": "",
        "raw_text": json.dumps(api_response, ensure_ascii=False),
        "collected_at": "2026-07-27T09:00:00+00:00",
        "parse_status": parse_status,
        "parsed_job_posting_id": None,
    }


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_basic(self):
        job = _make_job()
        assert _extract_title(job) == "백엔드 개발자 (Python/Django)"

    def test_strips_whitespace(self):
        job = _make_job({"position": "  프론트엔드 개발자  "})
        assert _extract_title(job) == "프론트엔드 개발자"

    def test_empty_position(self):
        job = _make_job({"position": ""})
        assert _extract_title(job) == ""

    def test_missing_position(self):
        job = _make_job()
        del job["position"]
        assert _extract_title(job) == ""


# ---------------------------------------------------------------------------
# _extract_company
# ---------------------------------------------------------------------------

class TestExtractCompany:
    def test_basic(self):
        job = _make_job()
        company = _extract_company(job, "wanted")
        assert company.raw_name == "테스트컴퍼니"
        assert company.industry_name == "IT, 컨텐츠"

    def test_canonical_name_fallback(self):
        job = _make_job()
        with patch("src.normalization.alias_resolver.resolve", return_value="테스트컴퍼니"):
            company = _extract_company(job, "wanted")
        assert company.name == "테스트컴퍼니"

    def test_missing_company(self):
        job = _make_job()
        job["company"] = {}
        company = _extract_company(job, "wanted")
        assert company.raw_name == ""

    def test_no_industry(self):
        job = _make_job()
        job["company"]["industry_name"] = None
        company = _extract_company(job, "wanted")
        assert company.industry_name is None


# ---------------------------------------------------------------------------
# _extract_location
# ---------------------------------------------------------------------------

class TestExtractLocation:
    def test_basic(self):
        job = _make_job()
        location = _extract_location(job, "wanted")
        assert location.city_name == "서울 강남구"
        assert location.region_name == "서울"
        assert location.country_name == "대한민국"

    def test_raw_text_contains_full_location(self):
        job = _make_job()
        location = _extract_location(job, "wanted")
        assert "서울" in location.raw_text or "강남" in location.raw_text

    def test_missing_address(self):
        job = _make_job()
        job["address"] = {}
        location = _extract_location(job, "wanted")
        assert location.country_name == "대한민국"

    def test_country_default(self):
        job = _make_job()
        job["address"]["country"] = None
        location = _extract_location(job, "wanted")
        # full_location 기반 parse_korean_location 사용
        assert location.country_name == "대한민국"


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------

class TestExtractDescription:
    def test_all_parts_present(self):
        job = _make_job()
        desc = _extract_description(job)
        assert "우리는 좋은 회사입니다" in desc
        assert "백엔드 서버 개발" in desc
        assert "Python 3년 이상" in desc
        assert "AWS 경험자" in desc
        assert "4대 보험" in desc

    def test_missing_intro(self):
        job = _make_job()
        job["detail"]["intro"] = ""
        desc = _extract_description(job)
        assert "백엔드 서버 개발" in desc
        assert desc.strip() != ""

    def test_all_empty_returns_empty(self):
        job = _make_job()
        job["detail"] = {
            "intro": "", "main_tasks": "", "requirements": "",
            "preferred_points": "", "benefits": "",
        }
        desc = _extract_description(job)
        assert desc == ""


# ---------------------------------------------------------------------------
# _extract_career_level
# ---------------------------------------------------------------------------

class TestExtractCareerLevel:
    def test_range(self):
        job = _make_job({"annual_from": 3, "annual_to": 7})
        cl = _extract_career_level(job)
        assert cl.min_years == 3
        assert cl.max_years == 7
        assert cl.label == "Mid"

    def test_zero_from_is_entry(self):
        job = _make_job({"annual_from": 0, "annual_to": None})
        cl = _extract_career_level(job)
        assert cl.label == "Entry"
        assert cl.min_years == 0

    def test_no_limits_is_no_restriction(self):
        job = _make_job({"annual_from": None, "annual_to": None})
        cl = _extract_career_level(job)
        assert cl.label == "Any"
        assert cl.min_years is None
        assert cl.max_years is None

    def test_min_only(self):
        job = _make_job({"annual_from": 5, "annual_to": None})
        cl = _extract_career_level(job)
        assert cl.min_years == 5
        assert cl.label == "Senior"

    def test_max_only(self):
        job = _make_job({"annual_from": None, "annual_to": 10})
        cl = _extract_career_level(job)
        assert cl.max_years == 10


# ---------------------------------------------------------------------------
# _extract_employment_type
# ---------------------------------------------------------------------------

class TestExtractEmploymentType:
    def test_default_is_fulltime(self):
        job = _make_job()
        assert _extract_employment_type(job) == "정규직"

    def test_intern_tag_detected(self):
        job = _make_job()
        job["company_tags"] = [{"id": 1, "title": "인턴십", "kind_title": "EMPLOYMENT"}]
        assert _extract_employment_type(job) == "인턴십"

    def test_contract_tag_detected(self):
        job = _make_job()
        job["company_tags"] = [{"id": 2, "title": "계약직", "kind_title": "EMPLOYMENT"}]
        assert _extract_employment_type(job) == "계약직"


# ---------------------------------------------------------------------------
# _extract_work_arrangement
# ---------------------------------------------------------------------------

class TestExtractWorkArrangement:
    def test_onsite_without_explicit_phrase(self):
        assert _extract_work_arrangement("오피스 근무입니다.") is None

    def test_remote_detection(self):
        assert _extract_work_arrangement("풀 리모트 근무 가능합니다.") == "REMOTE"

    def test_hybrid_detection(self):
        assert _extract_work_arrangement("하이브리드 근무를 지원합니다.") == "HYBRID"

    def test_reotework_with_hybrid_wins(self):
        desc = "재택근무 가능. 하이브리드 형태로 운영합니다."
        assert _extract_work_arrangement(desc) == "HYBRID"

    def test_empty_description(self):
        assert _extract_work_arrangement("") is None


# ---------------------------------------------------------------------------
# _extract_skills
# ---------------------------------------------------------------------------

class TestExtractSkills:
    def test_skill_tags_extracted(self):
        job = _make_job()
        skills = _extract_skills(job, "", "wanted")
        names = {s.raw_text for s in skills}
        assert "Python" in names
        assert "Django" in names

    def test_no_duplicates(self):
        job = _make_job()
        job["skill_tags"] = [
            {"id": 1, "title": "Python"},
            {"id": 2, "title": "Python"},   # 중복
        ]
        skills = _extract_skills(job, "", "wanted")
        names = [s.raw_text for s in skills]
        assert names.count("Python") == 1

    def test_description_augmentation(self):
        job = _make_job({"skill_tags": []})
        desc = "React와 TypeScript를 주로 사용합니다."
        skills = _extract_skills(job, desc, "wanted")
        names = {s.raw_text.lower() for s in skills}
        assert "react" in names or "typescript" in names

    def test_empty_skill_tags(self):
        job = _make_job({"skill_tags": []})
        skills = _extract_skills(job, "일반 텍스트 설명", "wanted")
        assert isinstance(skills, list)


# ---------------------------------------------------------------------------
# _extract_salary
# ---------------------------------------------------------------------------

class TestExtractSalary:
    def test_returns_salary_info_with_none(self):
        job = _make_job()
        salary = _extract_salary(job)
        assert salary.raw_text is None

    def test_min_max_none(self):
        salary = _extract_salary(_make_job())
        assert salary.min_amount is None
        assert salary.max_amount is None


# ---------------------------------------------------------------------------
# _extract_expires_at
# ---------------------------------------------------------------------------

class TestExtractExpiresAt:
    def test_valid_due_time(self):
        job = _make_job({"due_time": "2026-08-31T23:59:59+09:00"})
        result = _extract_expires_at(job)
        assert result is not None
        assert "2026" in result

    def test_null_due_time(self):
        job = _make_job({"due_time": None})
        assert _extract_expires_at(job) is None


# ---------------------------------------------------------------------------
# _infer_category
# ---------------------------------------------------------------------------

class TestInferCategory:
    def test_it_contents_maps_to_engineering(self):
        job = _make_job()
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        _, job_category = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_category == "Engineering & Technology"

    def test_unknown_industry_maps_to_other(self):
        # 직무 키워드가 있으면 function→category 유도가 우선하므로,
        # 업종만 미지인 경우를 보려면 비기술 포지션을 써야 한다.
        job = _make_job({"position": "일반 사무 지원"})
        job["company"]["industry_name"] = "알 수 없는 업종"
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        _, job_category = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_category == "Other"

    def test_finance_maps_to_finance(self):
        job = _make_job()
        job["company"]["industry_name"] = "금융, 보험, 투자"
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        _, job_category = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_category == "Finance & Accounting"


# ---------------------------------------------------------------------------
# _infer_function
# ---------------------------------------------------------------------------

class TestInferFunction:
    def test_backend_position(self):
        job = _make_job({"position": "백엔드 개발자 (Python)"})
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "Backend Engineer"

    def test_frontend_position(self):
        job = _make_job({"position": "프론트엔드 개발자 React"})
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "Frontend Engineer"

    def test_ml_position(self):
        job = _make_job({"position": "머신러닝 엔지니어 모집"})
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "Machine Learning Engineer"

    def test_data_engineer(self):
        job = _make_job({"position": "데이터 엔지니어"})
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "Data Engineer"

    def test_unknown_returns_empty(self):
        job = _make_job({"position": "비서 및 행정 담당자"})
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert isinstance(job_function, str)

    def test_devops(self):
        job = _make_job({"position": "DevOps 엔지니어 채용"})
        func_raw, cat_raw = extract_wanted_taxonomy_raw(job)
        job_function, _ = normalize_job_taxonomy(func_raw, cat_raw)
        assert job_function == "DevOps / Platform Engineer"


# ---------------------------------------------------------------------------
# parse_raw_posting (통합)
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def test_success_returns_dict(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["source_name"] == "wanted"
        assert result["source_job_id"] == "12345"

    def test_title_extracted(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        assert result["title"] == "백엔드 개발자 (Python/Django)"

    def test_company_extracted(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        assert result["company"]["raw_name"] == "테스트컴퍼니"

    def test_location_extracted(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        assert result["location"]["country_name"] == "대한민국"

    def test_skills_extracted(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        skill_texts = {s["raw_text"] for s in result["skills"]}
        assert "Python" in skill_texts

    def test_source_ref_present(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        assert len(result["source_refs"]) == 1
        assert result["source_refs"][0]["source_name"] == "wanted"

    def test_expires_at_parsed(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        assert result["expires_at"] is not None
        assert "2026" in result["expires_at"]

    def test_missing_raw_text_returns_none(self):
        raw = _make_raw()
        raw["raw_text"] = ""
        result = parse_raw_posting(raw)
        assert result is None

    def test_invalid_json_returns_none(self):
        raw = _make_raw()
        raw["raw_text"] = "not valid json {"
        result = parse_raw_posting(raw)
        assert result is None

    def test_missing_job_key_returns_none(self):
        raw = _make_raw()
        raw["raw_text"] = json.dumps({"application": None})
        result = parse_raw_posting(raw)
        assert result is None

    def test_career_level_in_result(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        assert result["career_level"]["min_years"] == 3
        assert result["career_level"]["max_years"] == 7

    def test_crawl_status_active_default(self):
        raw = _make_raw()
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            result = parse_raw_posting(raw)
        assert result["crawl_status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# run_wanted_parse (배치, 파일 I/O 모킹)
# ---------------------------------------------------------------------------

class TestRunWantedParse:
    def test_pending_items_get_parsed(self, tmp_path):
        raw_dir = tmp_path / "raw_job_postings" / "2026-07-27"
        raw_dir.mkdir(parents=True)
        json_file = raw_dir / "wanted_Backend_Engineer.json"

        raw_docs = [_make_raw(source_job_id="12345", parse_status="PENDING")]
        import json as _json
        json_file.write_text(_json.dumps(raw_docs, ensure_ascii=False))

        with (
            patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x),
            patch("src.crawlers.parse_batch.save_documents") as mock_save,
        ):
            run_wanted_parse(crawl_date="2026-07-27", base_dir=str(tmp_path))

        mock_save.assert_called_once()

    def test_already_parsed_skipped(self, tmp_path):
        raw_dir = tmp_path / "raw_job_postings" / "2026-07-27"
        raw_dir.mkdir(parents=True)
        json_file = raw_dir / "wanted_Backend_Engineer.json"

        raw_docs = [_make_raw(source_job_id="12345", parse_status="PARSED")]
        import json as _json
        json_file.write_text(_json.dumps(raw_docs, ensure_ascii=False))

        with patch("src.crawlers.parse_batch.save_documents") as mock_save:
            run_wanted_parse(crawl_date="2026-07-27", base_dir=str(tmp_path))

        mock_save.assert_not_called()

    def test_reparse_already_parsed_docs(self, tmp_path):
        from src.storage.json_writer import build_document_path

        raw_dir = tmp_path / "raw_job_postings" / "2026-07-27"
        raw_dir.mkdir(parents=True)

        existing_parsed_id = "parsed-id-001"
        raw_docs = [_make_raw(source_job_id="12345", parse_status="PARSED")]
        raw_docs[0]["parsed_job_posting_id"] = existing_parsed_id
        # 재파싱은 새 경로({jf}/{source}/{date}_{id}.json)의 기존 문서를 갱신한다
        existing_parsed = {
            "id": existing_parsed_id,
            "source_name": "wanted",
            "source_job_id": "12345",
            "job_function_name": "Backend Engineer",
            "created_at": "2026-07-27T01:00:00+00:00",
            "first_collected_at": "2026-07-27T00:00:00+00:00",
            "title": "old title",
        }
        parsed_path = build_document_path(
            collection_name="job_postings",
            job_function_name="Backend Engineer",
            source_name="wanted",
            crawl_date="2026-07-27",
            source_job_id="12345",
            base_dir=str(tmp_path),
        )
        parsed_path.parent.mkdir(parents=True, exist_ok=True)

        import json as _json
        json_file = raw_dir / "wanted_Backend_Engineer.json"
        json_file.write_text(_json.dumps(raw_docs, ensure_ascii=False))
        parsed_path.write_text(_json.dumps(existing_parsed, ensure_ascii=False))

        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda _, x, __: x):
            run_wanted_parse(
                crawl_date="2026-07-27",
                base_dir=str(tmp_path),
                reparse=True,
            )

        updated_parsed = _json.loads(parsed_path.read_text(encoding="utf-8"))
        assert isinstance(updated_parsed, dict)
        assert updated_parsed["id"] == existing_parsed_id
        assert updated_parsed["title"] != "old title"

    def test_missing_directory_handled_gracefully(self, tmp_path):
        non_existent = tmp_path / "no_such_dir"
        run_wanted_parse(crawl_date="2026-07-27", base_dir=str(non_existent))
