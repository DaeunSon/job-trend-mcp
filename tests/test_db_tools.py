"""MCP tool 5개의 SQL 경로 테스트 (tests/test_mcp_server.py 의 메모리 경로 테스트를 옮긴 것)."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from src.db.connection import DatabaseUnavailable, reset_pool
from src.db.ingest import ingest_documents, upsert_posting
from src.mcp_server.tools.category_stats import get_posting_count_by_category
from src.mcp_server.tools.company_activity import get_company_hiring_activity
from src.mcp_server.tools.salary_summary import get_salary_summary
from src.mcp_server.tools.search import search_job_postings
from src.mcp_server.tools.skill_trend import get_skill_trend
from src.taxonomy.job_categories import JOB_CATEGORIES
from tests.conftest import SAMPLE_DOCS, count, doc


@pytest.fixture
def seeded(db_conn):
    ingest_documents(db_conn, SAMPLE_DOCS, ingest_source="t")
    return db_conn


class TestSearch:
    def test_filter_by_function_and_location(self, seeded):
        out = search_job_postings(
            job_function="Backend Engineer",
            location="서울",
            conn=seeded,
        )
        assert out["status"] == "ok"
        assert out["count"] == 1
        assert out["results"][0]["title"] == "Backend Engineer A"
        assert "description" not in out["results"][0]

    def test_active_only_default(self, seeded):
        out = search_job_postings(job_function="Backend Engineer", conn=seeded)
        titles = {r["title"] for r in out["results"]}
        assert "Expired Backend" not in titles
        assert out["count"] == 2

    def test_active_only_false_includes_expired(self, seeded):
        out = search_job_postings(
            job_function="Backend Engineer",
            active_only=False,
            conn=seeded,
        )
        assert out["count"] == 3

    def test_unknown_function_returns_guidance(self, seeded):
        out = search_job_postings(job_function="not-a-real-role-xyz", conn=seeded)
        assert out["status"] == "unknown_param"
        assert out["results"] == []
        assert "available_job_functions" in out

    def test_alias_korean_function_resolves(self, seeded):
        out = search_job_postings(job_function="백엔드 개발자", conn=seeded)
        assert out["status"] == "ok"
        assert out["count"] >= 1

    def test_employment_type_underscore_matches_hyphen(self, seeded):
        out = search_job_postings(
            job_function="Backend Engineer",
            employment_type="full-time",
            conn=seeded,
        )
        assert out["status"] == "ok"
        assert out["count"] >= 1

    def test_valid_but_empty(self, seeded):
        out = search_job_postings(
            job_function="Backend Engineer",
            location="제주",
            conn=seeded,
        )
        assert out["status"] == "empty"
        assert out["results"] == []

    def test_filter_by_source_name(self, seeded):
        out = search_job_postings(
            job_function="Backend Engineer",
            source_name="jumpit",
            conn=seeded,
        )
        assert out["status"] == "ok"
        assert out["total_matched"] == 2
        assert {r["source_name"] for r in out["results"]} == {"jumpit"}

        wanted_only = search_job_postings(
            source_name="wanted",
            conn=seeded,
        )
        assert wanted_only["status"] == "ok"
        assert wanted_only["total_matched"] == 1
        assert wanted_only["results"][0]["title"] == "Data Analyst"
        assert wanted_only["results"][0]["source_name"] == "wanted"

    def test_source_name_case_insensitive(self, seeded):
        out = search_job_postings(source_name="Jumpit", conn=seeded)
        assert out["status"] == "ok"
        assert {r["source_name"] for r in out["results"]} == {"jumpit"}

    def test_unknown_source_name(self, seeded):
        out = search_job_postings(source_name="linkedin", conn=seeded)
        assert out["status"] == "unknown_param"
        assert out["results"] == []
        assert "available_source_names" in out
        assert "jobkorea" in out["available_source_names"]

    def test_korean_source_name_filters_like_canonical(self, seeded):
        assert (
            search_job_postings(source_name="점핏", conn=seeded)["total_matched"]
            == search_job_postings(source_name="jumpit", conn=seeded)["total_matched"]
        )

    @pytest.mark.parametrize("raw", ["디자이너", "AI 개발자", "data", "Healthcare"])
    def test_role_in_source_name_explains_which_param(self, seeded, raw: str):
        out = get_posting_count_by_category(source_name=raw, conn=seeded)
        assert out["status"] == "unknown_param"
        assert "not a role" in out["message"]

    def test_category_in_source_name_points_to_job_category(self, seeded):
        out = get_posting_count_by_category(source_name="Healthcare", conn=seeded)
        assert "use job_category" in out["message"]

    def test_salary_with_korean_source_name_resolves(self, seeded):
        out = get_salary_summary(job_function="Data Analyst", source_name="사람인", conn=seeded)
        assert out["status"] != "unknown_param"

    def test_source_name_omitted_keeps_all_sources(self, seeded):
        out = search_job_postings(conn=seeded)
        sources = {r["source_name"] for r in out["results"]}
        assert sources == {"jumpit", "wanted"}
        assert out["total_matched"] == 4  # ACTIVE only, mixed sources


class TestSkillTrend:
    def test_counts_canonical_skills(self, seeded):
        out = get_skill_trend("Backend Engineer", top_n=5, conn=seeded)
        assert out["status"] == "ok"
        skills = {s["skill"]: s["count"] for s in out["skills"]}
        assert skills["Python"] == 2
        assert skills["Docker"] == 1
        assert "Go" not in skills  # EXPIRED 공고 제외

    def test_source_name_filters_skill_pool(self, seeded):
        out = get_skill_trend("Data Analyst", source_name="wanted", conn=seeded)
        assert out["status"] == "ok"
        assert out["posting_count"] == 1
        assert out["skills"][0]["skill"] == "SQL"

        empty = get_skill_trend("Data Analyst", source_name="jumpit", conn=seeded)
        assert empty["status"] == "empty"

    def test_unknown_function(self, seeded):
        out = get_skill_trend("not-a-real-role", conn=seeded)
        assert out["status"] == "unknown_param"
        assert out["skills"] == []


class TestCategoryStats:
    def test_includes_zero_categories(self, seeded):
        out = get_posting_count_by_category(conn=seeded)
        assert out["status"] == "ok"
        assert len(out["categories"]) == len(JOB_CATEGORIES)
        by_name = {c["category"]: c["count"] for c in out["categories"]}
        assert by_name["Engineering & Technology"] == 3  # ACTIVE only
        assert by_name["Data & Analytics"] == 1
        assert by_name["Education & Training"] == 0
        assert by_name["Legal & Compliance"] == 0

    def test_source_name_filters_counts(self, seeded):
        out = get_posting_count_by_category(source_name="wanted", conn=seeded)
        by_name = {c["category"]: c["count"] for c in out["categories"]}
        assert by_name["Data & Analytics"] == 1
        assert by_name["Engineering & Technology"] == 0
        assert out["total_postings"] == 1


class TestSalarySummary:
    def test_with_salary_data(self, seeded):
        out = get_salary_summary(
            job_function="Backend Engineer",
            location="서울",
            conn=seeded,
        )
        assert out["status"] == "ok"
        assert out["matched_postings"] == 1
        assert out["salary_data_count"] == 1
        assert "postings_with_salary_data" not in out
        assert len(out["summaries"]) == 1
        s = out["summaries"][0]
        assert s["currency_code"] == "KRW"
        assert s["pay_period"] == "ANNUAL"
        assert s["group_sample_count"] == 1
        assert "postings_with_salary_data" not in s
        assert s["min"] == 60000000
        assert s["max"] == 80000000
        assert s["avg"] == 70000000
        assert "salary_data_count=" in (out["message"] or "")

    def test_no_salary_data(self, seeded):
        out = get_salary_summary(
            job_function="Backend Engineer",
            location="부산",
            conn=seeded,
        )
        assert out["status"] == "no_salary_data"
        assert out["matched_postings"] == 1
        assert out["salary_data_count"] == 0
        assert out["summaries"] == []

    def test_does_not_mix_currencies(self, seeded):
        out = get_salary_summary(conn=seeded)
        assert out["status"] == "ok"
        currencies = {s["currency_code"] for s in out["summaries"]}
        assert currencies == {"KRW", "USD"}
        assert sum(s["group_sample_count"] for s in out["summaries"]) == out[
            "salary_data_count"
        ]


class TestCompanyHiringActivity:
    def test_existing_company(self, seeded):
        out = get_company_hiring_activity("acme", limit=10, conn=seeded)
        assert out["status"] == "ok"
        assert out["company_name"] == "Acme"
        assert out["matched_postings"] == 3
        fns = {x["job_function"]: x["count"] for x in out["job_function_counts"]}
        assert fns["Backend Engineer"] == 2
        assert fns["Frontend Engineer"] == 1
        assert len(out["postings"]) == 3

    def test_unknown_company_suggests(self, seeded):
        out = get_company_hiring_activity("Acm", conn=seeded)
        assert out["status"] == "unknown_company"
        assert out["matched_postings"] == 0
        assert "Acme" in out["suggestions"]
        assert out["postings"] == []


def test_location_special_chars_are_literal(seeded):
    for q in ["%", "_", "서울'; DROP TABLE postings;--"]:
        out = search_job_postings(location=q, conn=seeded)
        assert out["status"] == "empty" and out["total_matched"] == 0
    assert count(seeded, "postings") == 5


def test_category_counts_include_uncategorized(seeded):
    upsert_posting(seeded, doc(source_job_id="u1", source_name="indeed",
                               job_function_name="", job_category_name=""), ingest_source="t")
    out = get_posting_count_by_category(conn=seeded)
    assert out["uncategorized_count"] == 1
    assert out["total_postings"] == sum(c["count"] for c in out["categories"]) + 1


def test_results_have_no_description(seeded):
    out = search_job_postings(conn=seeded)
    assert all("description" not in r for r in out["results"])


def test_server_imports_without_database():
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "TEST_DATABASE_URL")}
    proc = subprocess.run([sys.executable, "-c", "import src.mcp_server.server"],
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_tool_raises_database_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none_test")
    reset_pool()
    try:
        with pytest.raises(DatabaseUnavailable):
            search_job_postings()
    finally:
        monkeypatch.undo(); reset_pool()
