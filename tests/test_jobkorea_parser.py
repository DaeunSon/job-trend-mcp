"""
crawlers/jobkorea/parser.py 유닛 테스트.
"""
from __future__ import annotations

import json
import pytest
from bs4 import BeautifulSoup

from src.crawlers.jobkorea.parser import (
    parse_raw_posting,
    _extract_json_ld,
    _extract_title,
    _extract_company,
    _extract_location,
    _extract_description,
    _extract_salary,
    _extract_employment_type,
    _extract_work_arrangement,
    _extract_career_level,
    _extract_posted_at,
    _extract_skills,
    _extract_education_level,
    _extract_expires_at,
    _extract_company_extras,
    _extract_flight_skills,
    _extract_flight_career,
    _parse_salary_text,
    _parse_career_text,
    _parse_location_text,
)


# ---------------------------------------------------------------------------
# 테스트용 HTML 픽스처
# ---------------------------------------------------------------------------

SAMPLE_HTML_WITH_JSON_LD = """
<html>
<head>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "백엔드 개발자 (Python)",
    "datePosted": "2026-07-20",
    "employmentType": "FULL_TIME",
    "hiringOrganization": {
      "@type": "Organization",
      "name": "카카오"
    },
    "jobLocation": {
      "@type": "Place",
      "address": {
        "@type": "PostalAddress",
        "addressLocality": "서울",
        "addressRegion": "강남구"
      }
    },
    "baseSalary": {
      "@type": "MonetaryAmount",
      "currency": "KRW",
      "value": {
        "@type": "QuantitativeValue",
        "minValue": 60000000,
        "maxValue": 90000000,
        "unitText": "YEAR"
      }
    },
    "description": "<p>Python, FastAPI, PostgreSQL, Docker, AWS 경험 필요. 재택 가능.</p>"
  }
  </script>
</head>
<body>
  <h1 class="title">백엔드 개발자 (Python)</h1>
  <a class="coName">카카오</a>
  <td data-bind="workPlace">서울 강남구</td>
  <td data-bind="career">경력 3년~7년</td>
  <td data-bind="empType">정규직</td>
  <td data-bind="salary">연봉 6,000만원 ~ 9,000만원</td>
  <div id="jobDescriptionWrap">
    Python, FastAPI, PostgreSQL, Docker, AWS 경험 필요.
    재택 가능. CI/CD 환경에서 개발합니다.
  </div>
</body>
</html>
"""

SAMPLE_HTML_NO_JSON_LD = """
<html>
<body>
  <h1>데이터 분석가</h1>
  <a class="coName">네이버</a>
  <td data-bind="workPlace">경기 성남시</td>
  <td data-bind="career">신입</td>
  <td data-bind="empType">계약직</td>
  <div id="jobDescriptionWrap">
    Python, Spark, Tableau를 활용한 데이터 분석. 하이브리드 근무 가능.
  </div>
</body>
</html>
"""

SAMPLE_HTML_PARTTIME = """
<html>
<body>
  <h1>콘텐츠 마케터</h1>
  <a class="coName">스타트업A</a>
  <td data-bind="workPlace">부산 해운대구</td>
  <td data-bind="career">경력무관</td>
  <td data-bind="empType">파트타임</td>
  <div id="jobDescriptionWrap">현장 근무 필수. 주 3일 출근.</div>
</body>
</html>
"""


@pytest.fixture
def soup_with_ld() -> BeautifulSoup:
    return BeautifulSoup(SAMPLE_HTML_WITH_JSON_LD, "lxml")


@pytest.fixture
def soup_no_ld() -> BeautifulSoup:
    return BeautifulSoup(SAMPLE_HTML_NO_JSON_LD, "lxml")


@pytest.fixture
def soup_parttime() -> BeautifulSoup:
    return BeautifulSoup(SAMPLE_HTML_PARTTIME, "lxml")


@pytest.fixture
def sample_raw() -> dict:
    return {
        "id": "test-raw-jobkorea",
        "source_name": "jobkorea",
        "source_job_id": "24115438",
        "original_url": "https://www.jobkorea.co.kr/Recruit/GI_Read/24115438",
        "raw_html": SAMPLE_HTML_WITH_JSON_LD,
        "raw_text": "백엔드 개발자 카카오 서울 강남구",
        "collected_at": "2026-07-27T00:00:00+00:00",
        "parse_status": "PENDING",
        "parsed_job_posting_id": None,
    }


# ---------------------------------------------------------------------------
# _extract_json_ld
# ---------------------------------------------------------------------------

class TestExtractJsonLd:
    def test_returns_job_posting(self, soup_with_ld):
        ld = _extract_json_ld(soup_with_ld)
        assert ld.get("@type") == "JobPosting"
        assert ld.get("title") == "백엔드 개발자 (Python)"

    def test_empty_when_no_script(self, soup_no_ld):
        assert _extract_json_ld(soup_no_ld) == {}

    def test_invalid_json_returns_empty(self):
        soup = BeautifulSoup(
            '<html><head><script type="application/ld+json">{bad json}</script></head></html>',
            "lxml",
        )
        assert _extract_json_ld(soup) == {}


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_from_json_ld(self, soup_with_ld):
        ld = _extract_json_ld(soup_with_ld)
        assert _extract_title(soup_with_ld, ld) == "백엔드 개발자 (Python)"

    def test_from_h1_fallback(self, soup_no_ld):
        assert _extract_title(soup_no_ld, {}) == "데이터 분석가"

    def test_empty_when_not_found(self):
        soup = BeautifulSoup("<html><body><p>제목없음</p></body></html>", "lxml")
        assert _extract_title(soup, {}) == ""


# ---------------------------------------------------------------------------
# _extract_company
# ---------------------------------------------------------------------------

class TestExtractCompany:
    def test_from_json_ld(self, soup_with_ld):
        ld = _extract_json_ld(soup_with_ld)
        assert _extract_company(soup_with_ld, ld) == "카카오"

    def test_from_coname_selector(self, soup_no_ld):
        assert _extract_company(soup_no_ld, {}) == "네이버"

    def test_empty_when_not_found(self):
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        assert _extract_company(soup, {}) == ""


# ---------------------------------------------------------------------------
# _extract_location
# ---------------------------------------------------------------------------

class TestExtractLocation:
    def test_from_json_ld_address(self, soup_with_ld):
        ld = _extract_json_ld(soup_with_ld)
        loc = _extract_location(soup_with_ld, ld)
        assert "서울" in loc

    def test_from_data_bind_selector(self, soup_no_ld):
        loc = _extract_location(soup_no_ld, {})
        assert "경기 성남시" in loc

    def test_busan_location(self, soup_parttime):
        loc = _extract_location(soup_parttime, {})
        assert "부산" in loc


# ---------------------------------------------------------------------------
# _parse_salary_text
# ---------------------------------------------------------------------------

class TestParseSalaryText:
    def test_krw_annual_range(self):
        min_a, max_a, currency, period = _parse_salary_text("연봉 6,000만원 ~ 9,000만원")
        assert currency == "KRW"
        assert period == "ANNUAL"
        assert int(min_a) == 60_000_000
        assert int(max_a) == 90_000_000

    def test_monthly(self):
        _, _, _, period = _parse_salary_text("월급 300만원")
        assert period == "MONTHLY"

    def test_hourly(self):
        _, _, _, period = _parse_salary_text("시급 12,000원")
        assert period == "HOURLY"

    def test_no_amount(self):
        min_a, max_a, _, _ = _parse_salary_text("면접 후 결정")
        assert min_a is None
        assert max_a is None


# ---------------------------------------------------------------------------
# _extract_salary
# ---------------------------------------------------------------------------

class TestExtractSalary:
    def test_from_json_ld(self, soup_with_ld):
        ld = _extract_json_ld(soup_with_ld)
        salary = _extract_salary(soup_with_ld, ld)
        assert salary.currency_code == "KRW"
        assert salary.min_amount == "60000000"
        assert salary.max_amount == "90000000"
        assert salary.pay_period == "ANNUAL"

    def test_from_html_wan(self, soup_with_ld):
        # JSON-LD 없는 경우 HTML fallback 확인
        salary = _extract_salary(soup_with_ld, {})
        assert salary.raw_text is not None
        assert "만원" in salary.raw_text

    def test_no_salary_returns_empty(self, soup_parttime):
        salary = _extract_salary(soup_parttime, {})
        assert salary.raw_text is None


# ---------------------------------------------------------------------------
# _extract_employment_type
# ---------------------------------------------------------------------------

class TestExtractEmploymentType:
    def test_full_time_from_json_ld(self, soup_with_ld):
        ld = _extract_json_ld(soup_with_ld)
        emp, _ = _extract_employment_type(soup_with_ld, ld)
        assert "FULL_TIME" in emp.upper()

    def test_contract_from_html(self, soup_no_ld):
        emp, _ = _extract_employment_type(soup_no_ld, {})
        assert emp == "계약직"

    def test_part_time(self, soup_parttime):
        emp, _ = _extract_employment_type(soup_parttime, {})
        assert "파트" in emp or "PART" in emp.upper()

    def test_unknown_fallback(self):
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        emp, _ = _extract_employment_type(soup, {})
        assert emp == ""


# ---------------------------------------------------------------------------
# _extract_work_arrangement
# ---------------------------------------------------------------------------

class TestExtractWorkArrangement:
    def test_remote_from_description(self):
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        desc = "재택 근무 가능합니다."
        assert _extract_work_arrangement(soup, desc) == "REMOTE"

    def test_hybrid(self, soup_no_ld):
        desc = "하이브리드 근무 가능"
        assert _extract_work_arrangement(soup_no_ld, desc) == "HYBRID"

    def test_onsite(self, soup_parttime):
        desc = ""
        assert _extract_work_arrangement(soup_parttime, desc) == "ONSITE"

    def test_none_when_not_mentioned(self):
        soup = BeautifulSoup("<html><body><p>팀워크 중시</p></body></html>", "lxml")
        assert _extract_work_arrangement(soup, "좋은 팀원을 찾습니다.") is None


# ---------------------------------------------------------------------------
# _parse_career_text / _extract_career_level
# ---------------------------------------------------------------------------

class TestParseCareerText:
    def test_entry_level(self):
        c = _parse_career_text("신입")
        assert c.label == "Entry"
        assert c.min_years == 0

    def test_any(self):
        c = _parse_career_text("경력무관")
        assert c.label == "Any"

    def test_range(self):
        c = _parse_career_text("경력 3년~7년")
        assert c.label == "Mid"
        assert c.min_years == 3
        assert c.max_years == 7

    def test_min_only(self):
        c = _parse_career_text("경력 5년 이상")
        assert c.min_years == 5
        assert c.label == "Senior"

    def test_unknown(self):
        c = _parse_career_text("알 수 없음")
        assert c.label == "Any"


class TestExtractCareerLevel:
    def test_from_html(self, soup_with_ld):
        level = _extract_career_level(soup_with_ld)
        assert level.label == "Mid"
        assert level.min_years == 3
        assert level.max_years == 7

    def test_entry_from_html(self, soup_no_ld):
        level = _extract_career_level(soup_no_ld)
        assert level.label == "Entry"


# ---------------------------------------------------------------------------
# _extract_posted_at
# ---------------------------------------------------------------------------

class TestExtractPostedAt:
    def test_from_json_ld(self, soup_with_ld):
        ld = _extract_json_ld(soup_with_ld)
        assert _extract_posted_at(soup_with_ld, ld) == "2026-07-20"

    def test_from_time_datetime_attr(self):
        soup = BeautifulSoup(
            '<html><body><time datetime="2026-06-01">2026.06.01</time></body></html>', "lxml"
        )
        assert _extract_posted_at(soup, {}) == "2026-06-01"

    def test_dot_separator_normalized(self):
        soup = BeautifulSoup(
            '<html><body><span class="post-date">2026.07.15</span></body></html>', "lxml"
        )
        result = _extract_posted_at(soup, {})
        assert result == "2026-07-15"

    def test_none_when_not_found(self):
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        assert _extract_posted_at(soup, {}) is None


# ---------------------------------------------------------------------------
# _extract_skills
# ---------------------------------------------------------------------------

class TestExtractSkills:
    def test_known_skills(self):
        desc = "Python, FastAPI, PostgreSQL, Docker, AWS를 사용합니다."
        skills = _extract_skills(desc)
        assert "Python" in skills
        assert "FastAPI" in skills
        assert "AWS" in skills

    def test_no_skills(self):
        assert _extract_skills("커뮤니케이션 능력이 중요합니다.") == []

    def test_no_partial_match(self):
        # JavaScriptXYZ 는 JavaScript와 매칭되면 안 됨
        assert "JavaScript" not in _extract_skills("JavaScriptXYZ 사용")


# ---------------------------------------------------------------------------
# _parse_location_text
# ---------------------------------------------------------------------------

class TestParseLocationText:
    def test_seoul(self):
        city, region, country = _parse_location_text("서울 강남구")
        assert region == "서울"
        assert country == "대한민국"

    def test_gyeonggi(self):
        _, region, country = _parse_location_text("경기 성남시")
        assert region == "경기"
        assert country == "대한민국"

    def test_busan(self):
        _, region, _ = _parse_location_text("부산 해운대구")
        assert region == "부산"

    def test_empty(self):
        city, region, _ = _parse_location_text("")
        assert city == ""
        assert region is None

    def test_unknown_city_defaults_korea(self):
        _, _, country = _parse_location_text("알 수 없는 지역")
        assert country == "대한민국"


# ---------------------------------------------------------------------------
# parse_raw_posting (통합)
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def test_successful_parse(self, sample_raw):
        result = parse_raw_posting(sample_raw)
        assert result is not None
        assert result["source_name"] == "jobkorea"
        assert result["source_job_id"] == "24115438"
        assert result["title"] == "백엔드 개발자 (Python)"
        assert result["company"]["raw_name"] == "카카오"
        assert result["salary"]["min_amount"] == "60000000"
        assert result["employment_type_name"] == "Full-time"

    def test_returns_none_for_empty_html(self):
        raw = {
            "id": "no-html",
            "source_name": "jobkorea",
            "source_job_id": "0",
            "original_url": "https://example.com",
            "raw_html": "",
            "raw_text": "",
            "collected_at": "2026-07-27T00:00:00+00:00",
            "parse_status": "PENDING",
        }
        assert parse_raw_posting(raw) is None

    def test_required_fields_present(self, sample_raw):
        result = parse_raw_posting(sample_raw)
        assert result is not None
        for field in [
            "id", "source_name", "source_job_id", "original_url",
            "title", "description", "company", "location", "salary",
            "employment_type_name", "skills", "source_refs",
            "posted_at", "created_at", "updated_at",
        ]:
            assert field in result, f"필드 누락: {field}"

    def test_skills_extracted(self, sample_raw):
        result = parse_raw_posting(sample_raw)
        assert result is not None
        names = [s["raw_text"] for s in result["skills"]]
        assert "Python" in names
        assert "FastAPI" in names

    def test_career_level_extracted(self, sample_raw):
        result = parse_raw_posting(sample_raw)
        assert result is not None
        assert result["career_level"]["label"] == "Mid"
        assert result["career_level"]["min_years"] == 3

    def test_location_country_korea(self, sample_raw):
        result = parse_raw_posting(sample_raw)
        assert result is not None
        assert result["location"]["country_name"] == "대한민국"

    def test_source_refs_correct(self, sample_raw):
        result = parse_raw_posting(sample_raw)
        assert result is not None
        assert len(result["source_refs"]) == 1
        assert result["source_refs"][0]["source_name"] == "jobkorea"

    def test_parse_status_not_changed_by_function(self, sample_raw):
        """parse_raw_posting 자체는 parse_status를 변경하지 않는다."""
        parse_raw_posting(sample_raw)
        assert sample_raw["parse_status"] == "PENDING"


# ---------------------------------------------------------------------------
# _extract_education_level
# ---------------------------------------------------------------------------

class TestExtractEducationLevel:
    def _ld(self, val: str) -> dict:
        return {"educationRequirements": val}

    def test_bachelor(self):
        assert _extract_education_level(self._ld("대졸 이상")) == "BACHELOR"

    def test_master(self):
        assert _extract_education_level(self._ld("석사 이상")) == "MASTER"

    def test_doctor(self):
        assert _extract_education_level(self._ld("박사")) == "DOCTOR"

    def test_high_school(self):
        assert _extract_education_level(self._ld("고졸 이상")) == "HIGH_SCHOOL"

    def test_associate(self):
        assert _extract_education_level(self._ld("초대졸 이상")) == "ASSOCIATE"

    def test_any(self):
        assert _extract_education_level(self._ld("학력무관")) == "ANY"

    def test_missing_returns_none(self):
        assert _extract_education_level({}) is None


# ---------------------------------------------------------------------------
# _extract_expires_at
# ---------------------------------------------------------------------------

class TestExtractExpiresAt:
    def test_valid_through_datetime_format(self):
        ld = {"validThrough": "2026-09-18T23:59"}
        assert _extract_expires_at(ld) == "2026-09-18"

    def test_valid_through_date_only(self):
        ld = {"validThrough": "2026-08-06"}
        assert _extract_expires_at(ld) == "2026-08-06"

    def test_missing_returns_none(self):
        assert _extract_expires_at({}) is None

    def test_empty_string_returns_none(self):
        assert _extract_expires_at({"validThrough": ""}) is None


# ---------------------------------------------------------------------------
# _extract_salary — 단일 value 케이스 추가
# ---------------------------------------------------------------------------

class TestExtractSalarySingleValue:
    def _soup(self) -> "BeautifulSoup":
        return BeautifulSoup("<html><body></body></html>", "lxml")

    def test_single_value_annual(self):
        ld = {
            "baseSalary": {
                "@type": "MonetaryAmount",
                "currency": "KRW",
                "value": {
                    "@type": "QuantitativeValue",
                    "value": 36000000,
                    "unitText": "YEAR",
                },
            }
        }
        result = _extract_salary(self._soup(), ld)
        assert result.min_amount == "36000000"
        assert result.max_amount is None
        assert result.currency_code == "KRW"
        assert result.pay_period == "ANNUAL"

    def test_range_values(self):
        ld = {
            "baseSalary": {
                "currency": "KRW",
                "value": {
                    "unitText": "YEAR",
                    "minValue": 50000000,
                    "maxValue": 70000000,
                },
            }
        }
        result = _extract_salary(self._soup(), ld)
        assert result.min_amount == "50000000"
        assert result.max_amount == "70000000"


# ---------------------------------------------------------------------------
# _extract_location — streetAddress 우선
# ---------------------------------------------------------------------------

class TestExtractLocationStreetAddress:
    def _soup(self) -> "BeautifulSoup":
        return BeautifulSoup("<html><body></body></html>", "lxml")

    def test_street_address_used_first(self):
        ld = {
            "jobLocation": {
                "address": {
                    "streetAddress": "서울 영등포구 양평로 157 1411호",
                    "addressLocality": "",
                    "addressRegion": "",
                }
            }
        }
        result = _extract_location(self._soup(), ld)
        assert "서울 영등포구" in result

    def test_fallback_to_locality_when_no_street(self):
        ld = {
            "jobLocation": {
                "address": {
                    "streetAddress": "",
                    "addressLocality": "강남구",
                    "addressRegion": "서울",
                }
            }
        }
        result = _extract_location(self._soup(), ld)
        assert "강남구" in result or "서울" in result


# ---------------------------------------------------------------------------
# _extract_company_extras
# ---------------------------------------------------------------------------

class TestExtractCompanyExtras:
    def _soup(self, text: str) -> "BeautifulSoup":
        return BeautifulSoup(f"<html><body><p>{text}</p></body></html>", "lxml")

    def test_industry_from_page(self):
        html = """<html><body>
          <p>산업(업종)</p>
          <p>포털·컨텐츠·커뮤니티</p>
          <p>중소기업 (비상장)</p>
        </body></html>"""
        soup = BeautifulSoup(html, "lxml")
        industry, _ = _extract_company_extras(soup)
        assert industry == "포털·컨텐츠·커뮤니티"

    def test_size_sme(self):
        _, size = _extract_company_extras(self._soup("중소기업 (비상장)"))
        assert size == "SME"

    def test_size_large(self):
        _, size = _extract_company_extras(self._soup("대기업"))
        assert size == "LARGE"

    def test_size_mid(self):
        _, size = _extract_company_extras(self._soup("중견기업"))
        assert size == "MID"

    def test_size_from_employee_count(self):
        _, size = _extract_company_extras(self._soup("직원 51 ~ 300명 이하"))
        assert size == "SME"

    def test_empty_page(self):
        industry, size = _extract_company_extras(BeautifulSoup("<html></html>", "lxml"))
        assert industry is None
        assert size is None


# ---------------------------------------------------------------------------
# _extract_skills — 페이지 텍스트 포함
# ---------------------------------------------------------------------------

class TestExtractSkillsPageText:
    def test_skill_in_page_text_not_description(self):
        skills = _extract_skills("", page_text="Spring Boot와 Kubernetes 경험자 우대")
        assert "Spring" in skills
        assert "Kubernetes" in skills

    def test_combined_search(self):
        skills = _extract_skills("Python Django 개발", page_text="AWS Redis 사용")
        assert "Python" in skills
        assert "Django" in skills
        assert "AWS" in skills
        assert "Redis" in skills

    def test_no_false_positive(self):
        skills = _extract_skills("", page_text="채용 공고입니다")
        assert skills == []


# ---------------------------------------------------------------------------
# _extract_flight_skills
# ---------------------------------------------------------------------------

class TestExtractFlightSkills:
    def _html(self, skills_json: str) -> str:
        """escaped JSON을 포함한 HTML 생성."""
        escaped = skills_json.replace('"', '\\"')
        return f'<script>self.__next_f.push([1,"...\\\"skills\\\":{escaped}..."])</script>'

    def test_extracts_skill_names(self):
        html = self._html(
            '[{"name":"Java","rank":0,"manualInput":false,"skillTypeCode":"HARD_SKILL"},'
            '{"name":"Spring","rank":0,"manualInput":false,"skillTypeCode":"HARD_SKILL"}]'
        )
        result = _extract_flight_skills(html)
        assert "Java" in result
        assert "Spring" in result

    def test_multiple_skills(self):
        html = self._html(
            '[{"name":"AWS","rank":0,"manualInput":false,"skillTypeCode":"HARD_SKILL"},'
            '{"name":"Kafka","rank":0,"manualInput":false,"skillTypeCode":"HARD_SKILL"},'
            '{"name":"MySQL","rank":0,"manualInput":false,"skillTypeCode":"HARD_SKILL"}]'
        )
        result = _extract_flight_skills(html)
        assert len(result) == 3
        assert "AWS" in result

    def test_filters_korean_soft_skills(self):
        html = self._html(
            '[{"name":"Java","rank":0,"manualInput":false,"skillTypeCode":"HARD_SKILL"},'
            '{"name":"계획성","rank":0,"manualInput":false,"skillTypeCode":"SOFT_SKILL"},'
            '{"name":"성실성","rank":0,"manualInput":false,"skillTypeCode":"SOFT_SKILL"}]'
        )
        result = _extract_flight_skills(html)
        assert result == ["Java"]

    def test_empty_when_no_flight_data(self):
        assert _extract_flight_skills("<html><body>내용</body></html>") == []

    def test_ignores_code_only_skills(self):
        """skillTypeCode 없는 skills 배열은 무시."""
        html = '<script>__next_f [{"skills":[{"id":"abc","type":"HARD","code":"123"}]}]</script>'
        assert _extract_flight_skills(html) == []


# ---------------------------------------------------------------------------
# _extract_flight_career
# ---------------------------------------------------------------------------

class TestExtractFlightCareer:
    def _html(self, careers_json: str) -> str:
        escaped = careers_json.replace('"', '\\"')
        return f'<script>self.__next_f.push([1,"\\\"careers\\\":{escaped}"])</script>'

    def test_experienced_with_range(self):
        html = self._html(
            '[{"type":"EXPERIENCED","range":{"from":3,"to":7,"fromInclusive":true,"toInclusive":true}}]'
        )
        result = _extract_flight_career(html)
        assert result is not None
        assert result.label == "Mid"
        assert result.min_years == 3
        assert result.max_years == 7

    def test_experienced_min_only(self):
        html = self._html(
            '[{"type":"EXPERIENCED","range":{"from":5,"to":null,"fromInclusive":true,"toInclusive":false}}]'
        )
        result = _extract_flight_career(html)
        assert result is not None
        assert result.label == "Senior"
        assert result.min_years == 5
        assert result.max_years is None

    def test_experienced_no_range(self):
        html = self._html('[{"type":"EXPERIENCED","range":null}]')
        result = _extract_flight_career(html)
        assert result is not None
        assert result.label == "Mid"
        assert result.min_years is None

    def test_any(self):
        html = self._html('[{"type":"ANY","range":null}]')
        result = _extract_flight_career(html)
        assert result is not None
        assert result.label == "Any"

    def test_entry(self):
        html = self._html('[{"type":"ENTRY","range":null}]')
        result = _extract_flight_career(html)
        assert result is not None
        assert result.label == "Entry"
        assert result.min_years == 0

    def test_returns_none_when_not_found(self):
        assert _extract_flight_career("<html></html>") is None
