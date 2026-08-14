"""
원티드 전용 직무 카테고리 매핑.

구조
----
WANTED_SEARCH_QUERIES: dict[str, list[int]]
  키  : taxonomy/job_functions.py 의 표준 job_function_name 값
  값  : 원티드 내부 API tag_type_ids 목록 (sub_tag ID 기준)

원티드 API 방식
--------------
원티드 검색/목록 페이지는 CSR 렌더링이지만, 내부 JSON API가 공개 접근 가능하다.
  - 목록 API : GET /api/v4/jobs?country=kr&tag_type_ids={id,...}&...
  - 태그 목록: GET /api/v4/tags?country=kr  → id/title/sub_tags 구조 반환

tag_type_ids 출처
-----------------
https://www.wanted.co.kr/api/v4/tags?country=kr 응답 기준 (2026-07-27 확인):
  부모 카테고리 → sub_tag id: 직무명 순으로 아래 주석에 정리.

사람인·잡코리아와 동일한 taxonomy 키 구조를 유지한다.
"""
from __future__ import annotations

# ── 원티드 tag_type_ids 상수 (가독성용) ─────────────────────────────────────
# 개발 (parent_id=518)
_SERVER_DEV          = 872    # 서버 개발자
_ML_ENGINEER         = 1634   # 머신러닝 엔지니어
_PYTHON_DEV          = 899    # 파이썬 개발자
_SW_ENGINEER         = 10110  # 소프트웨어 엔지니어
_JAVA_DEV            = 660    # 자바 개발자
_DEVOPS              = 674    # DevOps / 시스템 관리자
_FRONTEND_DEV        = 669    # 프론트엔드 개발자
_DATA_ENGINEER       = 655    # 데이터 엔지니어
_DATA_SCIENTIST      = 1024   # 데이터 사이언티스트
_CPP_DEV             = 900    # C,C++ 개발자
_SYSNET_ADMIN        = 665    # 시스템,네트워크 관리자
_EMBEDDED_DEV        = 658    # 임베디드 개발자
_PM_DEV_SIDE         = 876    # 프로덕트 매니저 (개발 카테고리)
_WEB_DEV             = 873    # 웹 개발자
_NODEJS_DEV          = 895    # Node.js 개발자
_DEV_MANAGER         = 877    # 개발 매니저
_TECH_SUPPORT        = 1026   # 기술지원
_BIGDATA_ENGINEER    = 1025   # 빅데이터 엔지니어
_QA_ENGINEER         = 676    # QA,테스트 엔지니어
_HW_ENGINEER         = 672    # 하드웨어 엔지니어
_ANDROID_DEV         = 677    # 안드로이드 개발자
_IOS_DEV             = 678    # iOS 개발자
_CROSSPLATFORM_DEV   = 10111  # 크로스플랫폼 앱 개발자
_BI_ENGINEER         = 1022   # BI 엔지니어

# 정보보호 (parent_id=10566)
_SECURITY_ENGINEER   = 671    # 보안 엔지니어

# 디자인 (parent_id=511)
_UI_DESIGNER         = 597    # UI,GUI 디자이너
_UX_DESIGNER         = 599    # UX 디자이너
_PRODUCT_DESIGNER    = 603    # 제품 디자이너
_UX_RESEARCHER       = 10530  # UX 리서처

# 마케팅·광고 (parent_id=523)
_GROWTH_HACKER       = 717    # 그로스 해커
_PERF_MARKETER       = 10138  # 퍼포먼스 마케터
_CONTENT_MARKETER    = 1635   # 콘텐츠 마케터
_BRAND_MARKETER      = 707    # 브랜드 마케터
_KEYWORD_AD          = 722    # 키워드광고 (SEO/SEM)

# 경영·비즈니스 (parent_id=507)
_PM_BIZ_SIDE         = 559    # PM·PO
_STRATEGY_PLANNER    = 563    # 전략 기획자
_CONSULTANT          = 570    # 컨설턴트
_OPERATIONS_MANAGER  = 554    # 운영 매니저
_BIZ_DEV_PLANNER     = 564    # 사업개발·기획자
_DATA_ANALYST        = 656    # 데이터 분석가

# 금융 (parent_id=508)
_ACCOUNTING          = 534    # 회계담당
_FINANCIAL_ANALYST   = 538    # 재무 분석가
_QUANT_ANALYST       = 934    # 금융공학자
_INVESTMENT          = 10056  # 투자·증권

# 경영·비즈니스 회계 (parent_id=507)
_ACCOUNTING_BIZ      = 1034   # 회계·경리

# HR (parent_id=517)
_RECRUITER           = 644    # 리크루터
_HRBP                = 1043   # HRBP
_COMP_BENEFITS       = 645    # 평가·보상

# 영업 (parent_id=530)
_SALES_ENGINEER      = 773    # 세일즈 엔지니어
_B2B_SALES           = 1036   # 기업영업
_CSM                 = 1037   # 고객성공매니저

# 법률·법집행기관 (parent_id=521)
_LEGAL_COUNSEL       = 1002   # 법무담당
_COMPLIANCE          = 938    # 준법감시인

# 의료·제약·바이오 (parent_id=515)
_RESEARCHER          = 739    # 연구원
_NURSE               = 627    # 간호사
_CLINICAL_NURSE      = 736    # 임상시험 간호사
_HOSPITAL_COORD      = 10134  # 병원 코디네이터

# 고객서비스·리테일 (parent_id=510)
_HEALTHCARE_MGR      = 1637   # 헬스케어매니저

# HR — 교육 관련 (parent_id=517)
_TEACHER             = 608    # 교사
_CORP_INSTRUCTOR     = 1044   # 사내 강사
_ELEARNING           = 651    # E-러닝
_TECH_EDU            = 611    # 기술 교육
_PROFESSOR           = 1042   # 교수

# 물류·무역 (parent_id=532)
_LOGISTICS           = 783    # 물류담당
_LOGISTICS_ANALYST   = 782    # 물류 분석가
_DISTRIBUTION_MGR    = 10149  # 유통 관리자
_INBOUND_OUTBOUND    = 10148  # 입·출고 관리자
_TRANSPORT_MGR       = 786    # 운송 관리자


# ── 메인 매핑 ─────────────────────────────────────────────────────────────────

WANTED_SEARCH_QUERIES: dict[str, list[int]] = {
    # ── Engineering & Technology ─────────────────────────────────────────────
    "Software Engineer": [_SW_ENGINEER, _WEB_DEV],
    "Backend Engineer": [_SERVER_DEV],
    "Frontend Engineer": [_FRONTEND_DEV],
    "Full Stack Engineer": [_WEB_DEV, _SW_ENGINEER],
    "Mobile Engineer": [_ANDROID_DEV, _IOS_DEV, _CROSSPLATFORM_DEV],
    "DevOps / Platform Engineer": [_DEVOPS],
    "Site Reliability Engineer": [_SYSNET_ADMIN, _DEVOPS],
    "Security Engineer": [_SECURITY_ENGINEER],
    "QA / Test Engineer": [_QA_ENGINEER],
    "Embedded / Hardware Engineer": [_EMBEDDED_DEV, _HW_ENGINEER],
    # ── Data & Analytics ─────────────────────────────────────────────────────
    "Machine Learning Engineer": [_ML_ENGINEER],
    "Data Engineer": [_DATA_ENGINEER, _BIGDATA_ENGINEER],
    "Data Scientist": [_DATA_SCIENTIST],
    "Data Analyst": [_DATA_ANALYST],
    "AI Researcher": [_ML_ENGINEER, _DATA_SCIENTIST],
    "Business Intelligence Analyst": [_BI_ENGINEER],
    # ── Product & Design ─────────────────────────────────────────────────────
    "Product Manager": [_PM_BIZ_SIDE, _PM_DEV_SIDE],
    "UX Designer": [_UX_DESIGNER],
    "UI Designer": [_UI_DESIGNER],
    "Product Designer": [_PRODUCT_DESIGNER],
    "UX Researcher": [_UX_RESEARCHER],
    # ── Marketing & Growth ───────────────────────────────────────────────────
    "Growth Marketer": [_GROWTH_HACKER],
    "Performance Marketer": [_PERF_MARKETER],
    "Content Marketer": [_CONTENT_MARKETER],
    "Brand Marketer": [_BRAND_MARKETER],
    "SEO / SEM Specialist": [_KEYWORD_AD],
    # ── Finance & Accounting ─────────────────────────────────────────────────
    "Financial Analyst": [_FINANCIAL_ANALYST],
    "Accountant": [_ACCOUNTING, _ACCOUNTING_BIZ],
    "Quantitative Analyst": [_QUANT_ANALYST],
    "Investment Analyst": [_INVESTMENT],
    # ── Operations & Strategy ────────────────────────────────────────────────
    "Business Analyst": [_STRATEGY_PLANNER],
    "Strategy Consultant": [_CONSULTANT],
    "Operations Manager": [_OPERATIONS_MANAGER],
    "Project Manager": [_DEV_MANAGER, _BIZ_DEV_PLANNER],
    # ── Human Resources ──────────────────────────────────────────────────────
    "Recruiter": [_RECRUITER],
    "HR Business Partner": [_HRBP],
    "Compensation & Benefits Specialist": [_COMP_BENEFITS],
    # ── Sales & Business Development ─────────────────────────────────────────
    "Sales Engineer": [_SALES_ENGINEER],
    "Account Executive": [_B2B_SALES],
    "Business Development Manager": [_BIZ_DEV_PLANNER],
    # ── Legal & Compliance ───────────────────────────────────────────────────
    "Legal Counsel": [_LEGAL_COUNSEL],
    "Compliance Officer": [_COMPLIANCE],
    # ── Research & Science ───────────────────────────────────────────────────
    "Research Scientist": [_RESEARCHER],
    "Research Engineer": [_RESEARCHER, _ML_ENGINEER],
    # ── Customer Success ─────────────────────────────────────────────────────
    "Customer Success Manager": [_CSM],
    "Technical Support Engineer": [_TECH_SUPPORT],
    # ── Data Labeling (전용 태그 없음 → 데이터/ML 근접 태그) ────────────────
    "Data Labeling / Annotation Specialist": [_DATA_ANALYST, _ML_ENGINEER],
    # ── Education & Training ─────────────────────────────────────────────────
    "Teacher / Instructor": [_TEACHER, _CORP_INSTRUCTOR, _PROFESSOR],
    "Curriculum Developer": [_ELEARNING, _TECH_EDU],
    # ── Supply Chain & Logistics ─────────────────────────────────────────────
    "Supply Chain Manager": [_LOGISTICS_ANALYST, _DISTRIBUTION_MGR, _TRANSPORT_MGR],
    "Logistics Coordinator": [_LOGISTICS, _INBOUND_OUTBOUND],
    # ── Healthcare ───────────────────────────────────────────────────────────
    "Nurse": [_NURSE, _CLINICAL_NURSE],
    "Healthcare Specialist": [_HEALTHCARE_MGR, _HOSPITAL_COORD],
}


# ── 한글 직무명 → taxonomy 직무명 별칭 ─────────────────────────────────────────
# `--function` 인수에 한글을 입력했을 때도 매핑되도록 지원한다.

KOREAN_ALIASES: dict[str, str] = {
    # Engineering & Technology
    "소프트웨어 엔지니어": "Software Engineer",
    "소프트웨어 개발자": "Software Engineer",
    "백엔드 개발자": "Backend Engineer",
    "백엔드 엔지니어": "Backend Engineer",
    "서버 개발자": "Backend Engineer",
    "프론트엔드 개발자": "Frontend Engineer",
    "프론트엔드 엔지니어": "Frontend Engineer",
    "풀스택 개발자": "Full Stack Engineer",
    "풀스택 엔지니어": "Full Stack Engineer",
    "모바일 개발자": "Mobile Engineer",
    "iOS 개발자": "Mobile Engineer",
    "안드로이드 개발자": "Mobile Engineer",
    "devops 엔지니어": "DevOps / Platform Engineer",
    "클라우드 엔지니어": "DevOps / Platform Engineer",
    "인프라 엔지니어": "DevOps / Platform Engineer",
    "sre": "Site Reliability Engineer",
    "보안 엔지니어": "Security Engineer",
    "정보보안": "Security Engineer",
    "qa 엔지니어": "QA / Test Engineer",
    "테스트 엔지니어": "QA / Test Engineer",
    "임베디드 개발자": "Embedded / Hardware Engineer",
    "하드웨어 엔지니어": "Embedded / Hardware Engineer",
    # Data & Analytics
    "머신러닝 엔지니어": "Machine Learning Engineer",
    "ml 엔지니어": "Machine Learning Engineer",
    "데이터 엔지니어": "Data Engineer",
    "데이터 사이언티스트": "Data Scientist",
    "데이터 분석가": "Data Analyst",
    "ai 연구원": "AI Researcher",
    "bi 개발자": "Business Intelligence Analyst",
    # Product & Design
    "프로덕트 매니저": "Product Manager",
    "pm": "Product Manager",
    "서비스 기획자": "Product Manager",
    "ux 디자이너": "UX Designer",
    "ui 디자이너": "UI Designer",
    "프로덕트 디자이너": "Product Designer",
    "ux 리서처": "UX Researcher",
    # Marketing & Growth
    "그로스 마케터": "Growth Marketer",
    "퍼포먼스 마케터": "Performance Marketer",
    "콘텐츠 마케터": "Content Marketer",
    "브랜드 마케터": "Brand Marketer",
    "seo 전문가": "SEO / SEM Specialist",
    # Finance & Accounting
    "재무 분석가": "Financial Analyst",
    "회계사": "Accountant",
    "회계 담당": "Accountant",
    "퀀트": "Quantitative Analyst",
    "투자 분석가": "Investment Analyst",
    # Operations & Strategy
    "비즈니스 애널리스트": "Business Analyst",
    "전략 컨설턴트": "Strategy Consultant",
    "운영 매니저": "Operations Manager",
    "프로젝트 매니저": "Project Manager",
    # Human Resources
    "리크루터": "Recruiter",
    "채용 담당": "Recruiter",
    "hrbp": "HR Business Partner",
    "인사 담당": "HR Business Partner",
    "보상 전문가": "Compensation & Benefits Specialist",
    # Sales & Business Development
    "세일즈 엔지니어": "Sales Engineer",
    "영업 담당": "Account Executive",
    "사업개발": "Business Development Manager",
    # Legal & Compliance
    "법무 담당": "Legal Counsel",
    "컴플라이언스": "Compliance Officer",
    # Research & Science
    "연구원": "Research Scientist",
    "r&d 엔지니어": "Research Engineer",
    # Customer Success
    "고객 성공 매니저": "Customer Success Manager",
    "cs 매니저": "Customer Success Manager",
    "기술 지원": "Technical Support Engineer",
}


# ── 공개 유틸 ─────────────────────────────────────────────────────────────────

def get_tag_ids_for_function(function_name: str) -> list[int]:
    """
    taxonomy 직무명(영문) 또는 한글 별칭에 매핑된 원티드 tag_type_ids 목록을 반환한다.
    """
    # 1순위: 영문 taxonomy 직접 매핑
    ids = WANTED_SEARCH_QUERIES.get(function_name)
    if ids is not None:
        return ids

    # 2순위: 한글 별칭 → taxonomy 영문명 → tag_type_ids
    canonical = KOREAN_ALIASES.get(function_name.lower())
    if canonical:
        return WANTED_SEARCH_QUERIES.get(canonical, [])

    return []


def get_all_function_names() -> list[str]:
    """매핑 테이블에 등록된 모든 taxonomy 직무명 목록을 반환한다."""
    return list(WANTED_SEARCH_QUERIES.keys())


def get_all_tag_ids() -> list[int]:
    """매핑 테이블의 모든 tag_type_ids를 중복 없이 평탄화해 반환한다."""
    seen: set[int] = set()
    result: list[int] = []
    for ids in WANTED_SEARCH_QUERIES.values():
        for tag_id in ids:
            if tag_id not in seen:
                seen.add(tag_id)
                result.append(tag_id)
    return result
