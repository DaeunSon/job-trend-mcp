"""공고 문서를 PostgreSQL 에 멱등 적재한다.

호출자의 트랜잭션 안에서만 쓴다(여기서는 commit 하지 않는다).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Literal

from psycopg.types.json import Jsonb

from src.mcp_server.data_loader import _recrawl_sort_key
from src.mcp_server.tools.company_activity import _norm_company_key
from src.mcp_server.tools.salary_summary import _parse_amount
from src.mcp_server.tools.search import _location_blob, _norm_enum_token

Outcome = Literal["inserted", "updated", "unchanged", "skipped"]


@dataclass
class IngestResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    observations: int = 0


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_posted_on(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _row(doc: dict[str, Any]) -> dict[str, Any]:
    company = doc.get("company")
    company_name = company.get("name") if isinstance(company, dict) else None
    location = doc.get("location")
    city = location.get("city_name") if isinstance(location, dict) else None
    salary = doc.get("salary") if isinstance(doc.get("salary"), dict) else {}
    created = _parse_ts(doc.get("created_at"))
    return {
        "doc_id": None if doc.get("id") is None else str(doc["id"]),
        "title": _s(doc.get("title")),
        "normalized_title": _s(doc.get("normalized_title")),
        "company_name": company_name,
        "company_key": _norm_company_key(str(company_name)) if company_name else "",
        "job_function_name": _s(doc.get("job_function_name")),
        "job_category_name": _s(doc.get("job_category_name")),
        "employment_type_name": _s(doc.get("employment_type_name")),
        "employment_type_norm": _norm_enum_token(_s(doc.get("employment_type_name"))),
        "work_arrangement": doc.get("work_arrangement"),
        "city_name": city,
        "location_blob": _location_blob(doc),
        "salary_min": _parse_amount(salary.get("min_amount")),
        "salary_max": _parse_amount(salary.get("max_amount")),
        "currency_code": salary.get("currency_code"),
        "pay_period": salary.get("pay_period"),
        "crawl_status": _s(doc.get("crawl_status")) or "ACTIVE",
        "posted_on": _parse_posted_on(doc.get("posted_at")),
        "sort_key": _s(doc.get("posted_at") or doc.get("last_seen_at") or doc.get("created_at")),
        "recrawl_key": _recrawl_sort_key(doc),
        "first_collected_at": _parse_ts(doc.get("first_collected_at")) or created,
        "last_seen_at": _parse_ts(doc.get("last_seen_at")) or created,
        "doc": Jsonb(doc),
    }


def _skill_names(doc: dict[str, Any]) -> list[str]:
    names: dict[str, None] = {}
    for skill in doc.get("skills") or []:
        name = skill.get("canonical_name")
        if name:
            names[str(name)] = None
    return list(names)


_CONTENT_COLS = [
    "doc_id", "title", "normalized_title", "company_name", "company_key",
    "job_function_name", "job_category_name", "employment_type_name",
    "employment_type_norm", "work_arrangement", "city_name", "location_blob",
    "salary_min", "salary_max", "currency_code", "pay_period", "posted_on",
    "sort_key", "recrawl_key", "doc",
]


def _replace_skills(conn, posting_id: int, names: list[str]) -> None:
    conn.execute("DELETE FROM posting_skills WHERE posting_id = %s", (posting_id,))
    for name in names:
        conn.execute(
            "INSERT INTO posting_skills (posting_id, canonical_name) VALUES (%s, %s)",
            (posting_id, name),
        )


def _observe(conn, posting_id: int, doc: dict[str, Any], ingest_source: str) -> int:
    ts = _parse_ts(doc.get("created_at")) or _parse_ts(doc.get("last_seen_at"))
    if ts is None:
        return 0
    cur = conn.execute(
        "INSERT INTO posting_observations (posting_id, observed_on, ingest_source) "
        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (posting_id, ts.astimezone(timezone.utc).date(), ingest_source),
    )
    return cur.rowcount


def _upsert(conn, doc: dict[str, Any], ingest_source: str) -> tuple[Outcome, int]:
    source_name = _s(doc.get("source_name")).strip()
    source_job_id = _s(doc.get("source_job_id")).strip()
    if not source_name or not source_job_id:
        return "skipped", 0
    row = _row(doc)
    names = _skill_names(doc)

    existing = conn.execute(
        "SELECT id, recrawl_key FROM postings WHERE source_name = %s AND source_job_id = %s "
        "FOR UPDATE",
        (source_name, source_job_id),
    ).fetchone()

    if existing is None:
        cols = ["source_name", "source_job_id", "ingest_source", *_CONTENT_COLS,
                "crawl_status", "first_collected_at", "last_seen_at"]
        values = {**row, "source_name": source_name, "source_job_id": source_job_id,
                  "ingest_source": ingest_source}
        posting_id = conn.execute(
            f"INSERT INTO postings ({', '.join(cols)}) "
            f"VALUES ({', '.join('%(' + c + ')s' for c in cols)}) RETURNING id",
            values,
        ).fetchone()["id"]
        _replace_skills(conn, posting_id, names)
        return "inserted", _observe(conn, posting_id, doc, ingest_source)

    posting_id = existing["id"]
    conn.execute(
        "UPDATE postings SET "
        "first_collected_at = LEAST(first_collected_at, %(first)s), "
        "last_seen_at = GREATEST(last_seen_at, %(last)s) WHERE id = %(id)s",
        {"first": row["first_collected_at"], "last": row["last_seen_at"], "id": posting_id},
    )
    outcome: Outcome = "unchanged"
    if row["recrawl_key"] >= existing["recrawl_key"]:
        sets = ", ".join(f"{c} = %({c})s" for c in _CONTENT_COLS)
        conn.execute(
            f"UPDATE postings SET {sets}, updated_at = now() WHERE id = %(id)s",
            {**row, "id": posting_id},
        )
        _replace_skills(conn, posting_id, names)
        outcome = "updated"
    return outcome, _observe(conn, posting_id, doc, ingest_source)


def upsert_posting(conn, doc: dict[str, Any], *, ingest_source: str) -> Outcome:
    return _upsert(conn, doc, ingest_source)[0]


def ingest_documents(conn, docs: Iterable[dict[str, Any]], *, ingest_source: str) -> IngestResult:
    result = IngestResult()
    for doc in docs:
        outcome, observed = _upsert(conn, doc, ingest_source)
        setattr(result, outcome, getattr(result, outcome) + 1)
        result.observations += observed
    return result


def delete_ingest_source(conn, ingest_source: str) -> int:
    """해당 표시의 관측을 지우고, 관측이 남지 않은 공고를 지운다. 지운 공고 수를 돌려준다."""
    conn.execute("DELETE FROM posting_observations WHERE ingest_source = %s", (ingest_source,))
    cur = conn.execute(
        "DELETE FROM postings p WHERE NOT EXISTS "
        "(SELECT 1 FROM posting_observations o WHERE o.posting_id = p.id)"
    )
    return cur.rowcount
