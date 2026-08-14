"""
USAJobs 전용 검색어 매핑.

0단계 조사 결과 (2026-07-30)
-----------------------------
내부 검색 API: POST https://www.usajobs.gov/Search/ExecuteSearch
  - Keyword 파라미터로 영문 키워드 검색 (인증/API 키 불필요)
  - HiringPath=["public"] 로 일반 공개 공고 필터

매핑 구조
---------
USAJOBS_KEYWORD_QUERIES : dict[str, list[str]]
  키 : taxonomy/job_functions.py 표준 job_function_name (영문)
  값 : ExecuteSearch Keyword 에 순서대로 전달할 영문 검색어 목록

영문 직무 시드를 정리했다. 연방 공고 특성상 영문만 사용한다.
"""
from __future__ import annotations

USAJOBS_KEYWORD_QUERIES: dict[str, list[str]] = {
    # ── Engineering & Technology ─────────────────────────────────────────────
    "Software Engineer": [
        "software engineer",
        "software developer",
    ],
    "Backend Engineer": [
        "backend developer",
        "backend engineer",
        "server-side developer",
    ],
    "Frontend Engineer": [
        "frontend developer",
        "front end developer",
        "frontend engineer",
    ],
    "Full Stack Engineer": [
        "full stack developer",
        "full stack engineer",
    ],
    "Mobile Engineer": [
        "mobile developer",
        "iOS developer",
        "Android developer",
    ],
    "DevOps / Platform Engineer": [
        "DevOps engineer",
        "platform engineer",
        "cloud engineer",
        "infrastructure engineer",
    ],
    "Site Reliability Engineer": [
        "site reliability engineer",
        "SRE",
    ],
    "Security Engineer": [
        "security engineer",
        "cybersecurity engineer",
        "information security analyst",
    ],
    "QA / Test Engineer": [
        "QA engineer",
        "test engineer",
        "quality assurance engineer",
    ],
    "Embedded / Hardware Engineer": [
        "embedded engineer",
        "hardware engineer",
    ],
    # ── Data & Analytics ─────────────────────────────────────────────────────
    "Machine Learning Engineer": [
        "machine learning engineer",
        "ML engineer",
        "AI engineer",
    ],
    "Data Engineer": [
        "data engineer",
        "analytics engineer",
        "ETL developer",
    ],
    "Data Scientist": [
        "data scientist",
    ],
    "Data Analyst": [
        "data analyst",
        "business intelligence analyst",
    ],
    "AI Researcher": [
        "AI researcher",
        "research scientist machine learning",
    ],
    "Business Intelligence Analyst": [
        "business intelligence analyst",
        "BI analyst",
    ],
    # ── Product & Design ─────────────────────────────────────────────────────
    "Product Manager": [
        "product manager",
        "technical product manager",
    ],
    "UX Designer": [
        "UX designer",
        "user experience designer",
    ],
    "UI Designer": [
        "UI designer",
        "user interface designer",
    ],
    "Product Designer": [
        "product designer",
    ],
    "UX Researcher": [
        "UX researcher",
        "user researcher",
    ],
    # ── Marketing & Growth ───────────────────────────────────────────────────
    "Growth Marketer": [
        "growth marketer",
        "growth manager",
    ],
    "Performance Marketer": [
        "performance marketer",
        "paid media manager",
    ],
    "Content Marketer": [
        "content marketer",
        "content strategist",
    ],
    "Brand Marketer": [
        "brand marketer",
        "brand manager",
    ],
    "SEO / SEM Specialist": [
        "SEO specialist",
        "SEM specialist",
    ],
    # ── Finance & Accounting ─────────────────────────────────────────────────
    "Financial Analyst": [
        "financial analyst",
        "finance analyst",
    ],
    "Accountant": [
        "accountant",
        "staff accountant",
    ],
    "Quantitative Analyst": [
        "quantitative analyst",
        "quant analyst",
    ],
    "Investment Analyst": [
        "investment analyst",
        "equity research analyst",
    ],
    # ── Operations & Strategy ────────────────────────────────────────────────
    "Business Analyst": [
        "business analyst",
        "business systems analyst",
    ],
    "Strategy Consultant": [
        "strategy consultant",
        "management consultant",
    ],
    "Operations Manager": [
        "operations manager",
    ],
    "Project Manager": [
        "project manager",
        "program manager",
    ],
    # ── Human Resources ──────────────────────────────────────────────────────
    "Recruiter": [
        "recruiter",
        "technical recruiter",
        "talent acquisition specialist",
    ],
    "HR Business Partner": [
        "HR business partner",
        "human resources business partner",
    ],
    "Compensation & Benefits Specialist": [
        "compensation specialist",
        "benefits specialist",
    ],
    # ── Sales & Business Development ─────────────────────────────────────────
    "Sales Engineer": [
        "sales engineer",
        "solutions engineer",
    ],
    "Account Executive": [
        "account executive",
        "sales representative",
    ],
    "Business Development Manager": [
        "business development manager",
        "partnerships manager",
    ],
    # ── Legal & Compliance ───────────────────────────────────────────────────
    "Legal Counsel": [
        "legal counsel",
        "attorney advisor",
    ],
    "Compliance Officer": [
        "compliance officer",
        "compliance specialist",
    ],
    # ── Research & Science ───────────────────────────────────────────────────
    "Research Scientist": [
        "research scientist",
    ],
    "Research Engineer": [
        "research engineer",
    ],
    # ── Customer Success ─────────────────────────────────────────────────────
    "Customer Success Manager": [
        "customer success manager",
    ],
    "Technical Support Engineer": [
        "technical support engineer",
        "IT specialist",
    ],
    # ── Data Labeling ────────────────────────────────────────────────────────
    "Data Labeling / Annotation Specialist": [
        "data labeling",
        "data annotation",
        "annotation specialist",
    ],
    # ── Education & Training ─────────────────────────────────────────────────
    "Teacher / Instructor": [
        "teacher",
        "instructor",
        "educator",
    ],
    "Curriculum Developer": [
        "curriculum developer",
        "instructional designer",
    ],
    # ── Supply Chain & Logistics ─────────────────────────────────────────────
    "Supply Chain Manager": [
        "supply chain manager",
        "supply chain analyst",
    ],
    "Logistics Coordinator": [
        "logistics coordinator",
        "logistics specialist",
    ],
    # ── Healthcare ───────────────────────────────────────────────────────────
    "Nurse": [
        "nurse",
        "registered nurse",
        "RN",
    ],
    "Healthcare Specialist": [
        "healthcare specialist",
        "clinical specialist",
    ],
}


def get_keywords_for_function(function_name: str) -> list[str]:
    """
    taxonomy 직무명에 해당하는 USAJobs Keyword 목록을 반환한다.
    매핑이 없으면 빈 리스트.
    """
    return list(USAJOBS_KEYWORD_QUERIES.get(function_name, []))


def get_all_function_names() -> list[str]:
    """매핑 테이블에 등록된 모든 taxonomy 직무명 목록을 반환한다."""
    return list(USAJOBS_KEYWORD_QUERIES.keys())
