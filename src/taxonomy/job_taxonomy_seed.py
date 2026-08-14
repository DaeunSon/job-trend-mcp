"""
JOB_FUNCTION / JOB_CATEGORY alias seed 데이터.

모든 사이트별 매핑 테이블을 이 파일 한 곳으로 모은다.
resolve() 가 JSON 파일에 없을 때 이 seed 를 조회한다.
scripts/seed_job_taxonomy_aliases.py 로 normalization_aliases.json 에 반영 가능.
"""
from __future__ import annotations

# ── 사람인 jobCategoryNm 키워드 (우선순위 순) ────────────────────────────────
SARAMIN_FUNCTION_KEYWORD_PRIORITY: list[str] = [
    "백엔드/서버개발", "백엔드", "서버개발", "프론트엔드", "풀스택",
    "iOS", "Android", "앱개발", "모바일", "DevOps", "데브옵스", "클라우드",
    "SRE", "보안관제", "정보보안", "보안컨설팅", "QA", "테스트",
    "임베디드", "펌웨어", "데이터 사이언티스트", "데이터사이언티스트",
    "AI(인공지능)", "머신러닝", "딥러닝", "데이터엔지니어링", "데이터분석",
    "빅데이터", "웹개발", "SI개발", "솔루션", "개발PM", "IT개발·데이터",
    "소프트웨어개발",
]

# ── 잡코리아 title/description 키워드 (우선순위 순, 소문자) ─────────────────
JOBKOREA_FUNCTION_KEYWORD_PRIORITY: list[str] = [
    "임베디드", "embedded", "펌웨어", "firmware", "bsp ", "하드웨어 개발",
    "hardware engineer", "머신러닝", "machine learning", "딥러닝", "deep learning",
    "llm", "generative ai", "ai 엔지니어", "ai engineer",
    "데이터 엔지니어", "data engineer", "데이터 사이언티스트", "data scientist",
    "데이터 분석", "data analyst", "빅데이터", "백엔드", "backend", "서버 개발",
    "프론트엔드", "frontend", "풀스택", "full stack", "fullstack",
    "ios 개발", "android 개발", "모바일 앱", "앱 개발",
    "devops", "데브옵스", "cloud engineer", "클라우드 엔지니어", "인프라 엔지니어",
    "sre", "보안 엔지니어", "security engineer", "정보보안",
    "qa 엔지니어", "qa engineer", "테스트 엔지니어",
    "소프트웨어 엔지니어", "software engineer", "개발자", "developer", "개발",
]

# ── USAJobs 전용 title 키워드 (bare "engineer" 없음 — 연방 토목/기계 오분류 방지) ─
# 우선순위: 구체적 IT/SW → 보안 → 데이터 → HW/전자 → 비SW 공학(Research Engineer)
USAJOBS_FUNCTION_KEYWORD_PRIORITY: list[tuple[str, str]] = [
    ("software engineer", "software engineer"),
    ("software developer", "software developer"),
    ("computer scientist", "computer scientist"),
    ("application developer", "software engineer"),
    ("programmer analyst", "software engineer"),
    ("programmer", "software engineer"),
    ("it specialist", "software engineer"),
    ("information technology specialist", "software engineer"),
    ("cybersecurity", "cybersecurity"),
    ("information security", "security"),
    ("security engineer", "security"),
    ("data scientist", "data scientist"),
    ("data engineer", "data engineer"),
    ("data analyst", "data analyst"),
    ("machine learning", "machine learning"),
    ("devops", "devops"),
    ("site reliability", "site reliability"),
    ("cloud engineer", "cloud"),
    ("platform engineer", "platform engineer"),
    ("electronics engineer", "electronics engineer"),
    ("electrical engineer", "electrical engineer"),
    ("computer engineer", "computer engineer"),
    ("hardware engineer", "hardware"),
    ("embedded", "embedded"),
    ("firmware", "firmware"),
    ("astronautical", "research engineer"),
    ("aerospace engineer", "research engineer"),
    ("mechanical engineer", "research engineer"),
    ("civil engineer", "research engineer"),
    ("structural engineer", "research engineer"),
    ("chemical engineer", "research engineer"),
    ("nuclear engineer", "research engineer"),
    ("industrial engineer", "research engineer"),
    ("general engineer", "research engineer"),
    ("systems engineer", "research engineer"),
    ("reliability engineer", "research engineer"),
    ("test engineer", "test engineer"),
    ("quality assurance", "quality assurance"),
]

# USAJobs JobCategoryCode[].Name (연방 occupational series) → function raw_key
# 제목에 구체 키워드가 없을 때 fallback. 너무 넓은 series 는 빈 문자열.
USAJOBS_SERIES_FUNCTION_MAP: dict[str, str] = {
    "Information Technology Management": "software engineer",
    "Computer Science": "computer scientist",
    "Computer Engineering": "computer engineer",
    "Electronics Engineering": "electronics engineer",
    "Electrical Engineering": "electrical engineer",
    "Aerospace Engineering": "research engineer",
    "Mechanical Engineering": "research engineer",
    "Civil Engineering": "research engineer",
    "Architecture": "",
    "General Engineering": "",
    "Intelligence": "",
    "Railroad Safety": "",
    "Transportation Specialist": "",
}

# ── title/description 키워드 → resolve raw_key (소문자 keyword) ───────────
TITLE_FUNCTION_KEYWORD_PRIORITY: list[tuple[str, str]] = [
    ("머신러닝", "머신러닝"), ("machine learning", "machine learning"),
    ("딥러닝", "딥러닝"), ("deep learning", "deep learning"),
    ("빅데이터", "빅데이터"), ("bigdata", "bigdata"), ("big data", "big data"),
    ("데이터 엔지니어", "데이터 엔지니어"), ("data engineer", "data engineer"),
    ("데이터 사이언티스트", "데이터 사이언티스트"), ("data scientist", "data scientist"),
    ("데이터 분석", "데이터 분석"), ("data analyst", "data analyst"),
    ("data labeling", "data labeling"), ("data annotation", "data annotation"),
    ("annotation specialist", "annotation specialist"), ("labeling specialist", "labeling specialist"),
    ("ai researcher", "ai researcher"), ("ai 연구", "ai researcher"),
    ("research scientist", "research scientist"), ("nlp", "nlp"),
    ("프론트엔드", "프론트엔드"), ("frontend", "frontend"), ("front-end", "front-end"),
    ("백엔드", "백엔드"), ("backend", "backend"), ("back-end", "back-end"),
    ("서버 개발", "서버 개발"), ("server developer", "server developer"),
    ("풀스택", "풀스택"), ("fullstack", "fullstack"), ("full stack", "full stack"),
    ("full-stack", "full-stack"), ("ios", "ios"), ("android", "android"),
    ("안드로이드", "안드로이드"), ("모바일", "모바일"), ("mobile", "mobile"),
    ("devops", "devops"), ("클라우드", "클라우드"), ("cloud", "cloud"),
    ("인프라", "인프라"), ("sre", "sre"), ("시스템 엔지니어", "시스템 엔지니어"),
    ("보안", "보안"), ("security", "security"), ("정보보호", "정보보호"),
    ("qa", "qa"), ("테스트", "테스트"), ("test engineer", "test engineer"),
    ("품질", "품질"), ("임베디드", "임베디드"), ("embedded", "embedded"),
    ("h/w", "h/w"), ("hw ", "hw"),
    ("시스템 소프트웨어", "시스템 소프트웨어"), ("시스템 개발", "시스템 개발"),
    ("하드웨어", "하드웨어"), ("hardware", "hardware"), ("펌웨어", "펌웨어"),
    ("소프트웨어 엔지니어", "소프트웨어 엔지니어"),
    ("software engineer", "software engineer"),
    ("software developer", "software developer"),
    # Sales Engineer 계열은 일반 "engineer" 보다 앞에 둬야 함
    ("sales engineer", "sales engineer"),
    ("세일즈 엔지니어", "sales engineer"),
    ("presales engineer", "sales engineer"),
    ("pre-sales engineer", "sales engineer"),
    ("pre sales engineer", "sales engineer"),
    ("solutions engineer", "sales engineer"),
    ("solution engineer", "sales engineer"),
    ("vertriebsingenieur", "sales engineer"),
    ("technical sales", "sales engineer"),
    ("엔지니어", "엔지니어"), ("engineer", "engineer"),
    ("developer", "developer"), ("개발자", "개발자"),
    ("product manager", "product manager"), ("프로덕트 매니저", "프로덕트 매니저"),
    ("pm ", "pm"), (" pm,", "pm"), ("서비스 기획", "서비스 기획"),
    ("ux designer", "ux designer"), ("ux 디자이너", "ux 디자이너"),
    ("ui designer", "ui designer"), ("ui 디자이너", "ui 디자이너"),
    ("product designer", "product designer"), ("프로덕트 디자이너", "프로덕트 디자이너"),
    ("ux researcher", "ux researcher"), ("ux 리서처", "ux 리서처"),
    ("performance marketer", "performance marketer"),
    ("content marketer", "content marketer"), ("brand marketer", "brand marketer"),
    ("growth marketer", "growth marketer"), ("마케터", "마케터"), ("마케팅", "마케팅"),
    ("marketing", "marketing"),
    ("financial analyst", "financial analyst"), ("재무 분석", "재무 분석"),
    ("machine learning", "machine learning"), ("ml engineer", "ml engineer"),
    ("analytics engineer", "analytics engineer"),
    ("front end", "front end"), ("back end", "back end"), ("server-side", "server-side"),
    ("site reliability", "site reliability"), ("platform engineer", "platform engineer"),
    ("cybersecurity", "cybersecurity"), ("quality assurance", "quality assurance"),
    ("firmware", "firmware"), ("product owner", "product owner"),
    ("user researcher", "user researcher"), ("ux/ui", "ux/ui"), ("ui/ux", "ui/ux"),
    ("graphic designer", "graphic designer"),
    ("paid acquisition", "paid acquisition"), ("paid media", "paid media"),
    ("content writer", "content writer"), ("content strategist", "content strategist"),
    ("brand manager", "brand manager"), ("seo", "seo"), ("sem specialist", "sem specialist"),
    ("growth hacker", "growth hacker"),
    ("business development", "business development"),
    ("customer success", "customer success"),
    ("technical support", "technical support"),
    ("recruiter", "recruiter"), ("talent acquisition", "recruiter"),
    ("legal counsel", "legal counsel"), ("general counsel", "legal counsel"), ("attorney", "legal counsel"),
    ("research scientist", "research scientist"),
    # Finance / Accounting (Arbeitnow 등 독일어 공고 포함)
    ("steuerberater", "steuerberater"), ("tax advisor", "tax advisor"),
    ("tax consultant", "tax consultant"), ("accountant", "accountant"),
    ("buchhalter", "buchhalter"), ("accounting", "accounting"),
    # Sales
    ("account executive", "account executive"),
    ("vertrieb", "vertrieb"), ("field sales", "field sales"),
    ("enterprise sales", "enterprise sales"),
    # Education / Healthcare / Supply Chain
    ("teacher", "teacher"), ("lehrer", "lehrer"), ("instructor", "instructor"),
    ("curriculum", "curriculum"),
    ("nurse", "nurse"), ("pflegekraft", "pflegekraft"), ("registered nurse", "registered nurse"),
    ("healthcare", "healthcare"),
    ("supply chain", "supply chain"), ("logistics", "logistics"),
    ("disposition", "disposition"),
    # DE IT titles that often fall into Other
    ("fachinformatiker", "fachinformatiker"),
]


def _build_function_seeds() -> dict[str, str]:
    """모든 소스 매핑을 JOB_FUNCTION seed dict 로 병합한다."""
    seeds: dict[str, str] = {}

    def add(raw: str, func: str) -> None:
        if raw and func:
            seeds[raw] = func
            seeds.setdefault(raw.lower(), func)

    # 사람인
    _saramin = [
        ("백엔드/서버개발", "Backend Engineer"), ("백엔드", "Backend Engineer"),
        ("서버개발", "Backend Engineer"), ("프론트엔드", "Frontend Engineer"),
        ("풀스택", "Full Stack Engineer"), ("iOS", "Mobile Engineer"),
        ("Android", "Mobile Engineer"), ("앱개발", "Mobile Engineer"),
        ("모바일", "Mobile Engineer"), ("DevOps", "DevOps / Platform Engineer"),
        ("데브옵스", "DevOps / Platform Engineer"), ("클라우드", "DevOps / Platform Engineer"),
        ("SRE", "Site Reliability Engineer"), ("보안관제", "Security Engineer"),
        ("정보보안", "Security Engineer"), ("보안컨설팅", "Security Engineer"),
        ("QA", "QA / Test Engineer"), ("테스트", "QA / Test Engineer"),
        ("임베디드", "Embedded / Hardware Engineer"), ("펌웨어", "Embedded / Hardware Engineer"),
        ("데이터 사이언티스트", "Data Scientist"), ("데이터사이언티스트", "Data Scientist"),
        ("AI(인공지능)", "Machine Learning Engineer"), ("머신러닝", "Machine Learning Engineer"),
        ("딥러닝", "Machine Learning Engineer"), ("데이터엔지니어링", "Data Engineer"),
        ("데이터분석", "Data Analyst"), ("빅데이터", "Data Engineer"),
        ("웹개발", "Software Engineer"), ("SI개발", "Software Engineer"),
        ("솔루션", "Software Engineer"), ("개발PM", "Project Manager"),
        ("IT개발·데이터", "Software Engineer"), ("소프트웨어개발", "Software Engineer"),
    ]
    for raw, func in _saramin:
        add(raw, func)

    # 잡코리아
    _jobkorea = [
        ("임베디드", "Embedded / Hardware Engineer"), ("embedded", "Embedded / Hardware Engineer"),
        ("펌웨어", "Embedded / Hardware Engineer"), ("firmware", "Embedded / Hardware Engineer"),
        ("bsp ", "Embedded / Hardware Engineer"), ("하드웨어 개발", "Embedded / Hardware Engineer"),
        ("hardware engineer", "Embedded / Hardware Engineer"),
        ("머신러닝", "Machine Learning Engineer"), ("machine learning", "Machine Learning Engineer"),
        ("딥러닝", "Machine Learning Engineer"), ("deep learning", "Machine Learning Engineer"),
        ("llm", "Machine Learning Engineer"), ("generative ai", "Machine Learning Engineer"),
        ("ai 엔지니어", "Machine Learning Engineer"), ("ai engineer", "Machine Learning Engineer"),
        ("데이터 엔지니어", "Data Engineer"), ("data engineer", "Data Engineer"),
        ("데이터 사이언티스트", "Data Scientist"), ("data scientist", "Data Scientist"),
        ("데이터 분석", "Data Analyst"), ("data analyst", "Data Analyst"),
        ("빅데이터", "Data Engineer"), ("백엔드", "Backend Engineer"), ("backend", "Backend Engineer"),
        ("서버 개발", "Backend Engineer"), ("프론트엔드", "Frontend Engineer"),
        ("frontend", "Frontend Engineer"), ("풀스택", "Full Stack Engineer"),
        ("full stack", "Full Stack Engineer"), ("fullstack", "Full Stack Engineer"),
        ("ios 개발", "Mobile Engineer"), ("android 개발", "Mobile Engineer"),
        ("모바일 앱", "Mobile Engineer"), ("앱 개발", "Mobile Engineer"),
        ("devops", "DevOps / Platform Engineer"), ("데브옵스", "DevOps / Platform Engineer"),
        ("cloud engineer", "DevOps / Platform Engineer"),
        ("클라우드 엔지니어", "DevOps / Platform Engineer"),
        ("인프라 엔지니어", "DevOps / Platform Engineer"), ("sre", "Site Reliability Engineer"),
        ("보안 엔지니어", "Security Engineer"), ("security engineer", "Security Engineer"),
        ("정보보안", "Security Engineer"), ("qa 엔지니어", "QA / Test Engineer"),
        ("qa engineer", "QA / Test Engineer"), ("테스트 엔지니어", "QA / Test Engineer"),
        ("소프트웨어 엔지니어", "Software Engineer"), ("software engineer", "Software Engineer"),
        ("개발자", "Software Engineer"), ("developer", "Software Engineer"), ("개발", "Software Engineer"),
    ]
    for raw, func in _jobkorea:
        add(raw, func)

    # 점핏 카테고리명 + 한글 별칭
    _jumpit = {
        "서버/백엔드 개발자": "Backend Engineer", "프론트엔드 개발자": "Frontend Engineer",
        "웹 풀스택 개발자": "Full Stack Engineer", "안드로이드 개발자": "Mobile Engineer",
        "iOS 개발자": "Mobile Engineer", "크로스플랫폼 앱개발자": "Mobile Engineer",
        "게임 클라이언트 개발자": "Software Engineer", "게임 서버 개발자": "Backend Engineer",
        "DBA": "Business Intelligence Analyst", "인공지능/머신러닝": "Machine Learning Engineer",
        "devops/시스템 엔지니어": "DevOps / Platform Engineer",
        "정보보안 담당자": "Security Engineer", "QA 엔지니어": "QA / Test Engineer",
        "개발 PM": "Product Manager", "HW/임베디드": "Embedded / Hardware Engineer",
        "SW/솔루션": "Software Engineer", "웹퍼블리셔": "Frontend Engineer",
        "빅데이터 엔지니어": "Data Engineer", "VR/AR/3D": "Software Engineer",
        "기술지원": "Technical Support Engineer", "블록체인": "Software Engineer",
        "소프트웨어 엔지니어": "Software Engineer", "소프트웨어 개발자": "Software Engineer",
        "백엔드 개발자": "Backend Engineer", "백엔드 엔지니어": "Backend Engineer",
        "서버 개발자": "Backend Engineer", "프론트엔드 개발자": "Frontend Engineer",
        "풀스택 개발자": "Full Stack Engineer", "모바일 개발자": "Mobile Engineer",
        "devops 엔지니어": "DevOps / Platform Engineer", "클라우드 엔지니어": "DevOps / Platform Engineer",
        "인프라 엔지니어": "DevOps / Platform Engineer", "보안 엔지니어": "Security Engineer",
        "테스트 엔지니어": "QA / Test Engineer", "임베디드 개발자": "Embedded / Hardware Engineer",
        "하드웨어 엔지니어": "Embedded / Hardware Engineer",
        "머신러닝 엔지니어": "Machine Learning Engineer", "ml 엔지니어": "Machine Learning Engineer",
        "데이터 엔지니어": "Data Engineer", "데이터 사이언티스트": "Data Scientist",
        "데이터 분석가": "Data Analyst", "ai 연구원": "AI Researcher",
        "프로덕트 매니저": "Product Manager", "개발 pm": "Product Manager",
        "pm": "Product Manager", "서비스 기획자": "Product Manager",
        "ux 디자이너": "UX Designer", "ui 디자이너": "UI Designer",
        "게임 개발자": "Software Engineer", "블록체인": "Software Engineer",
    }
    for raw, func in _jumpit.items():
        add(raw, func)

    # title 키워드 raw_key → function (wanted/remotive/jumpit 공통)
    _title_map = {
        "머신러닝": "Machine Learning Engineer", "machine learning": "Machine Learning Engineer",
        "딥러닝": "Machine Learning Engineer", "deep learning": "Machine Learning Engineer",
        "빅데이터": "Data Engineer", "bigdata": "Data Engineer", "big data": "Data Engineer",
        "데이터 엔지니어": "Data Engineer", "data engineer": "Data Engineer",
        "데이터 사이언티스트": "Data Scientist", "data scientist": "Data Scientist",
        "데이터 분석": "Data Analyst", "data analyst": "Data Analyst",
        "data labeling": "Data Labeling / Annotation Specialist",
        "data labeling specialists": "Data Labeling / Annotation Specialist",
        "data annotation": "Data Labeling / Annotation Specialist",
        "annotation specialist": "Data Labeling / Annotation Specialist",
        "labeling specialist": "Data Labeling / Annotation Specialist",
        "ai researcher": "AI Researcher", "ai 연구": "AI Researcher", "nlp": "AI Researcher",
        "프론트엔드": "Frontend Engineer", "frontend": "Frontend Engineer",
        "front-end": "Frontend Engineer", "front end": "Frontend Engineer",
        "백엔드": "Backend Engineer", "backend": "Backend Engineer",
        "back-end": "Backend Engineer", "back end": "Backend Engineer",
        "서버 개발": "Backend Engineer", "server developer": "Backend Engineer",
        "server-side": "Backend Engineer", "server engineer": "Backend Engineer",
        "풀스택": "Full Stack Engineer", "fullstack": "Full Stack Engineer",
        "full stack": "Full Stack Engineer", "full-stack": "Full Stack Engineer",
        "ios": "Mobile Engineer", "android": "Mobile Engineer", "안드로이드": "Mobile Engineer",
        "모바일": "Mobile Engineer", "mobile": "Mobile Engineer",
        "devops": "DevOps / Platform Engineer", "클라우드": "DevOps / Platform Engineer",
        "cloud": "DevOps / Platform Engineer", "인프라": "DevOps / Platform Engineer",
        "sre": "Site Reliability Engineer", "site reliability": "Site Reliability Engineer",
        "platform engineer": "DevOps / Platform Engineer", "시스템 엔지니어": "DevOps / Platform Engineer",
        "보안": "Security Engineer", "security": "Security Engineer",
        "정보보호": "Security Engineer", "cybersecurity": "Security Engineer",
        "qa": "QA / Test Engineer", "테스트": "QA / Test Engineer",
        "test engineer": "QA / Test Engineer", "quality assurance": "QA / Test Engineer",
        "품질": "QA / Test Engineer",
        "임베디드": "Embedded / Hardware Engineer", "embedded": "Embedded / Hardware Engineer",
        "하드웨어": "Embedded / Hardware Engineer", "hardware": "Embedded / Hardware Engineer",
        "펌웨어": "Embedded / Hardware Engineer", "firmware": "Embedded / Hardware Engineer",
        "h/w": "Embedded / Hardware Engineer", "hw": "Embedded / Hardware Engineer",
        "h/w 엔지니어": "Embedded / Hardware Engineer", "hw 엔지니어": "Embedded / Hardware Engineer",
        "네트워크구축·운영·관리": "DevOps / Platform Engineer",
        "시스템 소프트웨어": "Software Engineer",
        "시스템 소프트웨어 개발자": "Software Engineer",
        "시스템 소프트웨어 개발자(프로그래머)": "Software Engineer",
        "시스템 개발": "Software Engineer",
        "소프트웨어 엔지니어": "Software Engineer", "software engineer": "Software Engineer",
        "software developer": "Software Engineer", "product engineer": "Software Engineer",
        "computer scientist": "Software Engineer",
        "electronics engineer": "Embedded / Hardware Engineer",
        "electrical engineer": "Embedded / Hardware Engineer",
        "computer engineer": "Embedded / Hardware Engineer",
        "research engineer": "Research Engineer",
        "sales engineer": "Sales Engineer", "세일즈 엔지니어": "Sales Engineer",
        "presales engineer": "Sales Engineer", "pre-sales engineer": "Sales Engineer",
        "pre sales engineer": "Sales Engineer",
        "solutions engineer": "Sales Engineer", "solution engineer": "Sales Engineer",
        "vertriebsingenieur": "Sales Engineer", "technical sales": "Sales Engineer",
        "엔지니어": "Software Engineer", "engineer": "Software Engineer",
        "developer": "Software Engineer", "개발자": "Software Engineer",
        "product manager": "Product Manager", "product owner": "Product Manager",
        "프로덕트 매니저": "Product Manager", "pm": "Product Manager", "서비스 기획": "Product Manager",
        "ux designer": "UX Designer", "ux 디자이너": "UX Designer", "ux/ui": "UX Designer",
        "ui/ux": "UX Designer", "ui designer": "UI Designer", "ui 디자이너": "UI Designer",
        "graphic designer": "UI Designer", "product designer": "Product Designer",
        "프로덕트 디자이너": "Product Designer",
        "ux researcher": "UX Researcher", "ux 리서처": "UX Researcher",
        "user researcher": "UX Researcher",
        "performance marketer": "Performance Marketer", "paid acquisition": "Performance Marketer",
        "paid media": "Performance Marketer",
        "content marketer": "Content Marketer", "content writer": "Content Marketer",
        "content strategist": "Content Marketer",
        "brand marketer": "Brand Marketer", "brand manager": "Brand Marketer",
        "growth marketer": "Growth Marketer", "growth hacker": "Growth Marketer",
        "마케터": "Growth Marketer", "마케팅": "Growth Marketer",
        "marketer": "Growth Marketer", "marketing": "Growth Marketer",
        "financial analyst": "Financial Analyst", "재무 분석": "Financial Analyst", "fp&a": "Financial Analyst",
        "ml engineer": "Machine Learning Engineer", "analytics engineer": "Data Analyst",
        "bi ": "Business Intelligence Analyst", "business intelligence": "Business Intelligence Analyst",
        "research scientist": "Research Scientist",
        "business development": "Business Development Manager",
        "customer success": "Customer Success Manager",
        "technical support": "Technical Support Engineer",
        "seo": "SEO / SEM Specialist", "sem specialist": "SEO / SEM Specialist",
        "accountant": "Accountant", "회계": "Accountant", "세무": "Accountant",
        "steuerberater": "Accountant", "tax advisor": "Accountant",
        "tax consultant": "Accountant", "buchhalter": "Accountant",
        "accounting": "Accountant",
        "account executive": "Account Executive",
        "vertrieb": "Business Development Manager",
        "field sales": "Account Executive", "enterprise sales": "Account Executive",
        "recruiter": "Recruiter", "채용": "Recruiter", "talent acquisition": "Recruiter",
        "legal counsel": "Legal Counsel", "general counsel": "Legal Counsel", "attorney": "Legal Counsel",
        "nlp": "AI Researcher",
        "teacher": "Teacher / Instructor", "lehrer": "Teacher / Instructor",
        "instructor": "Teacher / Instructor", "curriculum": "Curriculum Developer",
        "nurse": "Nurse", "pflegekraft": "Nurse", "registered nurse": "Nurse",
        "healthcare": "Healthcare Specialist",
        "supply chain": "Supply Chain Manager", "logistics": "Logistics Coordinator",
        "disposition": "Logistics Coordinator",
        "fachinformatiker": "Software Engineer",
    }
    for raw, func in _title_map.items():
        add(raw, func)

    # taxonomy 표준값 identity (이미 canonical 인 경우)
    from src.taxonomy.job_functions import get_function_names
    for fn in get_function_names():
        add(fn, fn)

    return seeds


def _build_category_seeds() -> dict[str, str]:
    seeds: dict[str, str] = {}

    def add(raw: str, cat: str) -> None:
        if raw and cat:
            seeds[raw] = cat

    # 원티드 industry
    _wanted = {
        "IT, 컨텐츠": "Engineering & Technology",
        "인터넷, 이커머스": "Engineering & Technology",
        "광고, 미디어, 엔터테인먼트": "Marketing & Growth",
        "게임": "Engineering & Technology",
        "금융, 보험, 투자": "Finance & Accounting",
        "컨설팅": "Operations & Strategy",
        "제조, 화학, 바이오, 헬스케어": "Research & Science",
        "유통, 물류, 무역": "Operations & Strategy",
        "교육": "Human Resources",
        "부동산, 건설": "Operations & Strategy",
        "서비스": "Operations & Strategy",
    }
    for raw, cat in _wanted.items():
        add(raw, cat)

    # Remotive category
    _remotive = {
        "Software Development": "Engineering & Technology",
        "Devops": "Engineering & Technology",
        "Quality Assurance": "Engineering & Technology",
        "Engineering": "Engineering & Technology",
        "Information Technology": "Engineering & Technology",
        "Artificial Intelligence": "Data & Analytics",
        "Data and Analytics": "Data & Analytics",
        "Design": "Product & Design",
        "Product Management": "Product & Design",
        "Marketing": "Marketing & Growth",
        "Writing": "Marketing & Growth",
        "Communications": "Marketing & Growth",
        "Finance": "Finance & Accounting",
        "Human Resources": "Human Resources",
        "Sales": "Sales & Business Development",
        "Account Management": "Sales & Business Development",
        "Business Development": "Sales & Business Development",
        "Operations": "Operations & Strategy",
        "Project Management": "Operations & Strategy",
        "Strategy": "Operations & Strategy",
        "Legal": "Legal & Compliance",
        "Compliance": "Legal & Compliance",
        "Research": "Research & Science",
        "Customer Service": "Customer Success",
        "Teaching": "Education & Training",
        "Education": "Education & Training",
        "Knowledge Management": "Other",
        "Supply Chain": "Supply Chain & Logistics",
        "Logistics": "Supply Chain & Logistics",
        "Travel and Hospitality": "Other",
        "Medical": "Healthcare",
        "Healthcare": "Healthcare",
        "All others": "Other",
    }
    for raw, cat in _remotive.items():
        add(raw, cat)

    # The Muse API category (2026-07-29 실제 호출 확인)
    _themuse = {
        "Software Engineering": "Engineering & Technology",
        "Data and Analytics": "Data & Analytics",
        "Science and Engineering": "Research & Science",
        "Product Management": "Product & Design",
        "Project Management": "Operations & Strategy",
        "Advertising and Marketing": "Marketing & Growth",
        "Account Management": "Sales & Business Development",
        "Accounting and Finance": "Finance & Accounting",
        "Human Resources and Recruitment": "Human Resources",
        "Sales": "Sales & Business Development",
        "Legal Services": "Legal & Compliance",
        "Management": "Operations & Strategy",
        "Business Operations": "Operations & Strategy",
    }
    for raw, cat in _themuse.items():
        add(raw, cat)

    # USAJobs occupational series (JobCategoryCode[].Name, 2026-07-31 실측)
    _usajobs = {
        "Information Technology Management": "Engineering & Technology",
        "Computer Science": "Engineering & Technology",
        "Computer Engineering": "Engineering & Technology",
        "Electronics Engineering": "Engineering & Technology",
        "Electrical Engineering": "Engineering & Technology",
        "Aerospace Engineering": "Research & Science",
        "Mechanical Engineering": "Research & Science",
        "Civil Engineering": "Research & Science",
        "General Engineering": "Research & Science",
        "Architecture": "Other",
        "Intelligence": "Other",
        "Railroad Safety": "Other",
        "Transportation Specialist": "Supply Chain & Logistics",
        "Nursing": "Healthcare",
        "Medical Officer": "Healthcare",
        "Education And Training": "Education & Training",
    }
    for raw, cat in _usajobs.items():
        add(raw, cat)

    # Arbeitnow tags (2026-07-30 실제 API 호출 확인)
    _arbeitnow = {
        "Engineering": "Engineering & Technology",
        "IT": "Engineering & Technology",
        "Technik": "Engineering & Technology",
        "R&D Engineering": "Engineering & Technology",
        "Value Engineering": "Engineering & Technology",
        "Sales": "Sales & Business Development",
        "Technical Sales": "Sales & Business Development",
        "Business Development": "Sales & Business Development",
        "Account Executives": "Sales & Business Development",
        "Enterprise Sales": "Sales & Business Development",
        "Field Sales": "Sales & Business Development",
        "Vertrieb": "Sales & Business Development",
        "Marketing": "Marketing & Growth",
        "Marketing Manager": "Marketing & Growth",
        "Social Media": "Marketing & Growth",
        "PR & Communications": "Marketing & Growth",
        "Consulting": "Operations & Strategy",
        "Beratung": "Operations & Strategy",
        "Supply Chain": "Supply Chain & Logistics",
        "People": "Human Resources",
        "People and Culture": "Human Resources",
        "CUR - Accounting": "Finance & Accounting",
    }
    for raw, cat in _arbeitnow.items():
        add(raw, cat)

    # Adzuna category.label
    _adzuna = {
        "IT Jobs": "Engineering & Technology",
        "Engineering Jobs": "Engineering & Technology",
        "Accounting & Finance Jobs": "Finance & Accounting",
        "Sales Jobs": "Sales & Business Development",
        "HR & Recruitment Jobs": "Human Resources",
        "Healthcare & Nursing Jobs": "Healthcare",
        "Teaching Jobs": "Education & Training",
        "Logistics & Warehouse Jobs": "Supply Chain & Logistics",
        "Customer Services Jobs": "Customer Success",
        "Legal Jobs": "Legal & Compliance",
        "Marketing & PR Jobs": "Marketing & Growth",
        "Scientific & QA Jobs": "Research & Science",
        "Other/General Jobs": "Other",
    }
    for raw, cat in _adzuna.items():
        add(raw, cat)

    # 점핏 카테고리명 → job_category
    _jumpit = {
        "서버/백엔드 개발자": "Engineering & Technology",
        "프론트엔드 개발자": "Engineering & Technology",
        "웹 풀스택 개발자": "Engineering & Technology",
        "안드로이드 개발자": "Engineering & Technology",
        "iOS 개발자": "Engineering & Technology",
        "크로스플랫폼 앱개발자": "Engineering & Technology",
        "게임 클라이언트 개발자": "Engineering & Technology",
        "게임 서버 개발자": "Engineering & Technology",
        "DBA": "Data & Analytics",
        "인공지능/머신러닝": "Data & Analytics",
        "devops/시스템 엔지니어": "Engineering & Technology",
        "정보보안 담당자": "Engineering & Technology",
        "QA 엔지니어": "Engineering & Technology",
        "개발 PM": "Product & Design",
        "HW/임베디드": "Engineering & Technology",
        "SW/솔루션": "Engineering & Technology",
        "웹퍼블리셔": "Engineering & Technology",
        "빅데이터 엔지니어": "Data & Analytics",
        "VR/AR/3D": "Engineering & Technology",
        "기술지원": "Engineering & Technology",
        "블록체인": "Engineering & Technology",
    }
    for raw, cat in _jumpit.items():
        add(raw, cat)

    from src.taxonomy.job_categories import JOB_CATEGORIES
    for cat in JOB_CATEGORIES:
        add(cat, cat)

    return seeds


JOB_FUNCTION_SEEDS: dict[str, str] = _build_function_seeds()
JOB_CATEGORY_SEEDS: dict[str, str] = _build_category_seeds()
