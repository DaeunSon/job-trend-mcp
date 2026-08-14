"""get_posting_count_by_category tool 로직."""
from __future__ import annotations

from typing import Any

from src.mcp_server.data_loader import JobPostingStore, get_store
from src.taxonomy.job_categories import JOB_CATEGORIES


def get_posting_count_by_category(
    active_only: bool = True,
    store: JobPostingStore | None = None,
) -> dict[str, Any]:
    """
    직군(job_category)별 채용공고 수를 집계해 반환한다.

    taxonomy의 15개 직군 전체를 기준으로, 0건인 직군도 포함한다.
    """
    store = store or get_store()

    counts: dict[str, int] = {c: 0 for c in JOB_CATEGORIES}
    uncategorized = 0

    for doc in store.postings:
        if active_only and (doc.get("crawl_status") or "ACTIVE") != "ACTIVE":
            continue
        cat = (doc.get("job_category_name") or "").strip()
        if cat in counts:
            counts[cat] += 1
        else:
            uncategorized += 1

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
