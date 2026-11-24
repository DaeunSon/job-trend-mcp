import os

import psycopg
import pytest

from src.db.connection import DatabaseUnavailable, connection, reset_pool


def test_body_operational_error_propagates_as_itself():
    reset_pool()
    try:
        with pytest.raises(psycopg.errors.QueryCanceled):
            with connection() as conn:
                conn.execute("SET statement_timeout = 10")
                conn.execute("SELECT pg_sleep(1)")
    finally:
        reset_pool()


def test_unreachable_database_raises_unavailable(monkeypatch):
    reset_pool()
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none_test")
    try:
        with pytest.raises(DatabaseUnavailable):
            with connection():
                pass
    finally:
        reset_pool()
        monkeypatch.undo()
        os.environ.get("DATABASE_URL")
