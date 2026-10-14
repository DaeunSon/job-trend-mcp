"""get_skill_trend tool 로직."""
from __future__ import annotations

from collections import Counter
from typing import Any

from src.mcp_server.data_loader import JobPostingStore, get_store


def get_skill_trend(
    job_function: str,
    top_n: int = 15,
    active_only: bool = True,
    source_name: str | None = None,
    store: JobPostingStore | None = None,
) -> dict[str, Any]:
    """
    특정 직무에서 가장 많이 요구되는 기술스택 상위 N개를 빈도순으로 반환한다.

    skills[].canonical_name 만 집계한다 (raw_text 미사용).
    """
    store = store or get_store()
    top_n = max(1, min(int(top_n), 50))

    resolved_fn, fn_error = store.resolve_job_function(job_function)
    if fn_error or resolved_fn is None:
        return {
            "status": "unknown_param",
            "message": fn_error
            or f"Unknown job_function {job_function!r}.",
            "available_job_functions": store.known_functions,
            "job_function": job_function,
            "skills": [],
        }

    resolved_src, src_error = store.resolve_source_name(source_name)
    if src_error:
        return {
            "status": "unknown_param",
            "message": src_error,
            "available_source_names": store.known_sources,
            "job_function": resolved_fn,
            "skills": [],
        }

    docs = store.by_function.get(resolved_fn, [])
    if active_only:
        docs = [d for d in docs if (d.get("crawl_status") or "ACTIVE") == "ACTIVE"]
    if resolved_src:
        docs = [d for d in docs if (d.get("source_name") or "").strip() == resolved_src]

    if not docs:
        return {
            "status": "empty",
            "message": (
                f"job_function {resolved_fn!r} is valid but no postings are loaded yet."
            ),
            "job_function": resolved_fn,
            "posting_count": 0,
            "skills": [],
        }

    counter: Counter[str] = Counter()
    for doc in docs:
        skills = doc.get("skills") or []
        if not isinstance(skills, list):
            continue
        seen_in_doc: set[str] = set()
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            name = (skill.get("canonical_name") or "").strip()
            if not name or name in seen_in_doc:
                continue
            seen_in_doc.add(name)
            counter[name] += 1

    ranked = [
        {"skill": skill, "count": count}
        for skill, count in counter.most_common(top_n)
    ]

    if not ranked:
        return {
            "status": "empty",
            "message": (
                f"Found {len(docs)} posting(s) for {resolved_fn!r}, "
                "but none have canonical skill tags."
            ),
            "job_function": resolved_fn,
            "posting_count": len(docs),
            "skills": [],
        }

    return {
        "status": "ok",
        "message": None,
        "job_function": resolved_fn,
        "posting_count": len(docs),
        "skills": ranked,
    }
