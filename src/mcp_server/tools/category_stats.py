"""get_posting_count_by_category tool 로직."""
from __future__ import annotations

from collections import Counter
from typing import Any

import psycopg

from src.db import queries
from src.mcp_server.data_loader import JobPostingStore
from src.taxonomy.job_categories import JOB_CATEGORIES


def _memory_category_counts(
    store: JobPostingStore, resolved_src: str | None, *, active_only: bool
) -> dict[str, int]:
    """메모리 경로: job_category_name(빈 문자열 포함) → 공고 수."""
    counts: Counter[str] = Counter()
    for doc in store.postings:
        if active_only and (doc.get("crawl_status") or "ACTIVE") != "ACTIVE":
            continue
        if resolved_src and (doc.get("source_name") or "").strip() != resolved_src:
            continue
        counts[doc.get("job_category_name") or ""] += 1
    return dict(counts)


def get_posting_count_by_category(
    active_only: bool = True,
    source_name: str | None = None,
    store: JobPostingStore | None = None,
    conn: psycopg.Connection | None = None,
) -> dict[str, Any]:
    """
    직군(job_category)별 채용공고 수를 집계해 반환한다.

    taxonomy의 15개 직군 전체를 기준으로, 0건인 직군도 포함한다.
    store 를 주면 메모리 스토어를, 안 주면 PostgreSQL(conn 또는 연결 풀)을 조회한다.
    """
    resolver = store if store is not None else JobPostingStore()

    resolved_src, src_error = resolver.resolve_source_name(source_name)
    if src_error:
        return {
            "status": "unknown_param",
            "message": src_error,
            "available_source_names": resolver.known_sources,
            "total_postings": 0,
            "uncategorized_count": 0,
            "categories": [],
        }

    if store is not None:
        raw_counts = _memory_category_counts(store, resolved_src, active_only=active_only)
    else:
        with queries.use_connection(conn) as c:
            raw_counts = queries.category_counts(
                c, source_name=resolved_src, active_only=active_only
            )

    counts: dict[str, int] = {c: 0 for c in JOB_CATEGORIES}
    uncategorized = 0
    for raw_cat, n in raw_counts.items():
        cat = (raw_cat or "").strip()
        if cat in counts:
            counts[cat] += n
        else:
            uncategorized += n

    categories = [
        {"category": cat, "count": counts[cat]}
        for cat in JOB_CATEGORIES
    ]
    # 건수 내림차순 유지하되 0건도 목록에 남김 — 정렬은 count desc, 이름 asc
    categories.sort(key=lambda x: (-x["count"], x["category"]))

    return {
        "status": "ok",
        "message": None,
        "total_postings": sum(counts.values()) + uncategorized,
        "uncategorized_count": uncategorized,
        "categories": categories,
    }
