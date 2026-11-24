"""PostgreSQL 연결 풀. 접속 정보는 DATABASE_URL 환경변수로만 받는다."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

CONNECT_TIMEOUT_SECONDS = 3

_pool: ConnectionPool | None = None
_pool_url: str | None = None
_lock = threading.Lock()


class DatabaseUnavailable(RuntimeError):
    """DB 설정이 없거나 접속할 수 없다."""


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise DatabaseUnavailable("DATABASE_URL is not set")
    return url


def _get_pool() -> ConnectionPool:
    global _pool, _pool_url
    url = get_database_url()
    with _lock:
        if _pool is not None and _pool_url != url:
            _pool.close()
            _pool = None
        if _pool is None:
            _pool = ConnectionPool(
                url,
                min_size=1,
                max_size=5,
                open=False,
                timeout=CONNECT_TIMEOUT_SECONDS,
                kwargs={"row_factory": dict_row, "connect_timeout": CONNECT_TIMEOUT_SECONDS},
            )
            _pool_url = url
            try:
                _pool.open()
            except Exception:
                _pool = None
                raise
        return _pool


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """풀에서 연결을 빌린다. 정상 종료 시 commit, 예외 시 rollback."""
    pool = _get_pool()
    try:
        with pool.connection() as conn:
            yield conn
    except (PoolTimeout, psycopg.OperationalError) as exc:
        raise DatabaseUnavailable(f"database unavailable: {exc}") from exc


def reset_pool() -> None:
    global _pool, _pool_url
    with _lock:
        if _pool is not None:
            _pool.close()
        _pool = None
        _pool_url = None
