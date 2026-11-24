"""get_skill_trend SQL 경로의 주 단위 시계열."""
from __future__ import annotations

import pytest

from src.db.ingest import ingest_documents, upsert_posting
from src.mcp_server.tools.skill_trend import get_skill_trend
from tests.conftest import doc


@pytest.fixture
def weekly(db_conn):
    def be(i, day, skills):
        ts = f"{day}T00:00:00+00:00"
        return doc(source_job_id=f"w{i}", created_at=ts, last_seen_at=ts, first_collected_at=ts,
                   skills=[{"raw_text": s, "canonical_name": s} for s in skills])
    ingest_documents(db_conn, [
        be(1, "2026-07-29", ["Python", "Docker"]), be(2, "2026-07-30", ["Python"]),
        be(3, "2026-08-04", ["Go"]),                # 다음 주
        be(4, "2026-11-24", ["Python", "Go"]),      # 공백 뒤
    ], ingest_source="t")
    return db_conn


def test_series_buckets_by_week_with_share(weekly):
    out = get_skill_trend("Backend Engineer", conn=weekly)
    assert [w["week_start"] for w in out["series"]] == ["2026-07-27", "2026-08-03", "2026-11-23"]
    first = out["series"][0]
    assert first["posting_count"] == 2
    assert {s["skill"]: (s["count"], s["share"]) for s in first["skills"]} == {
        "Python": (2, 1.0), "Go": (0, 0.0), "Docker": (1, 0.5)}


def test_series_skills_follow_top_n_order(weekly):
    out = get_skill_trend("Backend Engineer", top_n=1, conn=weekly)
    assert [[s["skill"] for s in w["skills"]] for w in out["series"]] == [["Python"]] * 3


def test_gap_is_reported_not_bridged(weekly):
    out = get_skill_trend("Backend Engineer", conn=weekly)
    assert out["collection_gaps"] == [{"from": "2026-08-10", "to": "2026-11-22"}]
    assert "share" in out["series_note"]


def test_same_posting_seen_twice_in_a_week_counts_once(weekly):
    ts = "2026-07-31T00:00:00+00:00"
    upsert_posting(weekly, doc(source_job_id="w1", created_at=ts, last_seen_at=ts,
                               skills=[{"raw_text": "Python", "canonical_name": "Python"},
                                       {"raw_text": "Docker", "canonical_name": "Docker"}]),
                   ingest_source="t")
    assert get_skill_trend("Backend Engineer", conn=weekly)["series"][0]["posting_count"] == 2


def test_empty_has_empty_series_and_unknown_has_none(db_conn):
    assert get_skill_trend("Backend Engineer", conn=db_conn)["series"] == []
    assert "series" not in get_skill_trend("zz-not-a-role", conn=db_conn)
