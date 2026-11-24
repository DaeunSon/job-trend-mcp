"""공고 검색 REST API. 실행: uvicorn src.api.app:app --host 127.0.0.1 --port 8001"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Iterator

import psycopg
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from src.db import queries
from src.db.connection import DatabaseUnavailable, connection
from src.mcp_server.data_loader import JobPostingStore
from src.mcp_server.tools.search import summarize_posting
from src.taxonomy.skills import lookup_skill_canonical

NOTE = "Collected sample from capped daily crawls; not a full census."

app = FastAPI(title="job-trend search API")


def get_conn() -> Iterator[psycopg.Connection]:
    with connection() as conn:
        yield conn


Conn = Annotated[psycopg.Connection, Depends(get_conn)]


@app.exception_handler(DatabaseUnavailable)
def _db_unavailable(request: Request, exc: DatabaseUnavailable) -> JSONResponse:
    if request.url.path == "/healthz":
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"detail": "database unavailable"}, status_code=503)


class _BadParam(Exception):
    def __init__(self, param: str, detail: str):
        self.param, self.detail = param, detail


@app.exception_handler(_BadParam)
def _bad_param(request: Request, exc: _BadParam) -> JSONResponse:
    return JSONResponse({"detail": exc.detail, "param": exc.param}, status_code=400)


@app.get("/healthz")
def healthz(conn: Conn) -> dict:
    return {"status": "ok", "postings": queries.count_postings(conn)}


@app.get("/api/v1/postings")
def search(
    conn: Conn,
    job_function: str | None = None,
    job_category: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    work_arrangement: str | None = None,
    source_name: str | None = None,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    skill: str | None = None,
    posted_from: date | None = None,
    active_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    resolver = JobPostingStore()  # 데이터를 올리지 않은 스토어: 이름 해석에만 쓴다

    resolved_fn, err = resolver.resolve_job_function(job_function)
    if err:
        raise _BadParam("job_function", err)

    if job_category and job_category.strip():
        cat = job_category.strip()
        known = {c.lower(): c for c in resolver.known_categories}
        if cat not in resolver.known_categories and cat.lower() not in known:
            raise _BadParam(
                "job_category",
                f"Unknown job_category {cat!r}. Available: {', '.join(resolver.known_categories)}",
            )
        job_category = known.get(cat.lower(), cat)

    resolved_src, err = resolver.resolve_source_name(source_name)
    if err:
        raise _BadParam("source_name", err)

    canonical_skill = None
    if skill and skill.strip():
        canonical_skill = lookup_skill_canonical(skill)
        if canonical_skill is None:
            raise _BadParam("skill", f"Unknown skill {skill.strip()!r}.")

    total, docs = queries.search_postings(
        conn,
        job_function=resolved_fn,
        job_category=job_category,
        source_name=resolved_src,
        location=location,
        employment_type=employment_type,
        work_arrangement=work_arrangement,
        keyword=q,
        skill=canonical_skill,
        posted_from=posted_from,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [summarize_posting(d) for d in docs],
        "note": NOTE,
    }
