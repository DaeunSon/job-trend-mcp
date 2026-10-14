"""search_job_postings tool 로직."""
from __future__ import annotations

from typing import Any

from src.mcp_server.data_loader import JobPostingStore, get_store


def _location_blob(doc: dict[str, Any]) -> str:
    loc = doc.get("location") or {}
    if not isinstance(loc, dict):
        return ""
    parts = [
        loc.get("city_name") or "",
        loc.get("region_name") or "",
        loc.get("country_name") or "",
        loc.get("raw_text") or "",
    ]
    return " ".join(str(p) for p in parts).lower()


def _norm_enum_token(value: str) -> str:
    """FULL_TIME / Full-time / full time → fulltime (모니터링 employment_type 미스매치 대응)."""
    return (
        value.strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _company_name(doc: dict[str, Any]) -> str | None:
    company = doc.get("company") or {}
    if isinstance(company, dict):
        return company.get("name")
    return None


def _city_name(doc: dict[str, Any]) -> str | None:
    loc = doc.get("location") or {}
    if isinstance(loc, dict):
        return loc.get("city_name")
    return None


def summarize_posting(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": doc.get("title"),
        "company": _company_name(doc),
        "location": _city_name(doc),
        "employment_type": doc.get("employment_type_name"),
        "work_arrangement": doc.get("work_arrangement"),
        "job_function": doc.get("job_function_name"),
        "job_category": doc.get("job_category_name"),
        "posted_at": doc.get("posted_at"),
        "original_url": doc.get("original_url"),
        "source_name": doc.get("source_name"),
    }


def search_job_postings(
    job_function: str | None = None,
    job_category: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    work_arrangement: str | None = None,
    source_name: str | None = None,
    limit: int = 20,
    active_only: bool = True,
    store: JobPostingStore | None = None,
) -> dict[str, Any]:
    """
    조건에 맞는 채용공고를 검색한다.

    Returns
    -------
    dict with keys:
      - results: list[dict] 요약 공고
      - count: int
      - status: "ok" | "unknown_param" | "empty"
      - message: str | None  (unknown_param / empty 안내)
    """
    store = store or get_store()
    limit = max(1, min(int(limit), 100))

    resolved_fn, fn_error = store.resolve_job_function(job_function)
    if fn_error:
        return {
            "status": "unknown_param",
            "message": fn_error,
            "available_job_functions": store.known_functions,
            "count": 0,
            "results": [],
        }

    if job_category and job_category.strip():
        cat = job_category.strip()
        known = {c.lower(): c for c in store.known_categories}
        if cat not in store.known_categories and cat.lower() not in known:
            return {
                "status": "unknown_param",
                "message": (
                    f"Unknown job_category {cat!r}. "
                    f"Available: {', '.join(store.known_categories)}"
                ),
                "available_job_categories": store.known_categories,
                "count": 0,
                "results": [],
            }
        job_category = known.get(cat.lower(), cat)

    resolved_src, src_error = store.resolve_source_name(source_name)
    if src_error:
        return {
            "status": "unknown_param",
            "message": src_error,
            "available_source_names": store.known_sources,
            "count": 0,
            "results": [],
        }

    # 후보 집합
    if resolved_fn:
        candidates = list(store.by_function.get(resolved_fn, []))
    elif job_category:
        candidates = list(store.by_category.get(job_category, []))
    else:
        candidates = list(store.postings)

    loc_q = (location or "").strip().lower() or None
    emp_q = (employment_type or "").strip().lower() or None
    emp_q_norm = _norm_enum_token(emp_q) if emp_q else None
    arr_q = (work_arrangement or "").strip().lower() or None

    matched: list[dict[str, Any]] = []
    for doc in candidates:
        if active_only and (doc.get("crawl_status") or "ACTIVE") != "ACTIVE":
            continue
        if job_category and (doc.get("job_category_name") or "").strip() != job_category:
            continue
        if resolved_src and (doc.get("source_name") or "").strip() != resolved_src:
            continue
        if loc_q and loc_q not in _location_blob(doc):
            continue
        if emp_q_norm:
            emp_doc = _norm_enum_token(doc.get("employment_type_name") or "")
            # 정규화 동등 또는 부분문자열(기존 관대함 유지)
            if emp_q_norm != emp_doc and emp_q not in (doc.get("employment_type_name") or "").lower():
                continue
        if arr_q and arr_q not in (doc.get("work_arrangement") or "").lower():
            continue
        matched.append(doc)

    # 최근 공고 우선 (posted_at / last_seen_at 내림차순)
    def _sort_key(d: dict[str, Any]) -> str:
        return str(d.get("posted_at") or d.get("last_seen_at") or d.get("created_at") or "")

    matched.sort(key=_sort_key, reverse=True)
    results = [summarize_posting(d) for d in matched[:limit]]

    if not results:
        return {
            "status": "empty",
            "message": (
                "No postings matched the filters. "
                "Filters are valid but the collected dataset has 0 hits for this combination."
            ),
            "count": 0,
            # 필터가 유효하면 0건이어도 total_matched 를 준다. unknown_param 에는 두지 않는다
            # (모델이 "0건"으로 답하지 않게).
            "total_matched": 0,
            "results": [],
        }

    return {
        "status": "ok",
        "message": None,
        "count": len(results),
        "total_matched": len(matched),
        "results": results,
    }
