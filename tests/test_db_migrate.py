import psycopg
import pytest

from src.db.connection import DatabaseUnavailable, get_database_url
from src.db.migrate import apply_migrations
from tests import conftest


def test_apply_creates_tables(db_conn):
    names = {r["table_name"] for r in db_conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert {"postings", "posting_skills", "posting_observations", "schema_migrations"} <= names


def test_apply_twice_applies_nothing(db_conn):
    assert apply_migrations(db_conn) == []


def test_unique_posting_key(db_conn):
    insert = ("INSERT INTO postings (source_name, source_job_id, ingest_source, doc) "
              "VALUES ('jumpit', '1', 't', '{}')")
    db_conn.execute(insert)
    with pytest.raises(psycopg.errors.UniqueViolation):
        db_conn.execute(insert)


def test_refuses_non_test_database(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:p@127.0.0.1:54329/jobtrend")
    with pytest.raises(RuntimeError, match="_test"):
        conftest.resolve_test_database_url()


def test_get_database_url_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(DatabaseUnavailable, match="DATABASE_URL is not set"):
        get_database_url()
