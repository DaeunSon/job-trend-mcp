"""공통 정규화 모듈 단위 테스트."""
from __future__ import annotations

import pytest

from src.normalization.work_arrangement import detect_work_arrangement
from src.normalization.location_utils import trim_to_district, parse_korean_location
from src.taxonomy.employment_types import normalize_employment_type, EMPLOYMENT_TYPES
from src.taxonomy.career_levels import normalize_career_level, CAREER_LEVELS


class TestEmploymentTypes:
    def test_korean_fulltime(self):
        assert normalize_employment_type("정규직") == "Full-time"

    def test_english_code(self):
        assert normalize_employment_type("FULL_TIME") == "Full-time"

    def test_internship(self):
        assert normalize_employment_type("인턴십") == "Internship"

    def test_unknown_returns_empty(self):
        assert normalize_employment_type("UNKNOWN") == ""
        assert normalize_employment_type("") == ""

    def test_all_standards_in_list(self):
        assert "Full-time" in EMPLOYMENT_TYPES
        assert "Freelance" in EMPLOYMENT_TYPES


class TestCareerLevels:
    def test_entry_korean(self):
        cl = normalize_career_level(raw_text="신입")
        assert cl.label == "Entry"
        assert cl.min_years == 0

    def test_any_korean(self):
        cl = normalize_career_level(raw_text="경력무관")
        assert cl.label == "Any"

    def test_years_mid(self):
        cl = normalize_career_level(min_years=3, max_years=5)
        assert cl.label == "Mid"

    def test_years_senior(self):
        cl = normalize_career_level(min_years=7)
        assert cl.label == "Senior"

    def test_legacy_entry(self):
        cl = normalize_career_level(legacy_label="ENTRY")
        assert cl.label == "Entry"

    def test_senior_english(self):
        cl = normalize_career_level(raw_text="Senior Backend Engineer")
        assert cl.label == "Senior"


class TestWorkArrangement:
    def test_hybrid_before_remote(self):
        text = "하이브리드 재택 근무 주 2회 출근"
        assert detect_work_arrangement(text) == "HYBRID"

    def test_remote_compound(self):
        assert detect_work_arrangement("재택 근무 가능합니다") == "REMOTE"

    def test_onsite_compound(self):
        assert detect_work_arrangement("현장 근무 필수") == "ONSITE"

    def test_no_guess_without_context(self):
        assert detect_work_arrangement("hybrid cloud saas platform") is None
        assert detect_work_arrangement("근무지: 서울 강남구") is None
        assert detect_work_arrangement("") is None

    def test_hybrid_with_context(self):
        assert detect_work_arrangement("근무 형태는 hybrid 로 운영") == "HYBRID"

    def test_hybrid_partial_office_days(self):
        text = "재택 근무\n개발팀은 주2회 사무실 대면 출근"
        assert detect_work_arrangement(text) == "HYBRID"


class TestLocationUtils:
    def test_trim_full_address(self):
        full = "서울 성동구 성수2가3동 315-7 성문빌딩 8층"
        assert trim_to_district(full) == "서울 성동구"

    def test_parse_korean(self):
        city, region, country = parse_korean_location(
            "서울 강남구 테헤란로 123"
        )
        assert city == "서울 강남구"
        assert region == "서울"
        assert country == "대한민국"


class TestJobTaxonomyNormalization:
    def test_saramin_backend_keyword(self):
        from src.normalization.job_taxonomy import (
            extract_saramin_function_raw,
            normalize_job_taxonomy,
        )
        raw = extract_saramin_function_raw("웹개발,백엔드/서버개발,Java")
        fn, cat = normalize_job_taxonomy(raw, "")
        assert fn == "Backend Engineer"
        assert cat == "Engineering & Technology"

    def test_jobkorea_title_keyword(self):
        from src.normalization.job_taxonomy import (
            extract_jobkorea_function_raw,
            normalize_job_taxonomy,
        )
        raw = extract_jobkorea_function_raw("[백엔드] Python 개발자", "")
        fn, cat = normalize_job_taxonomy(raw, "")
        assert fn == "Backend Engineer"
        assert cat == "Engineering & Technology"

    def test_data_labeling_specialist(self):
        from src.normalization.job_taxonomy import (
            extract_remotive_taxonomy_raw,
            normalize_job_taxonomy,
        )
        job = {"category": "Data and Analytics", "tags": ["research"]}
        func_raw, cat_raw = extract_remotive_taxonomy_raw(job, "Data Labeling Specialists")
        fn, cat = normalize_job_taxonomy(func_raw, cat_raw)
        assert fn == "Data Labeling / Annotation Specialist"
        assert cat == "Data & Analytics"

    def test_resolve_seed_before_manual(self):
        from src.normalization.alias_resolver import resolve
        assert resolve("JOB_FUNCTION", "백엔드") == "Backend Engineer"
        assert resolve("JOB_CATEGORY", "Software Development") == "Engineering & Technology"
