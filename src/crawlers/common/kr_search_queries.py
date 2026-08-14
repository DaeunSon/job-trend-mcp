"""
국내 채용 플랫폼 공통 검색어 맵 (사람인 · 잡코리아).

구조
----
KR_JOB_SEARCH_QUERIES: dict[str, list[str]]
  키  : taxonomy/job_functions.py 의 표준 job_function_name 값
  값  : 사이트에 실제로 던질 검색어 목록 (한글 중심, 영문 병기)

사이트별 search_queries.py 는 이 맵을 재수출한다.
사이트 전용 변형이 필요해지면 해당 모듈에서만 override 하면 된다.
"""
from __future__ import annotations

KR_JOB_SEARCH_QUERIES: dict[str, list[str]] = {
    # ── Engineering & Technology ──────────────────────────────────────────
    "Software Engineer": [
        "소프트웨어 개발자",
        "소프트웨어 엔지니어",
        "software engineer",
    ],
    "Backend Engineer": [
        "백엔드 개발자",
        "서버 개발자",
        "backend developer",
    ],
    "Frontend Engineer": [
        "프론트엔드 개발자",
        "웹 퍼블리셔",
        "frontend developer",
        "React 개발자",
    ],
    "Full Stack Engineer": [
        "풀스택 개발자",
        "full stack developer",
    ],
    "Mobile Engineer": [
        "모바일 개발자",
        "iOS 개발자",
        "안드로이드 개발자",
        "앱 개발자",
    ],
    "DevOps / Platform Engineer": [
        "DevOps 엔지니어",
        "클라우드 엔지니어",
        "인프라 엔지니어",
        "시스템 엔지니어",
    ],
    "Site Reliability Engineer": [
        "SRE",
        "site reliability engineer",
    ],
    "Security Engineer": [
        "보안 엔지니어",
        "정보보안",
        "보안 관제",
    ],
    "QA / Test Engineer": [
        "QA 엔지니어",
        "테스트 엔지니어",
        "품질관리",
    ],
    "Embedded / Hardware Engineer": [
        "임베디드 개발자",
        "펌웨어 개발자",
        "하드웨어 엔지니어",
    ],
    # ── Data & Analytics ──────────────────────────────────────────────────
    "Machine Learning Engineer": [
        "머신러닝 엔지니어",
        "AI 엔지니어",
        "딥러닝 엔지니어",
        "machine learning engineer",
    ],
    "Data Engineer": [
        "데이터 엔지니어",
        "데이터 파이프라인",
        "ETL 개발자",
    ],
    "Data Scientist": [
        "데이터 사이언티스트",
        "data scientist",
    ],
    "Data Analyst": [
        "데이터 분석가",
        "데이터 애널리스트",
        "BI 분석가",
    ],
    "AI Researcher": [
        "AI 연구원",
        "인공지능 연구원",
        "NLP 연구원",
    ],
    "Business Intelligence Analyst": [
        "BI 개발자",
        "경영정보 분석",
        "비즈니스 인텔리전스",
    ],
    # ── Product & Design ──────────────────────────────────────────────────
    "Product Manager": [
        "프로덕트 매니저",
        "PM",
        "서비스 기획자",
    ],
    "UX Designer": [
        "UX 디자이너",
        "UX 기획자",
        "사용자경험 디자이너",
    ],
    "UI Designer": [
        "UI 디자이너",
        "웹 디자이너",
        "앱 디자이너",
    ],
    "Product Designer": [
        "프로덕트 디자이너",
        "product designer",
    ],
    "UX Researcher": [
        "UX 리서처",
        "사용자 리서처",
    ],
    # ── Marketing & Growth ────────────────────────────────────────────────
    "Growth Marketer": [
        "그로스 마케터",
        "그로스 해킹",
        "퍼포먼스 마케팅",
    ],
    "Performance Marketer": [
        "퍼포먼스 마케터",
        "디지털 마케터",
        "광고 운영",
    ],
    "Content Marketer": [
        "콘텐츠 마케터",
        "콘텐츠 에디터",
        "카피라이터",
    ],
    "Brand Marketer": [
        "브랜드 마케터",
        "브랜드 매니저",
    ],
    "SEO / SEM Specialist": [
        "SEO 전문가",
        "검색엔진최적화",
        "키워드 광고",
    ],
    # ── Finance & Accounting ──────────────────────────────────────────────
    "Financial Analyst": [
        "재무 분석가",
        "FP&A",
        "재무기획",
    ],
    "Accountant": [
        "회계사",
        "세무사",
        "경리",
        "회계 담당",
    ],
    "Quantitative Analyst": [
        "퀀트 애널리스트",
        "계량분석",
    ],
    "Investment Analyst": [
        "투자 분석가",
        "주식 애널리스트",
        "IB 애널리스트",
    ],
    # ── Operations & Strategy ─────────────────────────────────────────────
    "Business Analyst": [
        "경영 분석가",
        "비즈니스 애널리스트",
        "BA",
    ],
    "Strategy Consultant": [
        "전략 컨설턴트",
        "경영 컨설턴트",
        "전략기획",
    ],
    "Operations Manager": [
        "운영 매니저",
        "사업 운영",
        "커머스 운영",
    ],
    "Project Manager": [
        "프로젝트 매니저",
        "PMP",
        "IT PM",
    ],
    # ── Human Resources ───────────────────────────────────────────────────
    "Recruiter": [
        "채용 담당자",
        "헤드헌터",
        "리크루터",
    ],
    "HR Business Partner": [
        "HR BP",
        "인사 담당자",
        "조직문화",
    ],
    "Compensation & Benefits Specialist": [
        "보상 전문가",
        "급여 담당",
        "복리후생",
    ],
    # ── Sales & Business Development ──────────────────────────────────────
    "Sales Engineer": [
        "영업 엔지니어",
        "세일즈 엔지니어",
        "기술 영업",
    ],
    "Account Executive": [
        "영업 담당자",
        "기업 영업",
        "B2B 영업",
    ],
    "Business Development Manager": [
        "사업개발 매니저",
        "BD 매니저",
        "파트너십",
    ],
    # ── Legal & Compliance ────────────────────────────────────────────────
    "Legal Counsel": [
        "법무 담당자",
        "사내 변호사",
        "기업 법무",
    ],
    "Compliance Officer": [
        "컴플라이언스",
        "준법감시인",
        "내부감사",
    ],
    # ── Research & Science ────────────────────────────────────────────────
    "Research Scientist": [
        "연구원",
        "R&D 연구원",
    ],
    "Research Engineer": [
        "연구 개발 엔지니어",
        "R&D 엔지니어",
    ],
    # ── Customer Success ──────────────────────────────────────────────────
    "Customer Success Manager": [
        "고객 성공 매니저",
        "CS 매니저",
        "고객 지원",
    ],
    "Technical Support Engineer": [
        "기술 지원 엔지니어",
        "IT 지원",
        "헬프데스크",
    ],
    # ── Data Labeling ─────────────────────────────────────────────────────
    "Data Labeling / Annotation Specialist": [
        "데이터 라벨링",
        "데이터 어노테이션",
        "AI 라벨러",
    ],
    # ── Education & Training ──────────────────────────────────────────────
    "Teacher / Instructor": [
        "강사",
        "교사",
        "교육 강사",
    ],
    "Curriculum Developer": [
        "교육과정 개발",
        "커리큘럼 개발",
        "교수설계",
    ],
    # ── Supply Chain & Logistics ──────────────────────────────────────────
    "Supply Chain Manager": [
        "공급망 관리",
        "SCM 매니저",
        "물류 관리자",
    ],
    "Logistics Coordinator": [
        "물류 담당",
        "물류 코디네이터",
        "물류 관리",
    ],
    # ── Healthcare ────────────────────────────────────────────────────────
    "Nurse": [
        "간호사",
        "간호",
    ],
    "Healthcare Specialist": [
        "헬스케어",
        "의료 전문",
        "임상",
    ],
}


def get_all_queries(
    queries: dict[str, list[str]] | None = None,
) -> list[str]:
    """검색어 맵의 모든 값을 중복 없이 평탄화해 반환한다."""
    source = queries if queries is not None else KR_JOB_SEARCH_QUERIES
    seen: set[str] = set()
    result: list[str] = []
    for items in source.values():
        for q in items:
            if q not in seen:
                seen.add(q)
                result.append(q)
    return result


def get_queries_for_function(
    function_name: str,
    queries: dict[str, list[str]] | None = None,
) -> list[str]:
    """taxonomy 직무명에 매핑된 검색어 목록을 반환한다."""
    source = queries if queries is not None else KR_JOB_SEARCH_QUERIES
    return source.get(function_name, [])
