"""
Remotive 전용 카테고리 매핑.

구조
----
REMOTIVE_SEARCH_QUERIES: dict[str, list[str]]
  키  : taxonomy/job_functions.py 의 표준 job_function_name 값
  값  : Remotive API category slug 목록

Remotive 공식 API 카테고리 출처
--------------------------------
GET https://remotive.com/api/remote-jobs/categories 응답 기준 (2026-07-27 확인):

  id=19   Software Development    slug=software-development
  id=18   Customer Service        slug=customer-service
  id=21   Design                  slug=design
  id=28   Marketing               slug=marketing
  id=30   Sales                   slug=sales
  id=23   Product Management      slug=product
  id=36   Project Management      slug=project-management
  id=37   Artificial Intelligence slug=artificial-intelligence
  id=24   Data and Analytics      slug=data
  id=25   Devops                  slug=devops
  id=26   Finance                 slug=finance
  id=27   Human Resources         slug=human-resources
  id=29   Quality Assurance       slug=qa
  id=32   Writing                 slug=writing
  id=38   Legal                   slug=legal
  id=39   Medical                 slug=medical
  id=40   Teaching                slug=education
  id=41   Account Management      slug=account-management
  id=42   Business Development    slug=business-development
  id=43   Communications          slug=communications
  id=44   Compliance              slug=compliance
  id=45   Engineering             slug=engineering
  id=46   Information Technology  slug=information-technology
  id=47   Knowledge Management    slug=knowledge-management
  id=48   Operations              slug=operations
  id=49   Research                slug=research
  id=50   Strategy                slug=strategy
  id=51   Supply Chain            slug=supply-chain
  id=52   Travel and Hospitality  slug=travel-hospitality
  id=22   All others              slug=all-others

설계 원칙
---------
- 하나의 taxonomy 직무가 여러 Remotive 카테고리에 걸쳐 수집될 수 있다.
  (예: "Security Engineer"는 software-development + information-technology 양쪽에 게재됨)
- 반대로 여러 taxonomy 직무가 동일한 Remotive 카테고리를 공유할 수 있다.
  (예: software-development 하나에서 Backend/Frontend/Full Stack 모두 수집)
- category slug는 Remotive API 응답의 'slug' 값과 동일하게 사용한다.
"""
from __future__ import annotations

# ── Remotive category slug 상수 (가독성용) ────────────────────────────────────
_SOFTWARE_DEV    = "software-development"
_DEVOPS          = "devops"
_AI              = "artificial-intelligence"
_DATA            = "data"
_QA              = "qa"
_ENGINEERING     = "engineering"
_IT              = "information-technology"
_DESIGN          = "design"
_PRODUCT         = "product"
_PROJECT_MGMT    = "project-management"
_MARKETING       = "marketing"
_WRITING         = "writing"
_COMMUNICATIONS  = "communications"
_FINANCE         = "finance"
_HR              = "human-resources"
_SALES           = "sales"
_ACCOUNT_MGMT    = "account-management"
_BIZ_DEV         = "business-development"
_OPERATIONS      = "operations"
_STRATEGY        = "strategy"
_LEGAL           = "legal"
_COMPLIANCE      = "compliance"
_RESEARCH        = "research"
_MEDICAL         = "medical"
_EDUCATION       = "education"
_SUPPLY_CHAIN    = "supply-chain"
_CUSTOMER_SVC    = "customer-service"


# ── 메인 매핑 ──────────────────────────────────────────────────────────────────
# taxonomy job_function_name → Remotive category slug 목록
# Remotive는 리모트 채용 특화 플랫폼이므로 글로벌 포지션 위주로 수집된다.

REMOTIVE_SEARCH_QUERIES: dict[str, list[str]] = {
    # ── Engineering & Technology ─────────────────────────────────────────────
    "Software Engineer":            [_SOFTWARE_DEV, _ENGINEERING],
    "Backend Engineer":             [_SOFTWARE_DEV],
    "Frontend Engineer":            [_SOFTWARE_DEV],
    "Full Stack Engineer":          [_SOFTWARE_DEV],
    "Mobile Engineer":              [_SOFTWARE_DEV],
    "DevOps / Platform Engineer":   [_DEVOPS],
    "Site Reliability Engineer":    [_DEVOPS],
    "Security Engineer":            [_SOFTWARE_DEV, _IT],
    "QA / Test Engineer":           [_QA],
    "Embedded / Hardware Engineer": [_ENGINEERING],
    # ── Data & Analytics ─────────────────────────────────────────────────────
    "Machine Learning Engineer":    [_AI, _SOFTWARE_DEV],
    "Data Engineer":                [_DATA],
    "Data Scientist":               [_DATA],
    "Data Analyst":                 [_DATA],
    "AI Researcher":                [_AI],
    "Business Intelligence Analyst":[_DATA],
    # ── Product & Design ─────────────────────────────────────────────────────
    "Product Manager":              [_PRODUCT],
    "UX Designer":                  [_DESIGN],
    "UI Designer":                  [_DESIGN],
    "Product Designer":             [_DESIGN],
    "UX Researcher":                [_DESIGN, _RESEARCH],
    # ── Marketing & Growth ───────────────────────────────────────────────────
    "Growth Marketer":              [_MARKETING],
    "Performance Marketer":         [_MARKETING],
    "Content Marketer":             [_MARKETING, _WRITING],
    "Brand Marketer":               [_MARKETING, _COMMUNICATIONS],
    "SEO / SEM Specialist":         [_MARKETING],
    # ── Finance & Accounting ─────────────────────────────────────────────────
    "Financial Analyst":            [_FINANCE],
    "Accountant":                   [_FINANCE],
    "Quantitative Analyst":         [_FINANCE],
    "Investment Analyst":           [_FINANCE],
    # ── Operations & Strategy ────────────────────────────────────────────────
    "Business Analyst":             [_STRATEGY, _OPERATIONS],
    "Strategy Consultant":          [_STRATEGY],
    "Operations Manager":           [_OPERATIONS],
    "Project Manager":              [_PROJECT_MGMT],
    # ── Human Resources ──────────────────────────────────────────────────────
    "Recruiter":                    [_HR],
    "HR Business Partner":          [_HR],
    "Compensation & Benefits Specialist": [_HR],
    # ── Sales & Business Development ─────────────────────────────────────────
    "Sales Engineer":               [_SALES],
    "Account Executive":            [_SALES, _ACCOUNT_MGMT],
    "Business Development Manager": [_BIZ_DEV],
    # ── Legal & Compliance ───────────────────────────────────────────────────
    "Legal Counsel":                [_LEGAL],
    "Compliance Officer":           [_COMPLIANCE, _LEGAL],
    # ── Research & Science ───────────────────────────────────────────────────
    "Research Scientist":           [_RESEARCH],
    "Research Engineer":            [_RESEARCH, _SOFTWARE_DEV],
    # ── Customer Success ─────────────────────────────────────────────────────
    "Customer Success Manager":     [_CUSTOMER_SVC, _ACCOUNT_MGMT],
    "Technical Support Engineer":   [_IT, _CUSTOMER_SVC],
    # ── Data Labeling (closest: data / AI) ───────────────────────────────────
    "Data Labeling / Annotation Specialist": [_DATA, _AI],
    # ── Education & Training ─────────────────────────────────────────────────
    "Teacher / Instructor":         [_EDUCATION],
    "Curriculum Developer":         [_EDUCATION],
    # ── Supply Chain & Logistics ─────────────────────────────────────────────
    "Supply Chain Manager":         [_SUPPLY_CHAIN],
    "Logistics Coordinator":        [_SUPPLY_CHAIN, _OPERATIONS],
    # ── Healthcare ───────────────────────────────────────────────────────────
    "Nurse":                        [_MEDICAL],
    "Healthcare Specialist":        [_MEDICAL],
}

# Remotive에서 수집할 카테고리 slug 전체 배치 목록 (기본 실행 대상)
# software-development, devops, data, ai를 핵심으로 삼고 나머지를 포함.
DEFAULT_BATCH_CATEGORIES: list[str] = [
    _SOFTWARE_DEV,
    _DEVOPS,
    _AI,
    _DATA,
    _QA,
    _DESIGN,
    _PRODUCT,
    _PROJECT_MGMT,
    _MARKETING,
    _FINANCE,
    _HR,
    _SALES,
    _BIZ_DEV,
    _OPERATIONS,
    _STRATEGY,
    _LEGAL,
    _COMPLIANCE,
    _RESEARCH,
    _CUSTOMER_SVC,
    _EDUCATION,
    _MEDICAL,
    _SUPPLY_CHAIN,
]


# ── 공개 유틸 ─────────────────────────────────────────────────────────────────

def get_slugs_for_function(function_name: str) -> list[str]:
    """
    taxonomy 직무명(영문)에 매핑된 Remotive category slug 목록을 반환한다.
    매핑이 없으면 빈 리스트를 반환한다.
    """
    return REMOTIVE_SEARCH_QUERIES.get(function_name, [])


def get_all_function_names() -> list[str]:
    """매핑 테이블에 등록된 모든 taxonomy 직무명 목록을 반환한다."""
    return list(REMOTIVE_SEARCH_QUERIES.keys())


def get_all_category_slugs() -> list[str]:
    """매핑 테이블의 모든 카테고리 slug를 중복 없이 평탄화해 반환한다."""
    seen: set[str] = set()
    result: list[str] = []
    for slugs in REMOTIVE_SEARCH_QUERIES.values():
        for slug in slugs:
            if slug not in seen:
                seen.add(slug)
                result.append(slug)
    return result
