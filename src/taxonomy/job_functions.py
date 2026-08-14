"""
모든 사이트가 공유하는 표준 직무(Job Function) 분류.
job_postings.job_function_name 필드의 허용값 기준.

각 직무는 job_category_name 하나에 귀속된다.
이 파일은 사람이 직접 관리한다 — discovery 스크립트가 덮어쓰지 않는다.
"""
from __future__ import annotations

JOB_FUNCTIONS: list[dict[str, str]] = [
    # Engineering & Technology
    {"category": "Engineering & Technology", "function": "Software Engineer"},
    {"category": "Engineering & Technology", "function": "Backend Engineer"},
    {"category": "Engineering & Technology", "function": "Frontend Engineer"},
    {"category": "Engineering & Technology", "function": "Full Stack Engineer"},
    {"category": "Engineering & Technology", "function": "Mobile Engineer"},
    {"category": "Engineering & Technology", "function": "DevOps / Platform Engineer"},
    {"category": "Engineering & Technology", "function": "Site Reliability Engineer"},
    {"category": "Engineering & Technology", "function": "Security Engineer"},
    {"category": "Engineering & Technology", "function": "QA / Test Engineer"},
    {"category": "Engineering & Technology", "function": "Embedded / Hardware Engineer"},
    # Data & Analytics
    {"category": "Data & Analytics", "function": "Machine Learning Engineer"},
    {"category": "Data & Analytics", "function": "Data Engineer"},
    {"category": "Data & Analytics", "function": "Data Scientist"},
    {"category": "Data & Analytics", "function": "Data Analyst"},
    {"category": "Data & Analytics", "function": "AI Researcher"},
    {"category": "Data & Analytics", "function": "Business Intelligence Analyst"},
    {"category": "Data & Analytics", "function": "Data Labeling / Annotation Specialist"},
    # Product & Design
    {"category": "Product & Design", "function": "Product Manager"},
    {"category": "Product & Design", "function": "UX Designer"},
    {"category": "Product & Design", "function": "UI Designer"},
    {"category": "Product & Design", "function": "Product Designer"},
    {"category": "Product & Design", "function": "UX Researcher"},
    # Marketing & Growth
    {"category": "Marketing & Growth", "function": "Growth Marketer"},
    {"category": "Marketing & Growth", "function": "Performance Marketer"},
    {"category": "Marketing & Growth", "function": "Content Marketer"},
    {"category": "Marketing & Growth", "function": "Brand Marketer"},
    {"category": "Marketing & Growth", "function": "SEO / SEM Specialist"},
    # Finance & Accounting
    {"category": "Finance & Accounting", "function": "Financial Analyst"},
    {"category": "Finance & Accounting", "function": "Accountant"},
    {"category": "Finance & Accounting", "function": "Quantitative Analyst"},
    {"category": "Finance & Accounting", "function": "Investment Analyst"},
    # Operations & Strategy
    {"category": "Operations & Strategy", "function": "Business Analyst"},
    {"category": "Operations & Strategy", "function": "Strategy Consultant"},
    {"category": "Operations & Strategy", "function": "Operations Manager"},
    {"category": "Operations & Strategy", "function": "Project Manager"},
    # Human Resources
    {"category": "Human Resources", "function": "Recruiter"},
    {"category": "Human Resources", "function": "HR Business Partner"},
    {"category": "Human Resources", "function": "Compensation & Benefits Specialist"},
    # Sales & Business Development
    {"category": "Sales & Business Development", "function": "Sales Engineer"},
    {"category": "Sales & Business Development", "function": "Account Executive"},
    {"category": "Sales & Business Development", "function": "Business Development Manager"},
    # Legal & Compliance
    {"category": "Legal & Compliance", "function": "Legal Counsel"},
    {"category": "Legal & Compliance", "function": "Compliance Officer"},
    # Research & Science
    {"category": "Research & Science", "function": "Research Scientist"},
    {"category": "Research & Science", "function": "Research Engineer"},
    # Customer Success
    {"category": "Customer Success", "function": "Customer Success Manager"},
    {"category": "Customer Success", "function": "Technical Support Engineer"},
    # Education & Training
    {"category": "Education & Training", "function": "Teacher / Instructor"},
    {"category": "Education & Training", "function": "Curriculum Developer"},
    # Supply Chain & Logistics
    {"category": "Supply Chain & Logistics", "function": "Supply Chain Manager"},
    {"category": "Supply Chain & Logistics", "function": "Logistics Coordinator"},
    # Healthcare
    {"category": "Healthcare", "function": "Nurse"},
    {"category": "Healthcare", "function": "Healthcare Specialist"},
]

_FUNCTION_SET: frozenset[str] = frozenset(jf["function"] for jf in JOB_FUNCTIONS)
_FUNCTION_TO_CATEGORY: dict[str, str] = {
    jf["function"]: jf["category"] for jf in JOB_FUNCTIONS
}


def get_function_names() -> list[str]:
    """표준 직무명 목록을 반환한다."""
    return [jf["function"] for jf in JOB_FUNCTIONS]


def get_category_for_function(function_name: str) -> str | None:
    """직무명에 해당하는 직군명을 반환한다. 없으면 None."""
    return _FUNCTION_TO_CATEGORY.get(function_name)


def is_valid_function(name: str) -> bool:
    return name in _FUNCTION_SET
