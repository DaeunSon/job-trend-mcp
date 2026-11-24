"""get_salary_summary tool 로직."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg

from src.db import queries
from src.mcp_server.data_loader import JobPostingStore
from src.mcp_server.tools.search import _location_blob


def _parse_amount(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _salary_amounts(doc: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    sal = doc.get("salary") or {}
    if not isinstance(sal, dict):
        return None, None
    return _parse_amount(sal.get("min_amount")), _parse_amount(sal.get("max_amount"))


def _has_salary_amount(doc: dict[str, Any]) -> bool:
    mn, mx = _salary_amounts(doc)
    return mn is not None or mx is not None


def _midpoint(mn: Decimal | None, mx: Decimal | None) -> Decimal | None:
    if mn is not None and mx is not None:
        return (mn + mx) / 2
    return mn if mn is not None else mx


def _dec_to_json(value: Decimal) -> float | int:
    """JSON-friendly number (정수면 int)."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _memory_salary_rows(
    store: JobPostingStore,
    resolved_fn: str | None,
    resolved_src: str | None,
    location: str | None,
    *,
    active_only: bool,
) -> tuple[int, list[dict[str, Any]]]:
    """메모리 경로: (조건에 맞는 공고 수, 숫자 급여가 있는 공고의 급여 행).

    행 모양은 src.db.queries.salary_rows 와 같다.
    """
    if resolved_fn:
        candidates = list(store.by_function.get(resolved_fn, []))
    else:
        candidates = list(store.postings)

    loc_q = (location or "").strip().lower() or None
    matched: list[dict[str, Any]] = []
    for doc in candidates:
        if active_only and (doc.get("crawl_status") or "ACTIVE") != "ACTIVE":
            continue
        if resolved_src and (doc.get("source_name") or "").strip() != resolved_src:
            continue
        if loc_q and loc_q not in _location_blob(doc):
            continue
        matched.append(doc)

    rows: list[dict[str, Any]] = []
    for doc in matched:
        if not _has_salary_amount(doc):
            continue
        mn, mx = _salary_amounts(doc)
        sal = doc.get("salary") or {}
        rows.append(
            {
                "salary_min": mn,
                "salary_max": mx,
                "currency_code": sal.get("currency_code"),
                "pay_period": sal.get("pay_period"),
            }
        )
    return len(matched), rows


def get_salary_summary(
    job_function: str | None = None,
    location: str | None = None,
    source_name: str | None = None,
    active_only: bool = True,
    store: JobPostingStore | None = None,
    conn: psycopg.Connection | None = None,
) -> dict[str, Any]:
    """
    직무·지역 조건에 맞는 채용공고의 급여 통계를 반환한다.

    min_amount/max_amount가 있는 공고만 집계한다.
    통화·pay_period가 섞이면 그룹별로 분리한다 (환율 변환·기간 혼합 평균 금지).
    store 를 주면 메모리 스토어를, 안 주면 PostgreSQL(conn 또는 연결 풀)을 조회한다.
    """
    resolver = store if store is not None else JobPostingStore()

    resolved_fn, fn_error = resolver.resolve_job_function(job_function)
    if fn_error:
        return {
            "status": "unknown_param",
            "message": fn_error,
            "available_job_functions": resolver.known_functions,
            "matched_postings": 0,
            "salary_data_count": 0,
            "summaries": [],
        }

    resolved_src, src_error = resolver.resolve_source_name(source_name)
    if src_error:
        return {
            "status": "unknown_param",
            "message": src_error,
            "available_source_names": resolver.known_sources,
            "matched_postings": 0,
            "salary_data_count": 0,
            "summaries": [],
        }

    if store is not None:
        matched_count, with_salary = _memory_salary_rows(
            store, resolved_fn, resolved_src, location, active_only=active_only
        )
    else:
        with queries.use_connection(conn) as c:
            matched_count, with_salary = queries.salary_rows(
                c,
                job_function=resolved_fn,
                location=location,
                source_name=resolved_src,
                active_only=active_only,
            )

    # salary_data_count = 필터에 걸린 공고 중 숫자 급여가 있는 총건수 (권위 있는 집계).
    # summaries[*].group_sample_count 는 통화·pay_period 그룹별 표본 수이며
    # 합치면 salary_data_count 와 같다. LLM이 그룹 수치만 보고 전체로 오인하지 않도록 이름을 분리한다.
    base = {
        "matched_postings": matched_count,
        "salary_data_count": len(with_salary),
        "job_function": resolved_fn,
        "location": location.strip() if location and location.strip() else None,
    }

    if not matched_count:
        return {
            "status": "empty",
            "message": (
                "No postings matched the filters. "
                "Filters are valid but the collected dataset has 0 hits."
            ),
            **base,
            "summaries": [],
        }

    if not with_salary:
        return {
            "status": "no_salary_data",
            "message": (
                f"Matched {matched_count} posting(s), but none have "
                "salary.min_amount / max_amount numeric values. "
                "salary_data_count is 0."
            ),
            **base,
            "summaries": [],
        }

    # (currency_code, pay_period) 별 집계 — 서로 다른 단위를 섞어 평균내지 않음
    groups: dict[tuple[str, str], list[tuple[Decimal | None, Decimal | None]]] = (
        defaultdict(list)
    )
    for row in with_salary:
        currency = (row["currency_code"] or "").strip() or "UNKNOWN"
        period = (row["pay_period"] or "").strip() or "UNKNOWN"
        groups[(currency, period)].append((row["salary_min"], row["salary_max"]))

    summaries: list[dict[str, Any]] = []
    for (currency, period), ranges in sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), item[0][0], item[0][1]),
    ):
        lows: list[Decimal] = []
        highs: list[Decimal] = []
        mids: list[Decimal] = []
        for mn, mx in ranges:
            if mn is not None:
                lows.append(mn)
            if mx is not None:
                highs.append(mx)
            mid = _midpoint(mn, mx)
            if mid is not None:
                mids.append(mid)

        # 그룹 min = 각 공고 하한(없으면 상한) 중 최소
        # 그룹 max = 각 공고 상한(없으면 하한) 중 최대
        group_mins = [mn if mn is not None else mx for mn, mx in ranges if mn or mx]
        group_maxs = [mx if mx is not None else mn for mn, mx in ranges if mn or mx]
        group_mins_f = [v for v in group_mins if v is not None]
        group_maxs_f = [v for v in group_maxs if v is not None]
        if not mids or not group_mins_f or not group_maxs_f:
            continue

        avg = sum(mids) / len(mids)
        summaries.append(
            {
                "currency_code": currency,
                "pay_period": period,
                "group_sample_count": len(ranges),
                "min": _dec_to_json(min(group_mins_f)),
                "max": _dec_to_json(max(group_maxs_f)),
                "avg": _dec_to_json(avg),
            }
        )

    total = len(with_salary)
    group_note = ", ".join(
        f"{s['currency_code']}/{s['pay_period']}={s['group_sample_count']}"
        for s in summaries
    )
    return {
        "status": "ok",
        "message": (
            f"salary_data_count={total} posting(s) have numeric salary "
            f"(matched_postings={matched_count}). "
            f"Stats are split by currency/pay_period: {group_note}. "
            "Use salary_data_count for the overall count; "
            "do not treat a single group's group_sample_count as the total."
        ),
        **base,
        "summaries": summaries,
    }
