"""
job_function_name / job_category_name 공통 정규화.

사이트 파서는 raw 힌트만 추출하고, 이 모듈에서 resolve() 로 표준 taxonomy 값을 반환한다.
"""
from __future__ import annotations

from src.normalization.alias_resolver import resolve
from src.taxonomy.job_categories import is_valid_category
from src.taxonomy.job_functions import get_category_for_function, is_valid_function
from src.taxonomy.job_taxonomy_seed import (
    JOBKOREA_FUNCTION_KEYWORD_PRIORITY,
    SARAMIN_FUNCTION_KEYWORD_PRIORITY,
    TITLE_FUNCTION_KEYWORD_PRIORITY,
    USAJOBS_FUNCTION_KEYWORD_PRIORITY,
    USAJOBS_SERIES_FUNCTION_MAP,
)


def normalize_job_function(raw: str, source_name: str | None = None) -> str:
    """원문 직무 힌트 → 표준 job_function_name."""
    text = raw.strip()
    if not text:
        return ""
    canonical = resolve("JOB_FUNCTION", text, source_name)
    return canonical if is_valid_function(canonical) else ""


def normalize_job_category(raw: str, source_name: str | None = None) -> str:
    """원문 직군 힌트 → 표준 job_category_name."""
    text = raw.strip()
    if not text:
        return ""
    canonical = resolve("JOB_CATEGORY", text, source_name)
    if is_valid_category(canonical):
        return canonical
    return "Other"


def normalize_job_taxonomy(
    function_raw: str,
    category_raw: str,
    source_name: str | None = None,
) -> tuple[str, str]:
    """
    function/category raw 힌트를 표준 taxonomy 로 변환한다.

    category 가 없고 function 만 있으면 job_functions.py 에서 category 를 유도한다.
    """
    job_function = normalize_job_function(function_raw, source_name)
    job_category = normalize_job_category(category_raw, source_name)

    if job_category == "Other" and job_function:
        job_category = get_category_for_function(job_function) or job_category

    if not job_category and job_function:
        job_category = get_category_for_function(job_function) or ""

    return job_function, job_category


def match_keyword_priority(text: str, keywords: list[str]) -> str:
    """우선순위 키워드 목록에서 첫 매칭 raw 키워드를 반환한다."""
    for kw in keywords:
        if kw in text:
            return kw
    return ""


def extract_saramin_function_raw(job_categories_str: str) -> str:
    """사람인 jobCategoryNm 에서 첫 매칭 키워드 raw 반환."""
    if not job_categories_str:
        return ""
    return match_keyword_priority(job_categories_str, SARAMIN_FUNCTION_KEYWORD_PRIORITY)


def extract_jobkorea_function_raw(title: str, description: str = "") -> str:
    """잡코리아 title+description 에서 첫 매칭 키워드 raw 반환."""
    text = (title + " " + description[:200]).lower()
    return match_keyword_priority(text, JOBKOREA_FUNCTION_KEYWORD_PRIORITY)


def extract_title_function_raw(title: str, description: str = "", limit: int = 200) -> str:
    """title/description 키워드 스캔 → resolve 용 raw 키 반환."""
    text = (title + " " + description[:limit]).lower()
    for keyword, raw_key in TITLE_FUNCTION_KEYWORD_PRIORITY:
        if keyword in text:
            return raw_key
    return ""


def extract_jumpit_taxonomy_raw(data: dict) -> tuple[str, str]:
    """점핏 jobCategories / title 에서 function·category raw 힌트를 추출한다."""
    categories = data.get("jobCategories") or data.get("categories") or []
    for cat in categories:
        cat_name = (cat.get("name") or "").strip()
        if cat_name:
            return cat_name, cat_name

    desc = " ".join(
        p for p in [
            data.get("responsibility") or data.get("mainTask") or "",
            data.get("qualifications") or data.get("qualification") or "",
            data.get("preferredRequirements") or data.get("preferredPoint") or "",
            data.get("welfares") or data.get("benefit") or "",
        ] if p
    )
    function_raw = extract_title_function_raw(data.get("title") or "", desc)
    return function_raw, ""


def extract_wanted_taxonomy_raw(job: dict) -> tuple[str, str]:
    """원티드 industry / position 에서 function·category raw 힌트를 추출한다."""
    company = job.get("company") or {}
    category_raw = (company.get("industry_name") or "").strip()
    position = (job.get("position") or "").strip()
    function_raw = extract_title_function_raw(position)
    return function_raw, category_raw


def extract_remotive_taxonomy_raw(job: dict, title: str) -> tuple[str, str]:
    """Remotive category / title·tags 에서 function·category raw 힌트를 추출한다."""
    category_raw = (job.get("category") or "").strip()
    tags_text = " ".join(job.get("tags") or [])
    function_raw = extract_title_function_raw(title, tags_text)
    return function_raw, category_raw


def extract_themuse_taxonomy_raw(
    job: dict,
    title: str,
    description: str = "",
) -> tuple[str, str]:
    """The Muse categories / title 에서 function·category raw 힌트를 추출한다.

    categories 필드는 [{"name": "Software Engineering"}, ...] 형태.
    API category가 제목과 불일치할 때(예: Lyft driver → Software Engineering)는 무시한다.
    """
    categories: list[dict] = job.get("categories") or []
    category_raw = categories[0].get("name", "").strip() if categories else ""
    title_lower = title.lower()
    function_raw = extract_title_function_raw(title, description)

    if category_raw and any(kw in title_lower for kw in _MISLEADING_CATEGORY_TITLE_KEYWORDS):
        category_raw = "Other" if not function_raw else ""

    return function_raw, category_raw


_MISLEADING_CATEGORY_TITLE_KEYWORDS: tuple[str, ...] = (
    "drive with",
    "driving with",
    " new drivers",
    "delivery driver",
    "rideshare driver",
    "uber driver",
    "lyft driver",
)


def extract_arbeitnow_taxonomy_raw(
    job: dict,
    title: str,
    description: str = "",
) -> tuple[str, str]:
    """Arbeitnow tags / title 에서 function·category raw 힌트를 추출한다.

    tags 필드는 ["Engineering", "Sales", ...] 형태.
    별도 카테고리 메타데이터 엔드포인트가 없으므로 태그·제목으로 resolve() 힌트를 만든다.
    """
    tags: list[str] = [t.strip() for t in (job.get("tags") or []) if t and str(t).strip()]
    category_raw = ""
    for tag in tags:
        if tag.lower() != "remote":
            category_raw = tag
            break

    tags_text = " ".join(tags)
    function_raw = extract_title_function_raw(title, f"{tags_text} {description[:200]}")
    return function_raw, category_raw


def extract_usajobs_taxonomy_raw(
    job: dict,
    title: str,
    description: str = "",
) -> tuple[str, str]:
    """
    USAJobs title + occupational series 에서 function·category raw 힌트를 추출한다.

    공통 TITLE_FUNCTION_KEYWORD_PRIORITY 의 bare "engineer" → Software Engineer
    규칙을 쓰지 않는다. 연방 Civil/Mechanical/Aerospace 등이 SW로 떨어지는 것을 막기 위함.

    순서:
      1) USAJobs 전용 제목 키워드 (software engineer, civil engineer, …)
      2) JobCategoryCode series → function fallback
      3) category_raw 는 series 명 (JOB_CATEGORY seed 로 정규화)
    """
    series = ""
    categories = job.get("JobCategoryCode") or []
    if isinstance(categories, list) and categories:
        first = categories[0]
        if isinstance(first, dict):
            series = (first.get("Name") or "").strip()

    # 제목만 스캔 — 상세 본문의 engineer/security 등이 직무를 덮어쓰지 않게 함
    title_lower = (title or "").lower()
    function_raw = ""
    for keyword, raw_key in USAJOBS_FUNCTION_KEYWORD_PRIORITY:
        if keyword in title_lower:
            function_raw = raw_key
            break

    if not function_raw and series:
        function_raw = USAJOBS_SERIES_FUNCTION_MAP.get(series, "")

    return function_raw, series


def extract_work24_taxonomy_raw(
    title: str,
    description: str,
    occupation_raw: str,
    search_query: str,
) -> tuple[str, str]:
    """고용24 모집 직종 / title / search_query 에서 function·category raw 힌트를 추출한다."""
    from src.crawlers.work24.search_queries import get_function_for_query

    # occupation(모집 직종)은 function 힌트로만 사용 — category 로 쓰면 Other 로 떨어진다
    category_raw = ""
    occupation = (occupation_raw or "").strip()
    mapped_query = get_function_for_query(search_query) if search_query else ""

    if occupation:
        function_raw = occupation
    elif mapped_query:
        function_raw = mapped_query
    else:
        # 제목 단독 우선 — description 의 '백엔드' 등이 title 키워드를 덮어쓰지 않게
        function_raw = extract_title_function_raw(title, "")
        if not function_raw:
            function_raw = extract_title_function_raw(title, description)

    if not function_raw and search_query:
        function_raw = extract_title_function_raw(search_query, "")

    return function_raw, category_raw
