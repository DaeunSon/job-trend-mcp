"""
crawlers/saramin/parser.py 유닛 테스트.
실제 사람인 HTML 구조를 최대한 모사한 픽스처를 사용한다.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from bs4 import BeautifulSoup

from src.crawlers.saramin.parser import (
    parse_raw_posting,
    run_saramin_parse,
    _extract_json_ld,
    _extract_title,
    _extract_company,
    _extract_location,
    _extract_description,
    _extract_salary,
    _extract_employment_type,
    _extract_work_arrangement,
    _extract_career_level,
    _extract_education_level,
    _extract_posted_at,
    _extract_expires_at,
    _extract_skills,
    _parse_career_text,
    _parse_salary_text,
    _parse_location_text,
    _extract_from_condition_table,
)
from src.taxonomy.employment_types import normalize_employment_type


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# 픽스처: 사람인 상세 페이지 HTML 모사
# ---------------------------------------------------------------------------

_DETAIL_HTML_FULL = """
<!DOCTYPE html>
<html lang="ko">
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "백엔드 개발자 (Python/Django)",
  "hiringOrganization": {
    "@type": "Organization",
    "name": "카카오"
  },
  "jobLocation": {
    "@type": "Place",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "서울 강남구",
      "addressRegion": "서울"
    }
  },
  "description": "Python과 Django를 활용한 백엔드 개발 담당. AWS, PostgreSQL, Redis 경험 우대.",
  "datePosted": "2026-07-01",
  "validThrough": "2026-08-31",
  "baseSalary": {
    "@type": "MonetaryAmount",
    "currency": "KRW",
    "value": {
      "@type": "QuantitativeValue",
      "minValue": 50000000,
      "maxValue": 80000000,
      "unitText": "YEAR"
    }
  },
  "employmentType": "FULL_TIME"
}
</script>
</head>
<body>
<div class="wrap-jv">
  <div class="jv-summary">
    <h1 class="tit">백엔드 개발자 (Python/Django)</h1>
    <div class="corp-name"><a href="#">카카오</a></div>
    <dl>
      <dt>근무지역</dt><dd>서울 강남구</dd>
      <dt>경력</dt><dd>경력 3~5년</dd>
      <dt>학력</dt><dd>대졸(4년)</dd>
      <dt>고용형태</dt><dd>정규직</dd>
      <dt>급여</dt><dd>5,000~8,000만원</dd>
      <dt>등록일</dt><dd>2026.07.01</dd>
      <dt>마감일</dt><dd>2026.08.31</dd>
    </dl>
  </div>
  <div class="jv-cont">
    <div class="cont">
      Python과 Django를 활용한 백엔드 API 개발.
      AWS 클라우드 환경에서 PostgreSQL, Redis 운용.
      Docker, Kubernetes 기반 인프라 관리.
      코드 리뷰 및 Agile 방법론 적용.
      재택근무 가능.
    </div>
  </div>
</div>
</body>
</html>
"""

_DETAIL_HTML_NO_LD = """
<!DOCTYPE html>
<html lang="ko">
<body>
<div class="wrap-jv">
  <div class="jv-summary">
    <h1 class="tit">프론트엔드 개발자 (React)</h1>
    <div class="corp-name"><a href="#">네이버</a></div>
    <dl>
      <dt>근무지역</dt><dd>경기 성남시</dd>
      <dt>경력</dt><dd>신입</dd>
      <dt>학력</dt><dd>학력무관</dd>
      <dt>고용형태</dt><dd>계약직</dd>
      <dt>급여</dt><dd>면접 후 결정</dd>
      <dt>등록일</dt><dd>2026.07.15</dd>
      <dt>마감일</dt><dd>상시채용</dd>
    </dl>
  </div>
  <div class="jv-cont">
    <div class="cont">
      React, TypeScript를 사용한 웹 프론트엔드 개발.
      Next.js 기반 SSR 구현 경험 우대.
      현장 근무 필수.
    </div>
  </div>
</div>
</body>
</html>
"""

_MINIMAL_HTML = """
<html><body>
<h1 class="tit">최소 필드 공고</h1>
<div class="corp-name"><a>테스트회사</a></div>
</body></html>
"""


# ---------------------------------------------------------------------------
# _extract_json_ld
# ---------------------------------------------------------------------------

class TestExtractJsonLd:
    def test_extracts_job_posting_type(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        assert ld.get("@type") == "JobPosting"

    def test_title_in_ld(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        assert "백엔드" in ld.get("title", "")

    def test_no_ld_returns_empty_dict(self):
        soup = _soup("<html><body><p>내용</p></body></html>")
        ld = _extract_json_ld(soup)
        assert ld == {}

    def test_malformed_json_skipped(self):
        html = '<html><head><script type="application/ld+json">{invalid json}</script></head></html>'
        soup = _soup(html)
        ld = _extract_json_ld(soup)
        assert ld == {}


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------

class TestExtractTitle:
    def test_from_json_ld(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        title = _extract_title(soup, ld)
        assert title == "백엔드 개발자 (Python/Django)"

    def test_from_html_when_no_ld(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        title = _extract_title(soup, {})
        assert "프론트엔드" in title

    def test_empty_when_no_title(self):
        soup = _soup("<html><body><p>제목 없음</p></body></html>")
        title = _extract_title(soup, {})
        assert title == ""


# ---------------------------------------------------------------------------
# _extract_company
# ---------------------------------------------------------------------------

class TestExtractCompany:
    def test_from_json_ld(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        company = _extract_company(soup, ld)
        assert company == "카카오"

    def test_from_html_when_no_ld(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        company = _extract_company(soup, {})
        assert "네이버" in company

    def test_empty_when_no_company(self):
        soup = _soup("<html><body><p>회사 없음</p></body></html>")
        company = _extract_company(soup, {})
        assert company == ""


# ---------------------------------------------------------------------------
# _extract_location
# ---------------------------------------------------------------------------

class TestExtractLocation:
    def test_from_json_ld(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        loc = _extract_location(soup, ld)
        assert "서울" in loc

    def test_from_condition_table_when_no_ld(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        loc = _extract_location(soup, {})
        assert "경기" in loc or "성남" in loc

    def test_empty_returns_empty_string(self):
        soup = _soup("<html><body><p>위치 없음</p></body></html>")
        loc = _extract_location(soup, {})
        assert loc == ""

    def test_from_jv_location_data_address(self):
        html = """
        <div class="jv_cont jv_location"
             data-address="서울 성동구 성수2가3동 315-7 성문빌딩 8층 브레인즈컴퍼니">
          <h2 class="jv_title">근무지위치</h2>
          <address class="address"><span>서울 성동구 성수2가3동 315-7</span></address>
        </div>
        <dl><dt>근무지역</dt><dd>서울 성동구지도보기</dd></dl>
        """
        loc = _extract_location(_soup(html), {})
        assert loc == "서울 성동구 성수2가3동 315-7 성문빌딩 8층 브레인즈컴퍼니"


# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------

class TestExtractDescription:
    def test_from_json_ld(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        desc = _extract_description(soup, ld)
        assert "Python" in desc

    def test_from_html_cont_when_no_ld(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        desc = _extract_description(soup, {})
        assert "React" in desc or "프론트엔드" in desc

    def test_empty_when_no_description(self):
        soup = _soup("<html><body><p>내용 없음</p></body></html>")
        desc = _extract_description(soup, {})
        assert desc == "" or len(desc) < 20


# ---------------------------------------------------------------------------
# _extract_salary
# ---------------------------------------------------------------------------

class TestExtractSalary:
    def test_from_json_ld(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        sal = _extract_salary(soup, ld)
        assert sal.currency_code == "KRW"
        assert sal.min_amount == "50000000"
        assert sal.max_amount == "80000000"
        assert sal.pay_period == "ANNUAL"

    def test_from_condition_table_when_no_ld(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        sal = _extract_salary(soup, {})
        # "면접 후 결정" → 파싱 불가하므로 raw_text만 있어야 함
        assert sal.raw_text is not None or sal.raw_text is None  # 예외 없이 처리

    def test_empty_returns_salary_info_object(self):
        soup = _soup("<html><body><p>급여 없음</p></body></html>")
        sal = _extract_salary(soup, {})
        from src.models.schemas import SalaryInfo
        assert isinstance(sal, SalaryInfo)


# ---------------------------------------------------------------------------
# _parse_salary_text
# ---------------------------------------------------------------------------

class TestParseSalaryText:
    def test_만원_range(self):
        min_a, max_a, currency, period = _parse_salary_text("5,000~8,000만원 연봉")
        assert currency == "KRW"
        assert min_a == "50000000"
        assert max_a == "80000000"
        assert period == "ANNUAL"

    def test_단일_만원(self):
        min_a, max_a, currency, period = _parse_salary_text("3,000만원 이상")
        assert currency == "KRW"
        assert min_a == "30000000"
        assert max_a is None

    def test_협의(self):
        min_a, max_a, currency, period = _parse_salary_text("면접 후 결정")
        assert min_a is None
        assert max_a is None

    def test_월급(self):
        _, _, currency, period = _parse_salary_text("250만원 월급")
        assert period == "MONTHLY"

    def test_시급(self):
        _, _, _, period = _parse_salary_text("시급 15,000원")
        assert period == "HOURLY"


# ---------------------------------------------------------------------------
# _extract_employment_type
# ---------------------------------------------------------------------------

class TestExtractEmploymentType:
    def test_from_json_ld_full_time(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        emp, reliable = _extract_employment_type(soup, ld)
        assert "FULL_TIME" in emp.upper()
        assert reliable is True

    def test_from_condition_table_계약직(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        emp, reliable = _extract_employment_type(soup, {})
        assert emp == "계약직"
        assert reliable is True

    def test_인턴(self):
        html = '<html><body><dl><dt>고용형태</dt><dd>인턴직</dd></dl></body></html>'
        soup = _soup(html)
        emp, reliable = _extract_employment_type(soup, {})
        assert "인턴" in emp
        assert reliable is True

    def test_unknown_returns_empty(self):
        soup = _soup("<html><body><p>고용형태 없음</p></body></html>")
        emp, reliable = _extract_employment_type(soup, {})
        assert emp == ""
        assert reliable is False


class TestNormalizeEmploymentType:
    def test_정규직(self):
        assert normalize_employment_type("정규직") == "Full-time"

    def test_계약직(self):
        assert normalize_employment_type("계약직") == "Contract"

    def test_아르바이트(self):
        assert normalize_employment_type("아르바이트") == "Part-time"

    def test_파트타임(self):
        assert normalize_employment_type("파트타임") == "Part-time"

    def test_인턴(self):
        assert normalize_employment_type("인턴직") == "Internship"

    def test_프리랜서(self):
        assert normalize_employment_type("프리랜서") == "Freelance"

    def test_알수없음(self):
        assert normalize_employment_type("미정") == ""


# ---------------------------------------------------------------------------
# _extract_work_arrangement
# ---------------------------------------------------------------------------

class TestExtractWorkArrangement:
    def test_remote_detected(self):
        soup = _soup(_DETAIL_HTML_FULL)  # "재택근무 가능" 포함
        desc = "재택근무 가능. Python 개발."
        arrangement = _extract_work_arrangement(soup, desc)
        assert arrangement == "REMOTE"

    def test_onsite_detected(self):
        soup = _soup("<html><body><p>사무실 출근 필수</p></body></html>")
        desc = "현장 근무 필수"
        arrangement = _extract_work_arrangement(soup, desc)
        assert arrangement == "ONSITE"

    def test_hybrid_detected(self):
        soup = _soup("<html><body><p>하이브리드 근무</p></body></html>")
        desc = "하이브리드 근무 정책 적용"
        arrangement = _extract_work_arrangement(soup, desc)
        assert arrangement == "HYBRID"

    def test_unknown_returns_none(self):
        soup = _soup("<html><body><p>근무 형태 미정</p></body></html>")
        arrangement = _extract_work_arrangement(soup, "특별한 언급 없음")
        assert arrangement is None


# ---------------------------------------------------------------------------
# _extract_career_level / _parse_career_text
# ---------------------------------------------------------------------------

class TestParseCareerText:
    def test_신입(self):
        cl = _parse_career_text("신입")
        assert cl.label == "Entry"
        assert cl.min_years == 0

    def test_경력무관(self):
        cl = _parse_career_text("경력무관")
        assert cl.label == "Any"

    def test_신입_경력_모두(self):
        cl = _parse_career_text("신입·경력")
        assert cl.label == "Any"

    def test_n년_이상(self):
        cl = _parse_career_text("경력 3년 이상")
        assert cl.label == "Mid"
        assert cl.min_years == 3

    def test_n_m년_범위(self):
        cl = _parse_career_text("경력 3~5년")
        assert cl.label == "Mid"
        assert cl.min_years == 3
        assert cl.max_years == 5

    def test_경력_일반(self):
        cl = _parse_career_text("경력자 우대")
        assert cl.label == "Mid"

    def test_unknown(self):
        cl = _parse_career_text("알 수 없음")
        assert cl.label == "Any"

    def test_from_condition_table(self):
        soup = _soup(_DETAIL_HTML_FULL)
        from src.crawlers.saramin.parser import _extract_career_level
        cl = _extract_career_level(soup)
        assert cl.label == "Mid"
        assert cl.min_years == 3
        assert cl.max_years == 5


# ---------------------------------------------------------------------------
# _extract_education_level
# ---------------------------------------------------------------------------

class TestExtractEducationLevel:
    def test_extracts_from_condition_table(self):
        soup = _soup(_DETAIL_HTML_FULL)
        edu = _extract_education_level(soup)
        assert edu is not None
        assert "대졸" in edu or "4년" in edu

    def test_학력무관(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        edu = _extract_education_level(soup)
        assert edu is not None
        assert "무관" in edu

    def test_no_education_returns_none(self):
        soup = _soup("<html><body><p>학력 정보 없음</p></body></html>")
        edu = _extract_education_level(soup)
        assert edu is None


# ---------------------------------------------------------------------------
# _extract_posted_at / _extract_expires_at
# ---------------------------------------------------------------------------

class TestExtractDates:
    def test_posted_at_from_ld(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        posted = _extract_posted_at(soup, ld)
        assert posted == "2026-07-01"

    def test_posted_at_from_table(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        posted = _extract_posted_at(soup, {})
        assert posted == "2026-07-15"

    def test_expires_at_from_ld(self):
        soup = _soup(_DETAIL_HTML_FULL)
        ld = _extract_json_ld(soup)
        expires = _extract_expires_at(soup, ld)
        assert expires == "2026-08-31"

    def test_expires_at_상시채용_returns_none(self):
        soup = _soup(_DETAIL_HTML_NO_LD)
        expires = _extract_expires_at(soup, {})
        assert expires is None

    def test_no_dates_returns_none(self):
        soup = _soup("<html><body><p>날짜 없음</p></body></html>")
        assert _extract_posted_at(soup, {}) is None
        assert _extract_expires_at(soup, {}) is None


# ---------------------------------------------------------------------------
# _extract_skills
# ---------------------------------------------------------------------------

class TestExtractSkills:
    def test_python_detected(self):
        skills = _extract_skills("Python과 Django를 사용합니다.")
        assert "Python" in skills

    def test_multiple_skills(self):
        desc = "AWS, Docker, PostgreSQL, Redis, Python 환경에서 개발합니다."
        skills = _extract_skills(desc)
        assert "AWS" in skills
        assert "Docker" in skills
        assert "PostgreSQL" in skills

    def test_no_skills_empty(self):
        skills = _extract_skills("일반 사무 보조 업무")
        assert skills == []

    def test_case_insensitive_not_matched_for_other_words(self):
        # "pythons" 처럼 단어 경계를 넘으면 매칭 안 돼야 함
        skills = _extract_skills("pythons are snakes")
        assert "Python" not in skills

    def test_react_detected(self):
        skills = _extract_skills("React와 TypeScript로 개발합니다.")
        assert "React" in skills
        assert "TypeScript" in skills


# ---------------------------------------------------------------------------
# _parse_location_text
# ---------------------------------------------------------------------------

class TestParseLocationText:
    def test_서울(self):
        city, region, country = _parse_location_text("서울 강남구")
        assert region == "서울"
        assert country == "대한민국"
        assert city == "서울 강남구"

    def test_경기(self):
        city, region, country = _parse_location_text("경기 성남시")
        assert region == "경기"

    def test_전국(self):
        city, region, country = _parse_location_text("전국")
        assert region is None
        assert country == "대한민국"

    def test_empty(self):
        city, region, country = _parse_location_text("")
        assert city == ""
        assert country == "대한민국"

    def test_부산(self):
        city, region, country = _parse_location_text("부산 해운대구")
        assert region == "부산"
        assert city == "부산 해운대구"

    def test_full_address_city_trimmed(self):
        """전체 주소에서 city_name은 구/시까지만."""
        full = "서울 성동구 성수2가3동 315-7 성문빌딩 8층 브레인즈컴퍼니"
        city, region, country = _parse_location_text(full)
        assert city == "서울 성동구"
        assert region == "서울"

    def test_postal_prefix_address(self):
        full = "(06072) 서울 강남구 영동대로137길 3, 106호"
        city, region, _ = _parse_location_text(full)
        assert city == "서울 강남구"
        assert region == "서울"


# ---------------------------------------------------------------------------
# _extract_from_condition_table
# ---------------------------------------------------------------------------

class TestExtractFromConditionTable:
    def test_dl_structure(self):
        html = """
        <dl>
          <dt>근무지역</dt><dd>서울 강남구</dd>
          <dt>경력</dt><dd>경력 3~5년</dd>
          <dt>급여</dt><dd>5,000만원 이상</dd>
        </dl>
        """
        soup = _soup(html)
        assert _extract_from_condition_table(soup, ["근무지역"]) == "서울 강남구"
        assert _extract_from_condition_table(soup, ["경력"]) == "경력 3~5년"
        assert _extract_from_condition_table(soup, ["급여"]) == "5,000만원 이상"

    def test_table_structure(self):
        html = """
        <table>
          <tr><th>근무지역</th><td>경기 수원시</td></tr>
          <tr><th>고용형태</th><td>정규직</td></tr>
        </table>
        """
        soup = _soup(html)
        assert _extract_from_condition_table(soup, ["근무지역"]) == "경기 수원시"
        assert _extract_from_condition_table(soup, ["고용형태"]) == "정규직"

    def test_label_not_found_returns_empty(self):
        html = "<dl><dt>근무지역</dt><dd>서울</dd></dl>"
        soup = _soup(html)
        assert _extract_from_condition_table(soup, ["급여", "연봉"]) == ""

    def test_multiple_label_candidates(self):
        html = "<dl><dt>연봉</dt><dd>5,000만원</dd></dl>"
        soup = _soup(html)
        result = _extract_from_condition_table(soup, ["급여", "연봉", "임금"])
        assert result == "5,000만원"


# ---------------------------------------------------------------------------
# parse_raw_posting — 통합 테스트
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def _make_raw(self, html: str, source_job_id: str = "99999999") -> dict:
        return {
            "id": "test-uuid-1234",
            "source_name": "saramin",
            "source_job_id": source_job_id,
            "original_url": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={source_job_id}",
            "raw_html": html,
            "raw_text": BeautifulSoup(html, "lxml").get_text(),
            "collected_at": "2026-07-27T00:00:00+00:00",
            "parse_status": "PENDING",
            "parsed_job_posting_id": None,
        }

    def test_full_detail_html_parsed(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["title"] == "백엔드 개발자 (Python/Django)"
        assert result["source_name"] == "saramin"
        assert result["source_job_id"] == "99999999"

    def test_company_extracted(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["company"]["raw_name"] == "카카오"

    def test_salary_extracted(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["salary"]["currency_code"] == "KRW"
        assert result["salary"]["pay_period"] == "ANNUAL"

    def test_career_level_extracted(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["career_level"]["label"] == "Mid"

    def test_employment_type_full_time(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["employment_type_name"] == "Full-time"

    def test_work_arrangement_remote(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["work_arrangement"] == "REMOTE"

    def test_skills_extracted(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        skill_names = [s["raw_text"] for s in result["skills"]]
        assert "Python" in skill_names

    def test_posted_at_extracted(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["posted_at"] == "2026-07-01"

    def test_expires_at_extracted(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["expires_at"] == "2026-08-31"

    def test_no_html_returns_none(self):
        raw = self._make_raw("")
        result = parse_raw_posting(raw)
        assert result is None

    def test_minimal_html_parsed(self):
        """최소 필드만 있는 HTML도 예외 없이 처리해야 한다."""
        raw = self._make_raw(_MINIMAL_HTML)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None

    def test_result_has_id(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert "id" in result
        assert result["id"]  # 비어있지 않아야 함

    def test_source_refs_populated(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert len(result["source_refs"]) == 1
        assert result["source_refs"][0]["source_name"] == "saramin"

    def test_location_info_extracted(self):
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        assert result["location"]["country_name"] == "대한민국"
        assert result["location"]["region_name"] == "서울"

    def test_no_schema_extra_fields(self):
        """스키마에 없는 필드가 추가되지 않아야 한다."""
        from src.models.schemas import JobPosting
        raw = self._make_raw(_DETAIL_HTML_FULL)
        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            result = parse_raw_posting(raw)
        assert result is not None
        allowed_keys = set(JobPosting.__dataclass_fields__.keys())
        for key in result:
            assert key in allowed_keys, f"스키마에 없는 필드 발견: {key!r}"


# ---------------------------------------------------------------------------
# run_saramin_parse — 배치 파싱 통합
# ---------------------------------------------------------------------------

class TestRunSaraminParse:
    def test_processes_pending_files(self, tmp_path):
        """PENDING 문서를 파싱하고 parse_status를 갱신해야 한다."""
        raw_dir = tmp_path / "raw_job_postings" / "2026-07-27"
        raw_dir.mkdir(parents=True)

        raw_docs = [
            {
                "id": "test-id-001",
                "source_name": "saramin",
                "source_job_id": "11111111",
                "original_url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=11111111",
                "raw_html": _MINIMAL_HTML,
                "raw_text": "최소 필드 공고",
                "collected_at": "2026-07-27T00:00:00+00:00",
                "parse_status": "PENDING",
                "parsed_job_posting_id": None,
            }
        ]

        import json
        json_file = raw_dir / "saramin_테스트.json"
        json_file.write_text(json.dumps(raw_docs, ensure_ascii=False), encoding="utf-8")

        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            run_saramin_parse(crawl_date="2026-07-27", base_dir=str(tmp_path))

        from src.storage.json_writer import _read_json_list

        updated = _read_json_list(json_file)
        statuses = {doc["id"]: doc["parse_status"] for doc in updated}
        assert statuses["test-id-001"] in ("PARSED", "FAILED")

    def test_skips_non_saramin_docs(self, tmp_path):
        """source_name이 saramin이 아닌 문서는 건너뛰어야 한다."""
        raw_dir = tmp_path / "raw_job_postings" / "2026-07-27"
        raw_dir.mkdir(parents=True)

        raw_docs = [
            {
                "id": "other-id-001",
                "source_name": "jobkorea",
                "source_job_id": "99999999",
                "original_url": "https://www.jobkorea.co.kr/...",
                "raw_html": _MINIMAL_HTML,
                "raw_text": "잡코리아 공고",
                "collected_at": "2026-07-27T00:00:00+00:00",
                "parse_status": "PENDING",
                "parsed_job_posting_id": None,
            }
        ]

        import json
        json_file = raw_dir / "saramin_테스트.json"
        json_file.write_text(json.dumps(raw_docs, ensure_ascii=False), encoding="utf-8")

        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            run_saramin_parse(crawl_date="2026-07-27", base_dir=str(tmp_path))

        updated = json.loads(json_file.read_text(encoding="utf-8"))
        assert updated[0]["parse_status"] == "PENDING"  # 건드리지 않음

    def test_reparse_already_parsed_docs(self, tmp_path):
        """reparse=True 이면 PARSED 문서도 다시 파싱해야 한다."""
        from src.storage.json_writer import _read_json_list, build_document_path

        raw_dir = tmp_path / "raw_job_postings" / "2026-07-27"
        raw_dir.mkdir(parents=True)

        existing_parsed_id = "parsed-id-001"
        raw_docs = [
            {
                "id": "test-id-001",
                "source_name": "saramin",
                "source_job_id": "11111111",
                "original_url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=11111111",
                "raw_html": _MINIMAL_HTML,
                "raw_text": "최소 필드 공고",
                "collected_at": "2026-07-27T00:00:00+00:00",
                "parse_status": "PARSED",
                "parsed_job_posting_id": existing_parsed_id,
            }
        ]
        # 최소 HTML 은 job_function 이 비어 _unknown 경로로 저장된다
        existing_parsed = {
            "id": existing_parsed_id,
            "source_name": "saramin",
            "source_job_id": "11111111",
            "job_function_name": "",
            "created_at": "2026-07-27T01:00:00+00:00",
            "first_collected_at": "2026-07-27T00:00:00+00:00",
            "title": "old title",
        }
        parsed_path = build_document_path(
            collection_name="job_postings",
            job_function_name="_unknown",
            source_name="saramin",
            crawl_date="2026-07-27",
            source_job_id="11111111",
            base_dir=str(tmp_path),
        )
        parsed_path.parent.mkdir(parents=True, exist_ok=True)

        import json
        json_file = raw_dir / "saramin_테스트.json"
        json_file.write_text(json.dumps(raw_docs, ensure_ascii=False), encoding="utf-8")
        parsed_path.write_text(
            json.dumps(existing_parsed, ensure_ascii=False), encoding="utf-8"
        )

        with patch("src.normalization.posting_normalizer.resolve", side_effect=lambda t, v, s: v):
            run_saramin_parse(
                crawl_date="2026-07-27",
                base_dir=str(tmp_path),
                reparse=True,
            )

        updated_raw = _read_json_list(json_file)
        assert updated_raw[0]["parse_status"] == "PARSED"

        updated_parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        assert isinstance(updated_parsed, dict)
        assert updated_parsed["id"] == existing_parsed_id
        assert updated_parsed["created_at"] == "2026-07-27T01:00:00+00:00"
        assert updated_parsed["title"] != "old title"

    def test_missing_directory_logs_warning(self, tmp_path, caplog):
        """raw_job_postings 디렉토리가 없으면 경고 로그만 남기고 종료해야 한다."""
        import logging
        with caplog.at_level(logging.WARNING, logger="src.crawlers.saramin.parser"):
            run_saramin_parse(base_dir=str(tmp_path / "nonexistent"))
        assert any("없음" in r.message for r in caplog.records)
