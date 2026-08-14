"""
The Muse 전용 카테고리 매핑.

구조
----
THEMUSE_SEARCH_QUERIES: dict[str, list[str]]
  키  : taxonomy/job_functions.py 의 표준 job_function_name 값
  값  : The Muse API category 이름 목록

The Muse 공식 API 카테고리 출처
--------------------------------
GET https://www.themuse.com/api/public/jobs 응답의 categories 필드 기준
(2026-07-29 실제 호출 확인):

  "Account Management"
  "Accounting and Finance"
  "Advertising and Marketing"
  "Animal Care"
  "Business Operations"
  "Data and Analytics"
  "Education"
  "Food and Hospitality Services"
  "Healthcare"
  "Human Resources and Recruitment"
  "Installation, Maintenance, and Repairs"
  "Legal Services"
  "Management"
  "Manufacturing and Warehouse"
  "Product Management"
  "Project Management"
  "Retail"
  "Sales"
  "Science and Engineering"
  "Software Engineering"
  "Unknown"

API 호출 파라미터: category=<name> (단수형, 문자열 일치)
예: GET /api/public/jobs?page=1&category=Software+Engineering

레벨 필터 (level= 파라미터):
  "Entry Level"   → entry-level 포지션
  "Mid Level"     → mid-level 포지션
  "Senior Level"  → senior 포지션

설계 원칙
---------
- 하나의 taxonomy 직무가 여러 The Muse 카테고리에 걸쳐 수집될 수 있다.
- 반대로 여러 taxonomy 직무가 동일한 The Muse 카테고리를 공유할 수 있다.
- category 이름은 API 응답의 categories[].name 값과 동일하게 사용한다.
"""
from __future__ import annotations

# ── The Muse category 상수 (가독성용) ─────────────────────────────────────────
_SOFTWARE_ENG      = "Software Engineering"
_DATA_ANALYTICS    = "Data and Analytics"
_SCIENCE_ENG       = "Science and Engineering"
_PRODUCT_MGMT      = "Product Management"
_PROJECT_MGMT      = "Project Management"
_BUSINESS_OPS      = "Business Operations"
_ADVERTISING       = "Advertising and Marketing"
_ACCOUNT_MGMT      = "Account Management"
_ACCOUNTING_FIN    = "Accounting and Finance"
_HR                = "Human Resources and Recruitment"
_SALES             = "Sales"
_LEGAL             = "Legal Services"
_MANAGEMENT        = "Management"
_EDUCATION         = "Education"
_HEALTHCARE        = "Healthcare"
_MANUFACTURING     = "Manufacturing and Warehouse"


# ── 메인 매핑 ──────────────────────────────────────────────────────────────────
# taxonomy job_function_name → The Muse category 이름 목록

THEMUSE_SEARCH_QUERIES: dict[str, list[str]] = {
    # ── Engineering & Technology ─────────────────────────────────────────────
    "Software Engineer":            [_SOFTWARE_ENG, _SCIENCE_ENG],
    "Backend Engineer":             [_SOFTWARE_ENG],
    "Frontend Engineer":            [_SOFTWARE_ENG],
    "Full Stack Engineer":          [_SOFTWARE_ENG],
    "Mobile Engineer":              [_SOFTWARE_ENG],
    "DevOps / Platform Engineer":   [_SOFTWARE_ENG, _SCIENCE_ENG],
    "Site Reliability Engineer":    [_SOFTWARE_ENG],
    "Security Engineer":            [_SOFTWARE_ENG, _SCIENCE_ENG],
    "QA / Test Engineer":           [_SOFTWARE_ENG],
    "Embedded / Hardware Engineer": [_SCIENCE_ENG],
    # ── Data & Analytics ─────────────────────────────────────────────────────
    "Machine Learning Engineer":    [_DATA_ANALYTICS, _SOFTWARE_ENG],
    "Data Engineer":                [_DATA_ANALYTICS],
    "Data Scientist":               [_DATA_ANALYTICS, _SCIENCE_ENG],
    "Data Analyst":                 [_DATA_ANALYTICS],
    "AI Researcher":                [_DATA_ANALYTICS, _SCIENCE_ENG],
    "Business Intelligence Analyst":[_DATA_ANALYTICS, _BUSINESS_OPS],
    # ── Product & Design ─────────────────────────────────────────────────────
    "Product Manager":              [_PRODUCT_MGMT],
    "UX Designer":                  [_SOFTWARE_ENG],
    "UI Designer":                  [_SOFTWARE_ENG],
    "Product Designer":             [_PRODUCT_MGMT],
    "UX Researcher":                [_PRODUCT_MGMT],
    # ── Marketing & Growth ───────────────────────────────────────────────────
    "Growth Marketer":              [_ADVERTISING],
    "Performance Marketer":         [_ADVERTISING],
    "Content Marketer":             [_ADVERTISING],
    "Brand Marketer":               [_ADVERTISING],
    "SEO / SEM Specialist":         [_ADVERTISING],
    # ── Finance & Accounting ─────────────────────────────────────────────────
    "Financial Analyst":            [_ACCOUNTING_FIN],
    "Accountant":                   [_ACCOUNTING_FIN],
    "Quantitative Analyst":         [_ACCOUNTING_FIN, _DATA_ANALYTICS],
    "Investment Analyst":           [_ACCOUNTING_FIN],
    # ── Operations & Strategy ────────────────────────────────────────────────
    "Business Analyst":             [_BUSINESS_OPS, _DATA_ANALYTICS],
    "Strategy Consultant":          [_BUSINESS_OPS, _MANAGEMENT],
    "Operations Manager":           [_BUSINESS_OPS],
    "Project Manager":              [_PROJECT_MGMT],
    # ── Human Resources ──────────────────────────────────────────────────────
    "Recruiter":                    [_HR],
    "HR Business Partner":          [_HR],
    "Compensation & Benefits Specialist": [_HR],
    # ── Sales & Business Development ─────────────────────────────────────────
    "Sales Engineer":               [_SALES],
    "Account Executive":            [_SALES, _ACCOUNT_MGMT],
    "Business Development Manager": [_SALES, _BUSINESS_OPS],
    # ── Legal & Compliance ───────────────────────────────────────────────────
    "Legal Counsel":                [_LEGAL],
    "Compliance Officer":           [_LEGAL],
    # ── Research & Science ───────────────────────────────────────────────────
    "Research Scientist":           [_SCIENCE_ENG, _DATA_ANALYTICS],
    "Research Engineer":            [_SCIENCE_ENG, _SOFTWARE_ENG],
    # ── Customer Success ─────────────────────────────────────────────────────
    "Customer Success Manager":     [_ACCOUNT_MGMT, _SALES],
    "Technical Support Engineer":   [_SOFTWARE_ENG],
    # ── Data Labeling (closest: Data and Analytics) ──────────────────────────
    "Data Labeling / Annotation Specialist": [_DATA_ANALYTICS],
    # ── Education & Training ─────────────────────────────────────────────────
    "Teacher / Instructor":         [_EDUCATION],
    "Curriculum Developer":         [_EDUCATION],
    # ── Supply Chain & Logistics ─────────────────────────────────────────────
    "Supply Chain Manager":         [_MANUFACTURING, _BUSINESS_OPS],
    "Logistics Coordinator":        [_MANUFACTURING, _BUSINESS_OPS],
    # ── Healthcare ───────────────────────────────────────────────────────────
    "Nurse":                        [_HEALTHCARE],
    "Healthcare Specialist":        [_HEALTHCARE],
}

# The Muse에서 수집할 카테고리 전체 배치 목록 (기본 실행 대상)
DEFAULT_BATCH_CATEGORIES: list[str] = [
    _SOFTWARE_ENG,
    _DATA_ANALYTICS,
    _SCIENCE_ENG,
    _PRODUCT_MGMT,
    _PROJECT_MGMT,
    _ADVERTISING,
    _ACCOUNT_MGMT,
    _ACCOUNTING_FIN,
    _HR,
    _SALES,
    _LEGAL,
    _MANAGEMENT,
    _BUSINESS_OPS,
    _EDUCATION,
    _HEALTHCARE,
    _MANUFACTURING,
]

# 유효한 level 필터 값 (API 실제 확인 — 2026-07-29)
VALID_LEVELS: list[str] = [
    "Entry Level",
    "Mid Level",
    "Senior Level",
]


# ── 공개 유틸 ─────────────────────────────────────────────────────────────────

def get_categories_for_function(function_name: str) -> list[str]:
    """
    taxonomy 직무명(영문)에 매핑된 The Muse category 이름 목록을 반환한다.
    매핑이 없으면 빈 리스트를 반환한다.
    """
    return THEMUSE_SEARCH_QUERIES.get(function_name, [])


def get_all_function_names() -> list[str]:
    """매핑 테이블에 등록된 모든 taxonomy 직무명 목록을 반환한다."""
    return list(THEMUSE_SEARCH_QUERIES.keys())


def get_all_category_names() -> list[str]:
    """매핑 테이블의 모든 카테고리 이름을 중복 없이 평탄화해 반환한다."""
    seen: set[str] = set()
    result: list[str] = []
    for names in THEMUSE_SEARCH_QUERIES.values():
        for name in names:
            if name not in seen:
                seen.add(name)
                result.append(name)
    return result
