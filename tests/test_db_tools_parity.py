"""같은 SAMPLE_DOCS 를 메모리 스토어와 DB 에 두고 tool 응답이 같은지 비교한다."""
from __future__ import annotations

import json

import pytest

from src.db.ingest import ingest_documents
from src.mcp_server.tools.category_stats import get_posting_count_by_category
from src.mcp_server.tools.company_activity import get_company_hiring_activity
from src.mcp_server.tools.salary_summary import get_salary_summary
from src.mcp_server.tools.search import search_job_postings
from src.mcp_server.tools.skill_trend import get_skill_trend
from src.mcp_server.data_loader import JobPostingStore
from tests.conftest import SAMPLE_DOCS, doc

# 동률일 때 순서가 달라질 수 있는 목록
_UNORDERED = ("results", "postings", "skills", "job_function_counts", "location_counts", "suggestions")
# Task 5 가 get_skill_trend 에 더하는 키
_IGNORED = ("series", "series_note", "collection_gaps")


def comparable(out: dict) -> dict:
    res = {k: v for k, v in out.items() if k not in _IGNORED}
    for key in _UNORDERED:
        if isinstance(res.get(key), list):
            res[key] = sorted(res[key], key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True))
    return res


@pytest.fixture
def seeded(db_conn):
    ingest_documents(db_conn, SAMPLE_DOCS, ingest_source="t")
    return db_conn


CASES = [
    (search_job_postings, {}), (search_job_postings, {"job_function": "Backend Engineer"}),
    (search_job_postings, {"job_function": "Backend Engineer", "active_only": False}),
    (search_job_postings, {"job_category": "data & analytics"}),
    (search_job_postings, {"location": "서울", "employment_type": "Full-time"}),
    (search_job_postings, {"work_arrangement": "remote", "source_name": "원티드"}),
    (search_job_postings, {"job_function": "zz-not-a-role"}), (search_job_postings, {"limit": 1}),
    # 정규화하면 빈 값이 되는 입력은 메모리 경로처럼 필터를 걸지 않는다
    (search_job_postings, {"employment_type": "_"}), (search_job_postings, {"employment_type": " - "}),
    (get_skill_trend, {"job_function": "Backend Engineer"}),
    (get_skill_trend, {"job_function": "Data Analyst", "source_name": "jumpit"}),
    (get_posting_count_by_category, {}), (get_posting_count_by_category, {"source_name": "wanted"}),
    (get_salary_summary, {}), (get_salary_summary, {"job_function": "Backend Engineer"}),
    (get_salary_summary, {"job_function": "Backend Engineer", "location": "부산"}),
    (get_company_hiring_activity, {"company_name": "acme"}),
    (get_company_hiring_activity, {"company_name": "Acm"}),
    (get_company_hiring_activity, {"company_name": ""}),
]


@pytest.mark.parametrize("fn, kwargs", CASES)
def test_sql_path_equals_memory_path(fn, kwargs, sample_store, seeded):
    assert comparable(fn(**kwargs, conn=seeded)) == comparable(fn(**kwargs, store=sample_store))


def test_padded_function_category_source_match_like_memory(db_conn):
    padded = doc(source_job_id="pad1", job_function_name=" Backend Engineer ",
                 job_category_name=" Engineering & Technology ", source_name=" jumpit ")
    ingest_documents(db_conn, [padded], ingest_source="t")
    store = JobPostingStore(postings=[padded])
    store.by_function["Backend Engineer"].append(padded)
    store.by_category["Engineering & Technology"].append(padded)
    for kwargs in [
        {"job_function": "Backend Engineer", "source_name": "jumpit"},
        {"job_category": "Engineering & Technology"},
    ]:
        sql = search_job_postings(**kwargs, conn=db_conn)
        assert sql["total_matched"] == 1
        assert sql["total_matched"] == search_job_postings(**kwargs, store=store)["total_matched"]
    by_name = {c["category"]: c["count"] for c in get_posting_count_by_category(conn=db_conn)["categories"]}
    assert by_name["Engineering & Technology"] == 1
