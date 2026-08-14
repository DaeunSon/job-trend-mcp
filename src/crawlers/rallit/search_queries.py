"""
랠릿 전용 검색 쿼리 매핑.

0단계 조사 결과 (2026-07-29 확인)
-----------------------------------
랠릿 내부 API (https://www.rallit.com/client/api/v1/position) 동작:
  - `keyword` 파라미터 : 공고 제목 기반 검색 — 실질적인 필터 역할 (확인됨)
  - `job`     파라미터 : jobs.code 기반 필터를 의도했으나 실제로는 전체를 반환함 (미작동 확인)
  - `jobGroup` 파라미터: 마찬가지로 전체 반환 (미작동 확인)
  따라서 검색/필터는 `keyword`만 사용한다.

매핑 구조
---------
RALLIT_KEYWORD_QUERIES : dict[str, list[str]]
  키 : taxonomy/job_functions.py 표준 job_function_name (영문)
  값 : 랠릿 keyword 파라미터에 순서대로 전달할 한국어/영어 검색어 목록

  이 목록의 각 keyword로 별도 검색 후 합산하므로, 중복 id가 생길 수 있다.
  crawler.py 의 saved_ids 세트로 중복을 제거한다.

JOB_CODE_TO_FUNCTION : dict[str, str]
  랠릿 상세 API의 jobs[].code 값 → taxonomy job_function_name 매핑.
  extractor.py 에서 job_function_raw 값 결정 시 사용한다.

  실측된 랠릿 jobs.code 목록 (2026-07-29):
    ANDROID_DEVELOPER       → 안드로이드 개발자
    BACKEND_DEVELOPER       → 백엔드/서버 개발자
    BUSINESS_SALES          → 기업영업
    CROSS_PLATFORM_DEVELOPER→ 크로스플랫폼 앱 개발자
    DATA_ENGINEER           → 데이터 엔지니어
    DEV_OPS                 → DevOps
    FRONTEND_DEVELOPER      → 프론트엔드/웹퍼블리셔
    INFRA_ENGINEER          → 시스템/네트워크 관리자
    MACHINE_LEARNING        → 머신러닝 엔지니어
    MANAGEMENT_SUPPORT      → 경영지원
    ORGANIZATIONAL_MANAGEMENT → 조직관리
    PO_PM                   → PO/PM
    PRODUCT_DESIGNER        → 프로덕트 디자이너
    QA_ENGINEER             → QA/테스트엔지니어
    RECRUITER               → 채용담당자
    SALES                   → 세일즈
    SALES_MANAGER           → 영업 관리자
    SECURITY_ENGINEER       → 보안 엔지니어
    SERVICE_OPERATION       → 서비스 운영
    SOFTWARE_ENGINEER       → SW 엔지니어
    TECHNICAL_DIRECTOR      → CTO/테크니컬 디렉터
    TECHNICAL_SALES         → 기술영업
    WEB_APP_DESIGNER        → 웹/앱 디자이너
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# taxonomy job_function_name → 랠릿 keyword 목록
# ---------------------------------------------------------------------------

RALLIT_KEYWORD_QUERIES: dict[str, list[str]] = {
    # ── Engineering & Technology ─────────────────────────────────────────────
    "Software Engineer":            ["소프트웨어 엔지니어", "software engineer", "software developer"],
    "Backend Engineer":             ["백엔드", "서버 개발자", "backend", "backend engineer", "backend developer"],
    "Frontend Engineer":            ["프론트엔드", "frontend", "frontend engineer", "frontend developer"],
    "Full Stack Engineer":          ["풀스택", "fullstack", "full stack"],
    "Mobile Engineer":              ["android", "ios", "안드로이드", "모바일"],
    "DevOps / Platform Engineer":   ["devops", "인프라", "클라우드 엔지니어"],
    "Site Reliability Engineer":    ["sre", "시스템 엔지니어", "네트워크"],
    "Security Engineer":            ["보안"],
    "QA / Test Engineer":           ["qa", "테스트 엔지니어"],
    "Embedded / Hardware Engineer": ["임베디드", "하드웨어"],
    # ── Data & Analytics ─────────────────────────────────────────────────────
    "Machine Learning Engineer":    ["머신러닝", "machine learning", "ml 엔지니어"],
    "Data Engineer":                ["데이터 엔지니어"],
    "Data Scientist":               ["데이터 사이언티스트"],
    "Data Analyst":                 ["데이터 분석"],
    "AI Researcher":                ["ai 연구", "ai researcher"],
    "Business Intelligence Analyst":["bi 엔지니어", "bi 개발"],
    # ── Product & Design ─────────────────────────────────────────────────────
    "Product Manager":              ["pm", "po", "프로덕트 매니저", "서비스 기획"],
    "UX Designer":                  ["ux 디자이너"],
    "UI Designer":                  ["ui 디자이너", "웹 디자이너"],
    "Product Designer":             ["프로덕트 디자이너"],
    "UX Researcher":                ["ux 리서처"],
    # ── Marketing & Growth ───────────────────────────────────────────────────
    "Growth Marketer":              ["그로스", "growth"],
    "Performance Marketer":         ["퍼포먼스 마케터"],
    "Content Marketer":             ["콘텐츠 마케터"],
    "Brand Marketer":               ["브랜드 마케터"],
    "SEO / SEM Specialist":         ["seo", "sem", "키워드 광고"],
    # ── Finance & Accounting ─────────────────────────────────────────────────
    "Financial Analyst":            ["재무 분석"],
    "Accountant":                   ["회계"],
    "Quantitative Analyst":         ["퀀트"],
    "Investment Analyst":           ["투자"],
    # ── Operations & Strategy ────────────────────────────────────────────────
    "Business Analyst":             ["비즈니스 애널리스트"],
    "Strategy Consultant":          ["전략 컨설턴트"],
    "Operations Manager":           ["운영 매니저"],
    "Project Manager":              ["프로젝트 매니저"],
    # ── Human Resources ──────────────────────────────────────────────────────
    "Recruiter":                    ["채용", "리크루터"],
    "HR Business Partner":          ["hrbp", "인사"],
    "Compensation & Benefits Specialist": ["보상"],
    # ── Sales & Business Development ─────────────────────────────────────────
    "Sales Engineer":               ["세일즈 엔지니어"],
    "Account Executive":            ["영업"],
    "Business Development Manager": ["사업개발"],
    # ── Legal & Compliance ───────────────────────────────────────────────────
    "Legal Counsel":                ["법무"],
    "Compliance Officer":           ["컴플라이언스"],
    # ── Research & Science ───────────────────────────────────────────────────
    "Research Scientist":           ["연구원"],
    "Research Engineer":            ["연구 엔지니어"],
    # ── Customer Success ─────────────────────────────────────────────────────
    "Customer Success Manager":     ["고객 성공"],
    "Technical Support Engineer":   ["기술 지원"],
    # ── Data Labeling ────────────────────────────────────────────────────────
    "Data Labeling / Annotation Specialist": ["데이터 라벨링", "데이터 어노테이션", "AI 라벨러"],
    # ── Education & Training ─────────────────────────────────────────────────
    "Teacher / Instructor":         ["강사", "교사", "교육"],
    "Curriculum Developer":         ["커리큘럼", "교육과정", "교수설계"],
    # ── Supply Chain & Logistics ─────────────────────────────────────────────
    "Supply Chain Manager":         ["공급망", "SCM", "물류 관리"],
    "Logistics Coordinator":        ["물류", "물류 담당"],
    # ── Healthcare ───────────────────────────────────────────────────────────
    "Nurse":                        ["간호사", "간호"],
    "Healthcare Specialist":        ["헬스케어", "의료", "임상"],
}

# ---------------------------------------------------------------------------
# 랠릿 jobs.code → taxonomy job_function_name 매핑
# ---------------------------------------------------------------------------

JOB_CODE_TO_FUNCTION: dict[str, str] = {
    "BACKEND_DEVELOPER":        "Backend Engineer",
    "FRONTEND_DEVELOPER":       "Frontend Engineer",
    "DEV_OPS":                  "DevOps / Platform Engineer",
    "INFRA_ENGINEER":           "Site Reliability Engineer",
    "MACHINE_LEARNING":         "Machine Learning Engineer",
    "DATA_ENGINEER":            "Data Engineer",
    "ANDROID_DEVELOPER":        "Mobile Engineer",
    "CROSS_PLATFORM_DEVELOPER": "Mobile Engineer",
    "QA_ENGINEER":              "QA / Test Engineer",
    "SECURITY_ENGINEER":        "Security Engineer",
    "SOFTWARE_ENGINEER":        "Software Engineer",
    "PO_PM":                    "Product Manager",
    "PRODUCT_DESIGNER":         "Product Designer",
    "WEB_APP_DESIGNER":         "UI Designer",
    "TECHNICAL_DIRECTOR":       "Software Engineer",
    "RECRUITER":                "Recruiter",
    "MANAGEMENT_SUPPORT":       "Operations Manager",
    "ORGANIZATIONAL_MANAGEMENT":"HR Business Partner",
    "BUSINESS_SALES":           "Account Executive",
    "SALES":                    "Account Executive",
    "SALES_MANAGER":            "Account Executive",
    "TECHNICAL_SALES":          "Sales Engineer",
    "SERVICE_OPERATION":        "Operations Manager",
}

# ---------------------------------------------------------------------------
# 한글 직무명 → taxonomy 직무명 별칭 (CLI 입력용)
# ---------------------------------------------------------------------------

KOREAN_ALIASES: dict[str, str] = {
    "백엔드 개발자":       "Backend Engineer",
    "백엔드 엔지니어":     "Backend Engineer",
    "서버 개발자":         "Backend Engineer",
    "프론트엔드 개발자":   "Frontend Engineer",
    "프론트엔드 엔지니어": "Frontend Engineer",
    "풀스택 개발자":       "Full Stack Engineer",
    "모바일 개발자":       "Mobile Engineer",
    "ios 개발자":          "Mobile Engineer",
    "안드로이드 개발자":   "Mobile Engineer",
    "devops 엔지니어":     "DevOps / Platform Engineer",
    "클라우드 엔지니어":   "DevOps / Platform Engineer",
    "인프라 엔지니어":     "DevOps / Platform Engineer",
    "sre":                 "Site Reliability Engineer",
    "보안 엔지니어":       "Security Engineer",
    "qa 엔지니어":         "QA / Test Engineer",
    "테스트 엔지니어":     "QA / Test Engineer",
    "임베디드 개발자":     "Embedded / Hardware Engineer",
    "머신러닝 엔지니어":   "Machine Learning Engineer",
    "ml 엔지니어":         "Machine Learning Engineer",
    "데이터 엔지니어":     "Data Engineer",
    "데이터 사이언티스트": "Data Scientist",
    "데이터 분석가":       "Data Analyst",
    "ai 연구원":           "AI Researcher",
    "프로덕트 매니저":     "Product Manager",
    "pm":                  "Product Manager",
    "서비스 기획자":       "Product Manager",
    "ux 디자이너":         "UX Designer",
    "ui 디자이너":         "UI Designer",
    "프로덕트 디자이너":   "Product Designer",
    "그로스 마케터":       "Growth Marketer",
    "퍼포먼스 마케터":     "Performance Marketer",
    "콘텐츠 마케터":       "Content Marketer",
    "브랜드 마케터":       "Brand Marketer",
    "재무 분석가":         "Financial Analyst",
    "회계사":              "Accountant",
    "리크루터":            "Recruiter",
    "채용 담당":           "Recruiter",
    "세일즈 엔지니어":     "Sales Engineer",
    "영업 담당":           "Account Executive",
    "법무 담당":           "Legal Counsel",
    "연구원":              "Research Scientist",
    "고객 성공 매니저":    "Customer Success Manager",
    "기술 지원":           "Technical Support Engineer",
}


# ---------------------------------------------------------------------------
# 공개 유틸
# ---------------------------------------------------------------------------

def get_keywords_for_function(function_name: str) -> list[str]:
    """
    taxonomy 직무명(영문) 또는 한글 별칭에 해당하는 랠릿 keyword 목록을 반환한다.
    """
    # 1순위: 영문 taxonomy 직접 매핑
    keywords = RALLIT_KEYWORD_QUERIES.get(function_name)
    if keywords is not None:
        return keywords

    # 2순위: 한글 별칭 → taxonomy 영문명 → keyword 목록
    canonical = KOREAN_ALIASES.get(function_name.lower())
    if canonical:
        return RALLIT_KEYWORD_QUERIES.get(canonical, [])

    return []


def get_function_for_job_code(job_code: str) -> str:
    """
    랠릿 상세 API의 jobs[].code 값에 대응하는 taxonomy job_function_name을 반환한다.
    매핑 없으면 빈 문자열.
    """
    return JOB_CODE_TO_FUNCTION.get(job_code, "")


def get_all_function_names() -> list[str]:
    """매핑 테이블에 등록된 모든 taxonomy 직무명 목록을 반환한다."""
    return list(RALLIT_KEYWORD_QUERIES.keys())
