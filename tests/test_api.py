"""검색 REST API 테스트."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import app, get_conn
from src.db.connection import reset_pool
from src.db.ingest import ingest_documents
from tests.conftest import SAMPLE_DOCS


@pytest.fixture
def seeded(db_conn):
    ingest_documents(db_conn, SAMPLE_DOCS, ingest_source="t")
    return db_conn


@pytest.fixture
def client(seeded):
    app.dependency_overrides[get_conn] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok", "postings": 5}


def test_search_filters_and_paginates(client):
    body = client.get("/api/v1/postings", params={"job_function": "백엔드", "limit": 1}).json()
    assert (body["total"], body["limit"], body["offset"], len(body["items"])) == (2, 1, 0, 1)
    page2 = client.get("/api/v1/postings",
                       params={"job_function": "백엔드", "limit": 1, "offset": 1}).json()
    assert page2["items"][0]["original_url"] != body["items"][0]["original_url"]


def test_items_are_summaries_without_description(client):
    item = client.get("/api/v1/postings").json()["items"][0]
    assert set(item) == {"title", "company", "location", "employment_type", "work_arrangement",
                         "job_function", "job_category", "posted_at", "original_url", "source_name"}


def test_note_present(client):
    assert client.get("/api/v1/postings").json()["note"] == (
        "Collected sample from capped daily crawls; not a full census.")


def test_keyword_skill_and_date_filters(client):
    get = lambda **p: client.get("/api/v1/postings", params=p).json()["total"]
    assert get(q="frontend") == 1 and get(q="ACME") == 3
    assert get(skill="kubernetes") == 1 and get(posted_from="2026-08-02") == 2


def test_keyword_special_chars_are_literal(client):
    for q in ["%%", "__", "a'; DROP TABLE postings;--"]:
        r = client.get("/api/v1/postings", params={"q": q})
        assert r.status_code == 200 and r.json()["total"] == 0
    assert client.get("/healthz").json()["postings"] == 5


def test_empty_result_is_200(client):
    r = client.get("/api/v1/postings", params={"location": "제주"})
    assert r.status_code == 200 and r.json()["items"] == []


@pytest.mark.parametrize("param, value", [("job_function", "zz-not-a-role"), ("source_name", "linkedin"),
                                          ("job_category", "zz"), ("skill", "zz-not-a-skill")])
def test_unknown_filter_value_is_400(client, param, value):
    r = client.get("/api/v1/postings", params={param: value})
    assert r.status_code == 400 and r.json()["param"] == param
    assert r.json()["detail"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1},
                                    {"q": "a"}, {"posted_from": "8월"}])
def test_out_of_range_is_422(client, params):
    assert client.get("/api/v1/postings", params=params).status_code == 422


def test_healthz_503_when_db_down(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none_test")
    reset_pool()
    try:
        with TestClient(app) as c:
            assert c.get("/healthz").status_code == 503
            assert c.get("/api/v1/postings").status_code == 503
    finally:
        monkeypatch.undo(); reset_pool()
