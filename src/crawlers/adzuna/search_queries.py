"""
Adzuna 검색어 매핑.

HTML SERP 는 q(키워드) + 국가별 도메인으로 검색한다.
taxonomy job_function_name → 검색 키워드 목록.
"""
from __future__ import annotations

ADZUNA_SEARCH_QUERIES: dict[str, list[str]] = {
    "Software Engineer": ['software engineer', 'software developer'],
    "Backend Engineer": ['backend engineer', 'backend developer', 'server engineer'],
    "Frontend Engineer": ['frontend engineer', 'frontend developer', 'react developer'],
    "Full Stack Engineer": ['full stack engineer', 'fullstack developer'],
    "Mobile Engineer": ['mobile engineer', 'android developer', 'ios developer'],
    "DevOps / Platform Engineer": ['devops engineer', 'platform engineer', 'sre'],
    "Site Reliability Engineer": ['site reliability engineer', 'sre'],
    "Security Engineer": ['security engineer', 'cybersecurity'],
    "QA / Test Engineer": ['qa engineer', 'test engineer', 'quality assurance'],
    "Embedded / Hardware Engineer": ['embedded engineer', 'hardware engineer', 'firmware engineer'],
    "Machine Learning Engineer": ['machine learning engineer', 'ml engineer'],
    "Data Engineer": ['data engineer'],
    "Data Scientist": ['data scientist'],
    "Data Analyst": ['data analyst'],
    "AI Researcher": ['AI researcher', 'research scientist machine learning', 'NLP researcher'],
    "Business Intelligence Analyst": ['business intelligence analyst', 'BI analyst', 'BI developer'],
    "Data Labeling / Annotation Specialist": ['data labeling', 'data annotation', 'annotation specialist'],
    "Product Manager": ['product manager'],
    "UX Designer": ['ux designer'],
    "UI Designer": ['ui designer'],
    "Product Designer": ['product designer'],
    "UX Researcher": ['UX researcher', 'user researcher'],
    "Growth Marketer": ['growth marketer', 'growth hacker', 'growth manager'],
    "Performance Marketer": ['performance marketer', 'performance marketing manager', 'paid media manager'],
    "Content Marketer": ['content marketer', 'content marketing manager', 'content strategist'],
    "Brand Marketer": ['brand marketer', 'brand manager', 'brand strategist'],
    "SEO / SEM Specialist": ['SEO specialist', 'SEM specialist', 'search engine optimization'],
    "Financial Analyst": ['financial analyst', 'finance analyst', 'FP&A analyst'],
    "Accountant": ['accountant', 'staff accountant', 'senior accountant'],
    "Quantitative Analyst": ['quantitative analyst', 'quant analyst', 'quantitative researcher'],
    "Investment Analyst": ['investment analyst', 'equity research analyst', 'portfolio analyst'],
    "Business Analyst": ['business analyst', 'business systems analyst'],
    "Strategy Consultant": ['strategy consultant', 'management consultant'],
    "Operations Manager": ['operations manager', 'business operations manager'],
    "Project Manager": ['project manager', 'program manager', 'scrum master'],
    "Recruiter": ['recruiter', 'technical recruiter', 'talent acquisition specialist'],
    "HR Business Partner": ['HR business partner', 'human resources business partner'],
    "Compensation & Benefits Specialist": ['compensation specialist', 'benefits specialist', 'compensation and benefits'],
    "Sales Engineer": ['sales engineer', 'solutions engineer', 'presales engineer'],
    "Account Executive": ['account executive', 'enterprise account executive', 'sales representative'],
    "Business Development Manager": ['business development manager', 'partnerships manager'],
    "Legal Counsel": ['legal counsel', 'corporate counsel', 'in-house counsel'],
    "Compliance Officer": ['compliance officer', 'compliance specialist'],
    "Research Scientist": ['research scientist'],
    "Research Engineer": ['research engineer'],
    "Customer Success Manager": ['customer success manager', 'customer success specialist'],
    "Technical Support Engineer": ['technical support engineer', 'IT support specialist', 'help desk engineer'],
    "Teacher / Instructor": ['teacher', 'instructor', 'educator'],
    "Curriculum Developer": ['curriculum developer', 'instructional designer', 'curriculum designer'],
    "Supply Chain Manager": ['supply chain manager', 'supply chain analyst'],
    "Logistics Coordinator": ['logistics coordinator', 'logistics specialist'],
    "Nurse": ['nurse', 'registered nurse', 'RN'],
    "Healthcare Specialist": ['healthcare specialist', 'clinical specialist', 'healthcare coordinator'],
}

# 기본 배치: IT 핵심 직무
DEFAULT_BATCH_FUNCTIONS: list[str] = [
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Engineer",
    "Software Engineer",
    "DevOps / Platform Engineer",
    "Machine Learning Engineer",
    "Data Engineer",
    "Data Scientist",
]

# HTML 크롤 가능 국가 (www.adzuna.com US 는 CAPTCHA 로 제외)
DEFAULT_COUNTRIES: list[str] = ["gb", "au"]


def get_queries_for_function(function_name: str) -> list[str]:
    return list(ADZUNA_SEARCH_QUERIES.get(function_name, [function_name]))


def get_all_queries() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for queries in ADZUNA_SEARCH_QUERIES.values():
        for q in queries:
            if q not in seen:
                seen.add(q)
                out.append(q)
    return out
