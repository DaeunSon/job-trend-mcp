"""get_skill_trend tool 로직."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

import psycopg

from src.db import queries
from src.mcp_server.data_loader import JobPostingStore


def _memory_skill_counts(
    store: JobPostingStore,
    resolved_fn: str,
    resolved_src: str | None,
    *,
    active_only: bool,
    top_n: int,
) -> tuple[int, list[tuple[str, int]]]:
    """메모리 경로: (공고 수, 스킬별 공고 수 상위 N)."""
    docs = store.by_function.get(resolved_fn, [])
    if active_only:
        docs = [d for d in docs if (d.get("crawl_status") or "ACTIVE") == "ACTIVE"]
    if resolved_src:
        docs = [d for d in docs if (d.get("source_name") or "").strip() == resolved_src]

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
    return len(docs), counter.most_common(top_n)


SERIES_NOTE = (
    "Weekly values come from a capped daily collection sample, not a full census. "
    "Compare share, not count. Weeks listed in collection_gaps have no data."
)


def _series_fields(skills: list[str], weekly: list[dict[str, Any]]) -> dict[str, Any]:
    """SQL 경로 전용: series / collection_gaps / series_note."""
    series = [
        {
            "week_start": w["week_start"].isoformat(),
            "posting_count": w["posting_count"],
            "skills": [
                {
                    "skill": name,
                    "count": w["counts"].get(name, 0),
                    "share": round(w["counts"].get(name, 0) / w["posting_count"], 4),
                }
                for name in skills
            ],
        }
        for w in weekly
    ]
    gaps = []
    for prev, nxt in zip(weekly, weekly[1:]):
        if (nxt["week_start"] - prev["week_start"]).days > 7:
            gaps.append({
                "from": (prev["week_start"] + timedelta(days=7)).isoformat(),
                "to": (nxt["week_start"] - timedelta(days=1)).isoformat(),
            })
    return {"series": series, "collection_gaps": gaps, "series_note": SERIES_NOTE}


def get_skill_trend(
    job_function: str,
    top_n: int = 15,
    active_only: bool = True,
    source_name: str | None = None,
    store: JobPostingStore | None = None,
    conn: psycopg.Connection | None = None,
) -> dict[str, Any]:
    """
    특정 직무에서 가장 많이 요구되는 기술스택 상위 N개를 빈도순으로 반환한다.

    skills[].canonical_name 만 집계한다 (raw_text 미사용).
    store 를 주면 메모리 스토어를, 안 주면 PostgreSQL(conn 또는 연결 풀)을 조회한다.
    """
    resolver = store if store is not None else JobPostingStore()
    top_n = max(1, min(int(top_n), 50))

    resolved_fn, fn_error = resolver.resolve_job_function(job_function)
    if fn_error or resolved_fn is None:
        return {
            "status": "unknown_param",
            "message": fn_error
            or f"Unknown job_function {job_function!r}.",
            "available_job_functions": resolver.known_functions,
            "job_function": job_function,
            "skills": [],
        }

    resolved_src, src_error = resolver.resolve_source_name(source_name)
    if src_error:
        return {
            "status": "unknown_param",
            "message": src_error,
            "available_source_names": resolver.known_sources,
            "job_function": resolved_fn,
            "skills": [],
        }

    weekly: list[dict[str, Any]] = []
    if store is not None:
        posting_count, counts = _memory_skill_counts(
            store, resolved_fn, resolved_src, active_only=active_only, top_n=top_n
        )
    else:
        with queries.use_connection(conn) as c:
            posting_count, counts = queries.skill_counts(
                c,
                job_function=resolved_fn,
                source_name=resolved_src,
                active_only=active_only,
                top_n=top_n,
            )
            if posting_count:
                weekly = queries.skill_weekly_series(
                    c,
                    job_function=resolved_fn,
                    skills=[skill for skill, _ in counts],
                    source_name=resolved_src,
                    active_only=active_only,
                )

    extra = _series_fields([skill for skill, _ in counts], weekly) if store is None else {}

    if not posting_count:
        return {
            "status": "empty",
            "message": (
                f"job_function {resolved_fn!r} is valid but no postings are loaded yet."
            ),
            "job_function": resolved_fn,
            "posting_count": 0,
            "skills": [],
            **extra,
        }

    ranked = [{"skill": skill, "count": count} for skill, count in counts]

    if not ranked:
        return {
            "status": "empty",
            "message": (
                f"Found {posting_count} posting(s) for {resolved_fn!r}, "
                "but none have canonical skill tags."
            ),
            "job_function": resolved_fn,
            "posting_count": posting_count,
            "skills": [],
            **extra,
        }

    return {
        "status": "ok",
        "message": None,
        "job_function": resolved_fn,
        "posting_count": posting_count,
        "skills": ranked,
        **extra,
    }
