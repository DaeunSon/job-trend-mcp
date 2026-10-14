"""get_company_hiring_activity tool 로직."""
from __future__ import annotations

import difflib
from collections import Counter
from typing import Any

from src.mcp_server.data_loader import JobPostingStore, get_store
from src.mcp_server.tools.search import _city_name, _company_name


def _norm_company_key(name: str) -> str:
    return " ".join(name.lower().split())


def _company_index(
    docs: list[dict[str, Any]],
) -> dict[str, str]:
    """normalized key → 가장 많이 쓰인 표기(canonical name)."""
    counts: dict[str, Counter[str]] = {}
    for doc in docs:
        name = _company_name(doc)
        if not name or not str(name).strip():
            continue
        key = _norm_company_key(str(name))
        counts.setdefault(key, Counter())[str(name)] += 1
    return {key: counter.most_common(1)[0][0] for key, counter in counts.items()}


# difflib.SequenceMatcher.ratio 하한.
# 0.55는 spacexx→Paychex(≈0.71) 같은 오탐을 허용한다. 0.75면 SpaceX(≈0.92)만 남는다.
_CLOSE_MATCH_CUTOFF = 0.75


def _suggest_companies(
    query: str,
    index: dict[str, str],
    *,
    limit: int = 8,
) -> list[str]:
    q = _norm_company_key(query)
    if not q:
        return []

    # 부분 일치 우선 (한쪽이 다른 쪽의 부분문자열)
    partial = [
        canonical
        for key, canonical in index.items()
        if q in key or key in q
    ]
    partial.sort(key=lambda n: (len(_norm_company_key(n)), n.lower()))

    close = difflib.get_close_matches(
        q, list(index.keys()), n=limit, cutoff=_CLOSE_MATCH_CUTOFF
    )
    close_names = [index[k] for k in close]

    seen: set[str] = set()
    out: list[str] = []
    for name in partial + close_names:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= limit:
            break
    return out


def get_company_hiring_activity(
    company_name: str,
    limit: int = 20,
    active_only: bool = True,
    source_name: str | None = None,
    store: JobPostingStore | None = None,
) -> dict[str, Any]:
    """
    특정 회사의 채용 현황(진행 중 공고·직무/지역 분포)을 반환한다.

    company.name(정규화 값) 기준. 대소문자·공백 차이는 관대하게 처리.
    정확히 일치하는 회사가 없으면 후보를 제안하고 빈 결과를 반환한다.
    """
    store = store or get_store()
    limit = max(1, min(int(limit), 100))
    query = (company_name or "").strip()

    resolved_src, src_error = store.resolve_source_name(source_name)
    if src_error:
        return {
            "status": "unknown_param",
            "message": src_error,
            "available_source_names": store.known_sources,
            "company_name": company_name,
            "suggestions": [],
            "matched_postings": 0,
            "job_function_counts": [],
            "location_counts": [],
            "postings": [],
        }

    pool = [
        d
        for d in store.postings
        if (not active_only or (d.get("crawl_status") or "ACTIVE") == "ACTIVE")
        and (
            not resolved_src
            or (d.get("source_name") or "").strip() == resolved_src
        )
    ]
    index = _company_index(pool)

    if not query:
        return {
            "status": "unknown_param",
            "message": "company_name is required.",
            "company_name": company_name,
            "suggestions": [],
            "matched_postings": 0,
            "job_function_counts": [],
            "location_counts": [],
            "postings": [],
        }

    key = _norm_company_key(query)
    canonical = index.get(key)
    if canonical is None:
        suggestions = _suggest_companies(query, index)
        return {
            "status": "unknown_company",
            "message": (
                f"No company matched {query!r} exactly "
                f"(case/whitespace-insensitive on company.name). "
                + (
                    f"Did you mean one of: {', '.join(suggestions)}?"
                    if suggestions
                    else "No similar company names found in the dataset."
                )
            ),
            "company_name": query,
            "suggestions": suggestions,
            "matched_postings": 0,
            "job_function_counts": [],
            "location_counts": [],
            "postings": [],
        }

    matched = [
        d
        for d in pool
        if _norm_company_key(str(_company_name(d) or "")) == key
    ]

    fn_counter: Counter[str] = Counter()
    loc_counter: Counter[str] = Counter()
    for doc in matched:
        fn = (doc.get("job_function_name") or "").strip() or "(uncategorized)"
        fn_counter[fn] += 1
        loc = (_city_name(doc) or "").strip() or (
            ((doc.get("location") or {}) if isinstance(doc.get("location"), dict) else {}).get(
                "raw_text"
            )
            or "(unknown)"
        )
        loc_counter[str(loc)] += 1

    def _sort_key(d: dict[str, Any]) -> str:
        return str(
            d.get("posted_at") or d.get("last_seen_at") or d.get("created_at") or ""
        )

    matched_sorted = sorted(matched, key=_sort_key, reverse=True)
    postings = [
        {
            "title": d.get("title"),
            "job_function": d.get("job_function_name"),
            "location": _city_name(d),
            "posted_at": d.get("posted_at"),
        }
        for d in matched_sorted[:limit]
    ]

    return {
        "status": "ok",
        "message": None,
        "company_name": canonical,
        "matched_postings": len(matched),
        "job_function_counts": [
            {"job_function": name, "count": count}
            for name, count in fn_counter.most_common()
        ],
        "location_counts": [
            {"location": name, "count": count}
            for name, count in loc_counter.most_common()
        ],
        "postings": postings,
    }
