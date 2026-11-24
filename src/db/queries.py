"""MCP tool · REST API 가 쓰는 공고 조회 SQL.

모든 함수는 `conn` 을 첫 인자로 받고, 값은 반드시 바인드 파라미터로 넘긴다.
필터는 메모리 경로(src/mcp_server/tools/*)와 같은 뜻이다. 부분 일치는 `LIKE` 대신
`position(...)` 을 써서 `%` · `_` 가 와일드카드로 해석되지 않게 한다.
파생 컬럼(location_blob, employment_type_norm, company_key, salary_*, sort_key)은
적재 시 메모리 경로의 함수로 계산해 두었으므로 여기서 다시 계산하지 않는다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator

import psycopg

from src.db.connection import connection
# tools 모듈이 이 모듈을 import 하므로 함수가 아니라 모듈을 가져온다(순환 import).
from src.mcp_server.tools import search as _search_tools

# 정렬 키는 ISO 날짜 · 시각 문자열이다. DB 기본 collation(en_US)은 구두점을 무시하므로
# 메모리 경로(파이썬 문자열 비교)와 같게 바이트 순서로 비교한다.
_ORDER_RECENT = 'p.sort_key COLLATE "C" DESC, p.id'


@contextmanager
def use_connection(conn: psycopg.Connection | None) -> Iterator[psycopg.Connection]:
    """주어진 연결을 그대로 쓰거나, 없으면 풀에서 빌린다."""
    if conn is not None:
        yield conn
        return
    with connection() as borrowed:
        yield borrowed


def _text(value: str | None) -> str | None:
    """앞뒤 공백을 지운 값. 비면 None (필터를 걸지 않는다)."""
    text = (value or "").strip()
    return text or None


def _where(
    *,
    job_function: str | None = None,
    job_category: str | None = None,
    source_name: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    work_arrangement: str | None = None,
    keyword: str | None = None,
    skill: str | None = None,
    posted_from: date | None = None,
    company_key: str | None = None,
    active_only: bool = True,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if active_only:
        clauses.append("p.crawl_status = 'ACTIVE'")
    if _text(job_function):
        clauses.append("p.job_function_name = %(job_function)s")
        params["job_function"] = _text(job_function)
    if _text(job_category):
        clauses.append("p.job_category_name = %(job_category)s")
        params["job_category"] = _text(job_category)
    if _text(source_name):
        clauses.append("p.source_name = %(source_name)s")
        params["source_name"] = _text(source_name)
    if _text(location):
        clauses.append("position(lower(%(location)s) in p.location_blob) > 0")
        params["location"] = _text(location).lower()
    emp = (_text(employment_type) or "").lower()
    emp_norm = _search_tools._norm_enum_token(emp)
    # 메모리 경로처럼 정규화 값이 비면("_", " - " 등) 필터를 걸지 않는다.
    if emp_norm:
        clauses.append(
            "(p.employment_type_norm = %(employment_norm)s "
            "OR position(lower(%(employment_type)s) in lower(p.employment_type_name)) > 0)"
        )
        params["employment_type"] = emp
        params["employment_norm"] = emp_norm
    if _text(work_arrangement):
        clauses.append(
            "position(lower(%(work_arrangement)s) in lower(coalesce(p.work_arrangement, ''))) > 0"
        )
        params["work_arrangement"] = _text(work_arrangement).lower()
    if _text(keyword):
        clauses.append(
            "(position(lower(%(keyword)s) in lower(p.title)) > 0 "
            "OR position(lower(%(keyword)s) in lower(p.normalized_title)) > 0 "
            "OR position(lower(%(keyword)s) in lower(coalesce(p.company_name, ''))) > 0)"
        )
        params["keyword"] = _text(keyword).lower()
    if _text(skill):
        clauses.append(
            "EXISTS (SELECT 1 FROM posting_skills s "
            "WHERE s.posting_id = p.id AND s.canonical_name = %(skill)s)"
        )
        params["skill"] = _text(skill)
    if posted_from is not None:
        clauses.append("p.posted_on >= %(posted_from)s")
        params["posted_from"] = posted_from
    if company_key is not None:
        clauses.append("p.company_key = %(company_key)s")
        params["company_key"] = company_key

    where = " AND ".join(clauses) if clauses else "TRUE"
    return where, params


def count_postings(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM postings").fetchone()["n"]


def search_postings(
    conn,
    *,
    job_function: str | None = None,
    job_category: str | None = None,
    source_name: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    work_arrangement: str | None = None,
    keyword: str | None = None,
    skill: str | None = None,
    posted_from: date | None = None,
    active_only: bool = True,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    """(조건에 맞는 전체 수, 최근 순 `doc` 목록)."""
    where, params = _where(
        job_function=job_function, job_category=job_category, source_name=source_name,
        location=location, employment_type=employment_type,
        work_arrangement=work_arrangement, keyword=keyword, skill=skill,
        posted_from=posted_from, active_only=active_only,
    )
    total = conn.execute(f"SELECT count(*) AS n FROM postings p WHERE {where}", params).fetchone()["n"]
    rows = conn.execute(
        f"SELECT p.doc FROM postings p WHERE {where} "
        f"ORDER BY {_ORDER_RECENT} LIMIT %(limit)s OFFSET %(offset)s",
        {**params, "limit": max(0, int(limit)), "offset": max(0, int(offset))},
    ).fetchall()
    return total, [r["doc"] for r in rows]


def skill_counts(
    conn,
    *,
    job_function: str,
    source_name: str | None = None,
    active_only: bool = True,
    top_n: int = 15,
) -> tuple[int, list[tuple[str, int]]]:
    """(공고 수, 스킬별 공고 수 상위 N). 정렬은 count DESC, canonical_name."""
    where, params = _where(job_function=job_function, source_name=source_name, active_only=active_only)
    total = conn.execute(f"SELECT count(*) AS n FROM postings p WHERE {where}", params).fetchone()["n"]
    rows = conn.execute(
        "SELECT btrim(s.canonical_name) AS name, count(DISTINCT s.posting_id) AS n "
        f"FROM postings p JOIN posting_skills s ON s.posting_id = p.id "
        f"WHERE {where} AND btrim(s.canonical_name) <> '' "
        "GROUP BY 1 ORDER BY n DESC, name LIMIT %(top_n)s",
        {**params, "top_n": max(0, int(top_n))},
    ).fetchall()
    return total, [(r["name"], r["n"]) for r in rows]


def category_counts(conn, *, source_name: str | None = None, active_only: bool = True) -> dict[str, int]:
    """job_category_name(빈 문자열 포함) → 공고 수."""
    where, params = _where(source_name=source_name, active_only=active_only)
    rows = conn.execute(
        f"SELECT p.job_category_name AS cat, count(*) AS n FROM postings p WHERE {where} GROUP BY 1",
        params,
    ).fetchall()
    return {r["cat"]: r["n"] for r in rows}


def salary_rows(
    conn,
    *,
    job_function: str | None = None,
    location: str | None = None,
    source_name: str | None = None,
    active_only: bool = True,
) -> tuple[int, list[dict[str, Any]]]:
    """(조건에 맞는 공고 수, 숫자 급여가 있는 공고의 salary_min/max · currency_code · pay_period)."""
    where, params = _where(
        job_function=job_function, location=location, source_name=source_name,
        active_only=active_only,
    )
    total = conn.execute(f"SELECT count(*) AS n FROM postings p WHERE {where}", params).fetchone()["n"]
    rows = conn.execute(
        "SELECT p.salary_min, p.salary_max, p.currency_code, p.pay_period FROM postings p "
        f"WHERE {where} AND (p.salary_min IS NOT NULL OR p.salary_max IS NOT NULL) "
        "ORDER BY p.id",
        params,
    ).fetchall()
    return total, [dict(r) for r in rows]


def company_index(conn, *, source_name: str | None = None, active_only: bool = True) -> dict[str, str]:
    """company_key → 가장 많이 쓰인 company_name."""
    where, params = _where(source_name=source_name, active_only=active_only)
    rows = conn.execute(
        "SELECT DISTINCT ON (p.company_key) p.company_key AS key, p.company_name AS name "
        f"FROM postings p WHERE {where} AND p.company_key <> '' "
        "GROUP BY p.company_key, p.company_name "
        "ORDER BY p.company_key, count(*) DESC, p.company_name COLLATE \"C\"",
        params,
    ).fetchall()
    return {r["key"]: r["name"] for r in rows}


def company_postings(
    conn,
    company_key: str,
    *,
    source_name: str | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """해당 회사의 `doc` 목록, 최근 순."""
    where, params = _where(company_key=company_key, source_name=source_name, active_only=active_only)
    rows = conn.execute(
        f"SELECT p.doc FROM postings p WHERE {where} ORDER BY {_ORDER_RECENT}",
        params,
    ).fetchall()
    return [r["doc"] for r in rows]
