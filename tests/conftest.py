"""공용 pytest fixture.

테스트 DB 는 TEST_DATABASE_URL 로만 받고, 이름이 `_test` 로 끝나는 DB 만 허용한다
(개발·운영 DB 를 실수로 비우거나 오염시키지 않기 위해).
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest
from psycopg.rows import dict_row

from src.db.migrate import apply_migrations
from src.mcp_server.data_loader import JobPostingStore, reset_store

_DOCKER_HINT = (
    "docker compose -f docker-compose.dev.yml up -d 로 테스트 DB 를 띄운 뒤 "
    "TEST_DATABASE_URL=postgresql://jobtrend:jobtrend@127.0.0.1:54329/jobtrend_test 를 지정하세요."
)


def resolve_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError(f"TEST_DATABASE_URL is not set. {_DOCKER_HINT}")
    dbname = urlparse(url).path.lstrip("/")
    if not dbname.endswith("_test"):
        raise RuntimeError(
            f"TEST_DATABASE_URL 의 DB 이름은 '_test' 로 끝나야 합니다 (현재: {dbname!r})."
        )
    return url


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    url = resolve_test_database_url()
    os.environ["DATABASE_URL"] = url
    with psycopg.connect(url, connect_timeout=3) as conn:
        apply_migrations(conn)
        conn.commit()
    yield url


@pytest.fixture
def db_conn(_test_database):
    """테스트마다 트랜잭션을 열고 끝나면 rollback 한다."""
    conn = psycopg.connect(_test_database, row_factory=dict_row, connect_timeout=3)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


_SNAPSHOT_AT = "2026-08-01T00:00:00+00:00"

_BASE_DOCS = [
    {
        "id": "1",
        "title": "Backend Engineer A",
        "company": {"name": "Acme", "raw_name": "Acme"},
        "job_function_name": "Backend Engineer",
        "job_category_name": "Engineering & Technology",
        "location": {
            "country_name": "대한민국",
            "city_name": "서울 강남구",
            "region_name": "서울",
            "raw_text": "서울 강남구",
        },
        "employment_type_name": "FULL_TIME",
        "work_arrangement": "HYBRID",
        "skills": [
            {"raw_text": "Python", "canonical_name": "Python", "category_name": None},
            {"raw_text": "Docker", "canonical_name": "Docker", "category_name": None},
        ],
        "salary": {
            "raw_text": "6000-8000",
            "min_amount": "60000000",
            "max_amount": "80000000",
            "currency_code": "KRW",
            "pay_period": "ANNUAL",
        },
        "posted_at": "2026-08-01",
        "original_url": "https://example.com/1",
        "source_name": "jumpit",
        "crawl_status": "ACTIVE",
    },
    {
        "id": "2",
        "title": "Backend Engineer B",
        "company": {"name": "Acme", "raw_name": "Acme Inc"},
        "job_function_name": "Backend Engineer",
        "job_category_name": "Engineering & Technology",
        "location": {
            "country_name": "대한민국",
            "city_name": "부산 해운대구",
            "region_name": "부산",
            "raw_text": "부산",
        },
        "employment_type_name": "FULL_TIME",
        "work_arrangement": "ONSITE",
        "skills": [
            {"raw_text": "Python", "canonical_name": "Python", "category_name": None},
            {"raw_text": "Kubernetes", "canonical_name": "Kubernetes", "category_name": None},
        ],
        "salary": {
            "raw_text": "면접 후 결정",
            "min_amount": None,
            "max_amount": None,
            "currency_code": None,
            "pay_period": None,
        },
        "posted_at": "2026-07-01",
        "original_url": "https://example.com/2",
        "source_name": "jumpit",
        "crawl_status": "ACTIVE",
    },
    {
        "id": "3",
        "title": "Expired Backend",
        "company": {"name": "OldCo", "raw_name": "OldCo"},
        "job_function_name": "Backend Engineer",
        "job_category_name": "Engineering & Technology",
        "location": {
            "country_name": "대한민국",
            "city_name": "서울",
            "region_name": "서울",
            "raw_text": "서울",
        },
        "employment_type_name": "FULL_TIME",
        "work_arrangement": "REMOTE",
        "skills": [
            {"raw_text": "Go", "canonical_name": "Go", "category_name": None},
        ],
        "salary": {
            "min_amount": "90000000",
            "max_amount": "100000000",
            "currency_code": "KRW",
            "pay_period": "ANNUAL",
        },
        "posted_at": "2025-01-01",
        "original_url": "https://example.com/3",
        "source_name": "jumpit",
        "crawl_status": "EXPIRED",
    },
    {
        "id": "4",
        "title": "Data Analyst",
        "company": {"name": "DataCo", "raw_name": "DataCo"},
        "job_function_name": "Data Analyst",
        "job_category_name": "Data & Analytics",
        "location": {
            "country_name": "대한민국",
            "city_name": "서울",
            "region_name": "서울",
            "raw_text": "서울",
        },
        "employment_type_name": "CONTRACT",
        "work_arrangement": "REMOTE",
        "skills": [
            {"raw_text": "SQL", "canonical_name": "SQL", "category_name": None},
        ],
        "salary": {
            "min_amount": "80000",
            "max_amount": "100000",
            "currency_code": "USD",
            "pay_period": "ANNUAL",
        },
        "posted_at": "2026-08-02",
        "original_url": "https://example.com/4",
        "source_name": "wanted",
        "crawl_status": "ACTIVE",
    },
    {
        "id": "5",
        "title": "Acme Frontend",
        "company": {"name": "Acme", "raw_name": "Acme"},
        "job_function_name": "Frontend Engineer",
        "job_category_name": "Engineering & Technology",
        "location": {
            "country_name": "대한민국",
            "city_name": "서울 강남구",
            "region_name": "서울",
            "raw_text": "서울",
        },
        "employment_type_name": "FULL_TIME",
        "work_arrangement": "HYBRID",
        "skills": [],
        "salary": {
            "min_amount": "50000000",
            "max_amount": "70000000",
            "currency_code": "KRW",
            "pay_period": "ANNUAL",
        },
        "posted_at": "2026-08-03",
        "original_url": "https://example.com/5",
        "source_name": "jumpit",
        "crawl_status": "ACTIVE",
    },
]

SAMPLE_DOCS = [
    {
        **doc,
        "source_job_id": doc["id"],
        "created_at": _SNAPSHOT_AT,
        "first_collected_at": _SNAPSHOT_AT,
        "last_seen_at": _SNAPSHOT_AT,
    }
    for doc in _BASE_DOCS
]


def doc(**over):
    """SAMPLE_DOCS[0] 을 깊은 복사해 필드를 덮어쓴다."""
    d = copy.deepcopy(SAMPLE_DOCS[0])
    d.update(over)
    return d


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


@pytest.fixture
def sample_store(tmp_path: Path) -> JobPostingStore:
    """작은 fixture 데이터셋으로 스토어를 구성한다."""
    reset_store()
    root = tmp_path
    for i, doc in enumerate(SAMPLE_DOCS, start=1):
        path = root / "job_postings" / doc["job_function_name"] / doc["source_name"]
        path.mkdir(parents=True, exist_ok=True)
        (path / f"2026-08-01_{i}.json").write_text(
            json.dumps(doc, ensure_ascii=False),
            encoding="utf-8",
        )

    store = JobPostingStore().load(root)
    return store
