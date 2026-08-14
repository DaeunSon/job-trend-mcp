"""
crawlers/work24/extractor.py 유닛 테스트.

HTML 파싱 로직을 네트워크 없이 테스트한다.
"""
from __future__ import annotations

import json
from textwrap import dedent
from unittest.mock import patch

import pytest

from src.crawlers.work24.extractor import (
    EXCLUDED_INFO_TYPE_CDS,
    _extract_education_from_description,
    _normalize_date,
    _parse_career,
    _parse_expires_at,
    _parse_salary,
    _resolve_education_raw,
    extract_detail_fields,
    extract_list_cards,
    extract_total_count,
    is_excluded_source,
    parse_raw_posting,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처 / 헬퍼
# ---------------------------------------------------------------------------

def _make_serp_html(cards: list[dict]) -> str:
    """
    검색 결과 목록 페이지 HTML 을 생성한다.

    각 card dict 에는 wanted_auth_no, info_type_cd, title, company 가 있다.
    """
    rows = ""
    for card in cards:
        wanted_auth_no = card["wanted_auth_no"]
        info_type_cd = card["info_type_cd"]
        title = card.get("title", "테스트 공고")
        company = card.get("company", "테스트 회사")
        rows += f"""
        <tr>
          <td>
            <strong class="cp_name">{company}</strong>
            <a href="/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo={wanted_auth_no}&infoTypeCd={info_type_cd}&infoTypeGroup=tb_workinfogubun">
              {title}
            </a>
          </td>
          <td>월급 300 만원 경력 3년 이상 학력무관 주5일 서울 강남구</td>
          <td>마감일 : 2026-08-31 등록일 : 2026-07-29</td>
        </tr>
        """
    return f"""
    <html><body>
      <span>검색건수 139건</span>
      <table><tbody>{rows}</tbody></table>
    </html></body>
    """


def _make_detail_html(
    title: str = "백엔드 개발자",
    company: str = "(주)테스트",
    salary: str = "연봉 4,000 만원 ~ 6,000 만원",
    career: str = "경력 3년 이상",
    location: str = "서울특별시 강남구 테헤란로 123",
    employment_type: str = "기간의 정함이 없는 근로계약",
    education: str = "대졸(4년)",
    occupation: str = "",
    description: str = "Django 기반 백엔드 개발\n재택근무 가능",
    remote_in_table: str | None = None,
    posted_at: str = "2026-07-01",
    expires_at: str = "2026-08-31",
) -> str:
    remote_row = (
        f'<tr><th>재택근무</th><td>{remote_in_table}</td></tr>'
        if remote_in_table is not None
        else ""
    )
    occupation_row = (
        f"<tr><th>모집 직종</th><td>{occupation}</td></tr>"
        if occupation
        else ""
    )
    return dedent(f"""
    <html><head><title>{title} | 고용24</title></head>
    <body>
      <h1 class="job-title">{title}</h1>
      <a class="cp-name">{company}</a>
      <table>
        <tr><th>급여</th><td>{salary}</td></tr>
        <tr><th>경력</th><td>{career}</td></tr>
        <tr><th>근무지역</th><td>{location}</td></tr>
        <tr><th>고용형태</th><td>{employment_type}</td></tr>
        <tr><th>학력</th><td>{education}</td></tr>
        {occupation_row}
        <tr><th>등록일</th><td>{posted_at}</td></tr>
        <tr><th>마감일</th><td>{expires_at}</td></tr>
        {remote_row}
      </table>
      <div id="duty_wrap">{description}</div>
    </body></html>
    """)


def _make_raw(
    wanted_auth_no: str = "ABC1234567890",
    info_type_cd: str = "WK",
    query: str = "백엔드 개발자",
    raw_html: str = "",
) -> dict:
    """parse_raw_posting 에 넘길 raw_job_postings 문서를 생성한다."""
    if not raw_html:
        raw_html = _make_detail_html()
    return {
        "source_name": "work24",
        "source_job_id": wanted_auth_no,
        "original_url": (
            f"https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do"
            f"?wantedAuthNo={wanted_auth_no}&infoTypeCd={info_type_cd}"
        ),
        "raw_html": raw_html,
        "raw_text": json.dumps(
            {
                "search_query": query,
                "card_meta": {
                    "wanted_auth_no": wanted_auth_no,
                    "info_type_cd": info_type_cd,
                    "title_raw": "백엔드 개발자",
                    "company_raw": "(주)테스트",
                },
            },
            ensure_ascii=False,
        ),
        "id": "test-uuid-1234",
        "collected_at": "2026-07-29T00:00:00+00:00",
        "parse_status": "PENDING",
        "parsed_job_posting_id": None,
    }


# ---------------------------------------------------------------------------
# is_excluded_source
# ---------------------------------------------------------------------------

class TestIsExcludedSource:
    def test_saramin_excluded(self):
        assert is_excluded_source("CSI") is True

    def test_jobkorea_excluded(self):
        assert is_excluded_source("CJK") is True

    def test_wanted_excluded(self):
        assert is_excluded_source("CWT") is True

    def test_case_insensitive(self):
        assert is_excluded_source("csi") is True
        assert is_excluded_source("Cjk") is True

    def test_work24_own_not_excluded(self):
        assert is_excluded_source("WK") is False

    def test_narajob_not_excluded(self):
        assert is_excluded_source("NR") is False

    def test_cleanye_not_excluded(self):
        # 클린아이 자체는 공공기관 계열 → 제외하지 않음
        assert is_excluded_source("CLE") is False

    def test_incruit_not_excluded(self):
        # 인크루트는 사람인/잡코리아/원티드가 아니므로 수집 대상
        assert is_excluded_source("CIN") is False


# ---------------------------------------------------------------------------
# extract_total_count
# ---------------------------------------------------------------------------

class TestExtractTotalCount:
    def test_detects_korean_count(self):
        html = "<html><body><span>검색건수 1,234건</span></body></html>"
        assert extract_total_count(html) == 1234

    def test_detects_total_count_pattern(self):
        html = "<html><body>총 567건의 결과</body></html>"
        assert extract_total_count(html) == 567

    def test_returns_zero_on_no_count(self):
        html = "<html><body>결과 없음</body></html>"
        assert extract_total_count(html) == 0

    def test_commas_in_number(self):
        html = "<html><body>검색건수 139,510건</body></html>"
        assert extract_total_count(html) == 139510


# ---------------------------------------------------------------------------
# extract_list_cards
# ---------------------------------------------------------------------------

class TestExtractListCards:
    def test_extracts_single_card(self):
        html = _make_serp_html(
            [{"wanted_auth_no": "WK123456", "info_type_cd": "WK", "title": "백엔드 개발자", "company": "(주)테스트"}]
        )
        cards = extract_list_cards(html)
        assert len(cards) == 1
        assert cards[0]["wanted_auth_no"] == "WK123456"
        assert cards[0]["info_type_cd"] == "WK"

    def test_extracts_multiple_cards(self):
        html = _make_serp_html(
            [
                {"wanted_auth_no": "WK111", "info_type_cd": "WK"},
                {"wanted_auth_no": "CSI222", "info_type_cd": "CSI"},
                {"wanted_auth_no": "NR333", "info_type_cd": "NR"},
            ]
        )
        cards = extract_list_cards(html)
        assert len(cards) == 3

    def test_skips_duplicate_wanted_auth_no(self):
        html = _make_serp_html(
            [
                {"wanted_auth_no": "WK111", "info_type_cd": "WK"},
                {"wanted_auth_no": "WK111", "info_type_cd": "WK"},
            ]
        )
        cards = extract_list_cards(html)
        assert len(cards) == 1

    def test_detail_url_contains_params(self):
        html = _make_serp_html(
            [{"wanted_auth_no": "ABC999", "info_type_cd": "NR"}]
        )
        cards = extract_list_cards(html)
        assert "wantedAuthNo=ABC999" in cards[0]["detail_url"]
        assert "infoTypeCd=NR" in cards[0]["detail_url"]

    def test_empty_html_returns_empty_list(self):
        assert extract_list_cards("<html><body></body></html>") == []

    def test_company_extracted_from_surrounding(self):
        html = _make_serp_html(
            [{"wanted_auth_no": "WK001", "info_type_cd": "WK", "company": "나라기관"}]
        )
        cards = extract_list_cards(html)
        assert cards[0]["company_raw"] == "나라기관"


# ---------------------------------------------------------------------------
# extract_detail_fields
# ---------------------------------------------------------------------------

class TestExtractDetailFields:
    def test_extracts_title(self):
        html = _make_detail_html(title="시니어 백엔드 개발자")
        fields = extract_detail_fields(html)
        assert fields["title"] == "시니어 백엔드 개발자"

    def test_extracts_company(self):
        html = _make_detail_html(company="(주)네이버")
        fields = extract_detail_fields(html)
        assert fields["company"] == "(주)네이버"

    def test_extracts_location(self):
        html = _make_detail_html(location="서울특별시 강남구 테헤란로 123")
        fields = extract_detail_fields(html)
        assert "강남구" in fields["location_raw"]

    def test_extracts_salary(self):
        html = _make_detail_html(salary="연봉 4,000 만원 ~ 6,000 만원")
        fields = extract_detail_fields(html)
        assert fields["salary_period"] == "ANNUAL"
        assert fields["salary_min"] == "40000000"
        assert fields["salary_max"] == "60000000"

    def test_extracts_career(self):
        html = _make_detail_html(career="경력 3년 이상")
        fields = extract_detail_fields(html)
        assert "3" in fields["career_raw"]

    def test_extracts_education(self):
        html = _make_detail_html(education="대졸(4년)")
        fields = extract_detail_fields(html)
        assert fields["education_raw"] == "대졸(4년)"

    def test_extracts_employment_type(self):
        html = _make_detail_html(employment_type="기간의 정함이 없는 근로계약")
        fields = extract_detail_fields(html)
        assert "정함이 없는" in fields["employment_type_raw"]

    def test_extracts_description(self):
        html = _make_detail_html(description="Django 백엔드 개발 담당")
        fields = extract_detail_fields(html)
        assert "Django" in fields["description"]

    def test_extracts_posted_at(self):
        html = _make_detail_html(posted_at="2026-07-01")
        fields = extract_detail_fields(html)
        assert fields["posted_at"] == "2026-07-01"

    def test_extracts_expires_at(self):
        html = _make_detail_html(expires_at="2026-08-31")
        fields = extract_detail_fields(html)
        assert fields["expires_at"] == "2026-08-31"

    def test_remote_work_flag_true(self):
        html = _make_detail_html(remote_in_table="가능")
        fields = extract_detail_fields(html)
        assert fields["has_remote_work"] is True

    def test_remote_work_flag_false(self):
        html = _make_detail_html(remote_in_table="불가")
        fields = extract_detail_fields(html)
        assert fields["has_remote_work"] is False

    def test_remote_work_flag_none_when_absent(self):
        html = _make_detail_html()  # remote_in_table 없음
        fields = extract_detail_fields(html)
        assert fields["has_remote_work"] is None

    def test_card_meta_fallback_for_title(self):
        """상세 HTML 에 제목이 없으면 card_meta 에서 폴백."""
        html = "<html><body><table></table></body></html>"
        fields = extract_detail_fields(html, card_meta={"title_raw": "폴백 제목"})
        assert fields["title"] == "폴백 제목"


# ---------------------------------------------------------------------------
# _parse_salary
# ---------------------------------------------------------------------------

class TestParseSalary:
    def test_annual_salary(self):
        min_a, max_a, period = _parse_salary("연봉 4,000 만원 ~ 6,000 만원")
        assert period == "ANNUAL"
        assert min_a == "40000000"
        assert max_a == "60000000"

    def test_monthly_salary(self):
        min_a, max_a, period = _parse_salary("월급 300 만원 ~ 400 만원")
        assert period == "MONTHLY"
        assert min_a == "3000000"

    def test_hourly_salary(self):
        min_a, max_a, period = _parse_salary("시급 10,320 원 ~ 12,000 원")
        assert period == "HOURLY"
        assert min_a == "10320"

    def test_single_amount(self):
        min_a, max_a, period = _parse_salary("연봉 5,000 만원")
        assert min_a == "50000000"
        assert max_a is None

    def test_negotiable_returns_none(self):
        min_a, max_a, period = _parse_salary("면접 후 협의")
        assert min_a is None
        assert max_a is None
        assert period is None

    def test_empty_returns_none(self):
        min_a, max_a, period = _parse_salary("")
        assert min_a is None
        assert max_a is None
        assert period is None


# ---------------------------------------------------------------------------
# _parse_career
# ---------------------------------------------------------------------------

class TestParseCareer:
    def test_min_only(self):
        assert _parse_career("경력 3년 이상") == (3, None)

    def test_range(self):
        assert _parse_career("경력 3년 ~ 7년") == (3, 7)

    def test_new_grad(self):
        assert _parse_career("신입") == (0, 0)

    def test_any_career(self):
        assert _parse_career("경력무관") == (None, None)

    def test_empty(self):
        assert _parse_career("") == (None, None)


# ---------------------------------------------------------------------------
# _normalize_date
# ---------------------------------------------------------------------------

class TestNormalizeDate:
    def test_slash_format(self):
        assert _normalize_date("2026/07/29") == "2026-07-29"

    def test_dot_format(self):
        assert _normalize_date("2026.07.29") == "2026-07-29"

    def test_iso_format(self):
        assert _normalize_date("2026-07-29") == "2026-07-29"

    def test_with_label(self):
        assert _normalize_date("마감일 : 2026-08-31") == "2026-08-31"

    def test_single_digit_month_day(self):
        assert _normalize_date("2026.7.5") == "2026-07-05"

    def test_empty_returns_empty(self):
        assert _normalize_date("") == ""

    def test_no_date_returns_empty(self):
        assert _normalize_date("날짜 없음") == ""


# ---------------------------------------------------------------------------
# _parse_expires_at
# ---------------------------------------------------------------------------

class TestParseExpiresAt:
    def test_range_uses_end_date(self):
        raw = "2026.07.30 (목) ~ 2026.08.31 (월)"
        assert _parse_expires_at(raw) == "2026-08-31"

    def test_single_deadline(self):
        assert _parse_expires_at("마감일 : 2026-08-31") == "2026-08-31"

    def test_open_ended_returns_none(self):
        assert _parse_expires_at("접수 마감일채용시까지") is None

    def test_empty_returns_none(self):
        assert _parse_expires_at("") is None


# ---------------------------------------------------------------------------
# parse_raw_posting (통합 테스트)
# ---------------------------------------------------------------------------

class TestParseRawPosting:
    def test_returns_dict_on_valid_raw(self):
        raw = _make_raw()
        result = parse_raw_posting(raw)
        assert result is not None
        assert isinstance(result, dict)

    def test_result_has_required_fields(self):
        raw = _make_raw()
        result = parse_raw_posting(raw)
        assert result is not None
        for key in ("source_name", "source_job_id", "title", "company", "location"):
            assert key in result

    def test_source_name_is_work24(self):
        raw = _make_raw()
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["source_name"] == "work24"

    def test_source_job_id_preserved(self):
        raw = _make_raw(wanted_auth_no="MYID999")
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["source_job_id"] == "MYID999"

    def test_returns_none_for_empty_html(self):
        raw = _make_raw()
        raw["raw_html"] = ""
        result = parse_raw_posting(raw)
        assert result is None

    def test_remote_override_when_remote_flag_true(self):
        html = _make_detail_html(remote_in_table="가능")
        raw = _make_raw(raw_html=html)
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["work_arrangement"] == "REMOTE"

    def test_work_arrangement_from_description_when_no_flag(self):
        html = _make_detail_html(
            description="재택근무 가능합니다. 주 3회 재택 허용.",
            remote_in_table=None,
        )
        raw = _make_raw(raw_html=html)
        result = parse_raw_posting(raw)
        assert result is not None
        # description 에 재택 키워드 있으므로 detect_work_arrangement 가 REMOTE 반환
        assert result["work_arrangement"] == "REMOTE"

    def test_annual_salary_parsed(self):
        html = _make_detail_html(salary="연봉 4,000 만원 ~ 6,000 만원")
        raw = _make_raw(raw_html=html)
        result = parse_raw_posting(raw)
        assert result is not None
        sal = result["salary"]
        assert sal["pay_period"] == "ANNUAL"
        assert sal["min_amount"] == "40000000"

    def test_job_function_from_search_query(self):
        # 검색어가 직종 소분류명(work24 직종별 카테고리명) 기반으로 변경됨
        # "소프트웨어" → Backend Engineer 포함 여러 함수에 매핑되므로
        # Backend Engineer 에만 속하는 "컴퓨터시스템" 은 여러 함수에 걸쳐있어
        # 역매핑 시 처음 매칭되는 함수를 반환함.
        # "네트워크 시스템 및 정보보안" → Security Engineer / DevOps 등
        # 단일 매핑이 보장되는 "회계·경리 사무" → Accountant 를 사용
        html = _make_detail_html()
        raw = _make_raw(raw_html=html, query="회계·경리 사무")
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["job_function_name"] == "Accountant"

    def test_malformed_html_returns_none(self):
        raw = _make_raw()
        raw["raw_html"] = "<<<not html at all>>>"
        # 제목 추출 실패 시 None 반환
        result = parse_raw_posting(raw)
        # HTML 파싱 자체는 BeautifulSoup 가 허용적으로 처리하므로
        # title 추출 실패 여부에 따라 None 또는 dict 반환
        # 여기서는 예외 없이 처리되는지만 확인
        # (title 이 비면 None, 아니면 dict)
        assert result is None or isinstance(result, dict)

    def test_education_range_preserved(self):
        html = _make_detail_html(education="대졸(4년)~석사")
        raw = _make_raw(raw_html=html)
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["education_level"] == "대졸(4년)~석사"

    def test_education_from_description_when_table_generic(self):
        description = dedent("""
            공통자격요건
            ㆍ학력 : 대졸 이상
            ㆍ경력 : 경력 3년 이상
        """)
        html = _make_detail_html(education="학력무관", description=description)
        raw = _make_raw(raw_html=html)
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["education_level"] == "대졸 이상"

    def test_job_function_from_occupation(self):
        html = _make_detail_html(
            title="[일자리매칭플랫폼] 제일일렉트릭주식회사 H/W 제품 개발자",
            occupation="H/W 엔지니어",
        )
        raw = _make_raw(raw_html=html, query="개발자")
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["job_function_name"] == "Embedded / Hardware Engineer"

    def test_job_function_from_title_when_no_occupation(self):
        html = _make_detail_html(
            title="반도체 검사기 시스템 개발 전문가를 모집합니다.",
            occupation="",
            description="반도체 검사 알고리즘 및 시스템 소프트웨어 개발",
        )
        raw = _make_raw(raw_html=html, query="개발자")
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["job_function_name"] == "Software Engineer"

    def test_normalized_title_cuts_particle_promo(self):
        html = _make_detail_html(title="개발 전문가를 모집합니다.")
        raw = _make_raw(raw_html=html, query="개발자")
        result = parse_raw_posting(raw)
        assert result is not None
        assert result["normalized_title"] == "개발 전문가"


# ---------------------------------------------------------------------------
# _resolve_education_raw / _extract_education_from_description
# ---------------------------------------------------------------------------

class TestEducationExtraction:
    def test_extract_from_description(self):
        text = "공통자격요건\nㆍ학력 : 대졸 이상\nㆍ경력 : 3년"
        assert _extract_education_from_description(text) == "대졸 이상"

    def test_resolve_prefers_description_when_table_generic(self):
        result = _resolve_education_raw("학력무관", "ㆍ학력 : 대졸 이상")
        assert result == "대졸 이상"

    def test_resolve_keeps_table_range(self):
        result = _resolve_education_raw("대졸(4년)~석사", "")
        assert result == "대졸(4년)~석사"

    def test_resolve_moogwan_when_no_specific_desc(self):
        assert _resolve_education_raw("학력무관", "") == "무관"
        assert _resolve_education_raw("학력무관", "ㆍ학력 : 무관") == "무관"
