from datetime import date
from decimal import Decimal

import pytest

from src.db.ingest import delete_ingest_source, ingest_documents, upsert_posting
from tests.conftest import SAMPLE_DOCS, count, doc


def test_insert_maps_columns(db_conn):
    assert upsert_posting(db_conn, doc(), ingest_source="t") == "inserted"
    row = db_conn.execute("SELECT * FROM postings").fetchone()
    assert (row["company_key"], row["employment_type_norm"]) == ("acme", "fulltime")
    assert (row["salary_min"], row["salary_max"]) == (Decimal("60000000"), Decimal("80000000"))
    assert "서울" in row["location_blob"] and row["posted_on"] == date(2026, 8, 1)
    assert count(db_conn, "posting_skills") == 2 and count(db_conn, "posting_observations") == 1


def test_ingest_twice_is_idempotent(db_conn):
    first = ingest_documents(db_conn, SAMPLE_DOCS, ingest_source="t")
    second = ingest_documents(db_conn, SAMPLE_DOCS, ingest_source="t")
    assert (first.inserted, second.inserted, second.observations) == (5, 0, 0)
    assert count(db_conn, "postings") == 5 and count(db_conn, "posting_observations") == 5


def test_recrawl_adds_observation_and_widens_dates(db_conn):
    upsert_posting(db_conn, doc(), ingest_source="t")
    later = doc(title="A (recrawl)", created_at="2026-08-03T00:00:00+00:00",
                last_seen_at="2026-08-03T00:00:00+00:00")
    assert upsert_posting(db_conn, later, ingest_source="t") == "updated"
    row = db_conn.execute("SELECT * FROM postings").fetchone()
    assert row["title"] == "A (recrawl)"
    assert row["first_collected_at"].date() == date(2026, 8, 1)
    assert row["last_seen_at"].date() == date(2026, 8, 3)
    assert count(db_conn, "posting_observations") == 2


def test_older_record_does_not_overwrite_newer(db_conn):
    newer = doc(title="new", created_at="2026-08-03T00:00:00+00:00")
    older = doc(title="old", created_at="2026-07-30T00:00:00+00:00")
    upsert_posting(db_conn, newer, ingest_source="t")
    assert upsert_posting(db_conn, older, ingest_source="t") == "unchanged"
    assert db_conn.execute("SELECT title FROM postings").fetchone()["title"] == "new"
    assert count(db_conn, "posting_observations") == 2


def test_missing_key_is_skipped(db_conn):
    assert upsert_posting(db_conn, doc(source_job_id=""), ingest_source="t") == "skipped"
    assert count(db_conn, "postings") == 0


def test_unknown_source_and_empty_function_are_kept(db_conn):
    d = doc(source_name="indeed", job_function_name="", job_category_name="")
    assert upsert_posting(db_conn, d, ingest_source="t") == "inserted"


def test_bad_posted_at_becomes_null(db_conn):
    upsert_posting(db_conn, doc(posted_at="상시채용"), ingest_source="t")
    assert db_conn.execute("SELECT posted_on FROM postings").fetchone()["posted_on"] is None


def test_failed_run_leaves_no_partial_rows(db_conn):
    bad = doc(source_job_id="x2", skills="not-a-list-of-dicts", salary=object())
    with pytest.raises(Exception):
        with db_conn.transaction():
            ingest_documents(db_conn, [doc(), bad], ingest_source="t")
    assert count(db_conn, "postings") == 0


def test_delete_ingest_source_keeps_postings_seen_elsewhere(db_conn):
    upsert_posting(db_conn, doc(), ingest_source="backfill:x")
    upsert_posting(db_conn, doc(created_at="2026-11-25T00:00:00+00:00"), ingest_source="daily")
    upsert_posting(db_conn, doc(source_job_id="only-backfill"), ingest_source="backfill:x")
    assert delete_ingest_source(db_conn, "backfill:x") == 1
    assert count(db_conn, "postings") == 1 and count(db_conn, "posting_observations") == 1
