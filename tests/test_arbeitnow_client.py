"""
crawlers/arbeitnow/client.py 유닛 테스트.
네트워크 호출은 unittest.mock으로 패치한다.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.crawlers.arbeitnow.client import (
    _call_api,
    _fetch_page,
    fetch_arbeitnow,
    run_arbeitnow_batch,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처 / 헬퍼
# ---------------------------------------------------------------------------

def _make_job(
    slug: str = "backend-engineer-101",
    title: str = "Backend Engineer",
) -> dict:
    return {
        "slug": slug,
        "company_name": "Acme Corp",
        "title": title,
        "description": "&lt;p&gt;We need a &lt;strong&gt;Python&lt;/strong&gt; developer.&lt;/p&gt;",
        "remote": True,
        "url": f"https://www.arbeitnow.com/jobs/companies/acme/{slug}",
        "tags": ["Engineering", "python"],
        "job_types": ["Full time"],
        "location": "Berlin",
        "created_at": 1785391025,
    }


def _make_api_response(
    jobs: list[dict] | None = None,
    page: int = 1,
    has_next: bool = False,
) -> dict:
    if jobs is None:
        jobs = [_make_job()]
    next_url = (
        f"https://www.arbeitnow.com/api/job-board-api?page={page + 1}"
        if has_next else None
    )
    return {
        "data": jobs,
        "links": {
            "first": "https://www.arbeitnow.com/api/job-board-api?page=1",
            "last": None,
            "prev": None if page == 1 else f"https://www.arbeitnow.com/api/job-board-api?page={page - 1}",
            "next": next_url,
        },
        "meta": {
            "current_page": page,
            "per_page": 100,
            "terms": "This is a free public API for jobs, please do not abuse.",
            "info": "Use ?page= to paginate.",
        },
    }


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _call_api
# ---------------------------------------------------------------------------

class TestCallApi:
    def test_success_returns_dict(self):
        expected = _make_api_response()
        with patch("requests.get", return_value=_mock_response(expected)):
            result = _call_api({"page": 1})

        assert result == expected

    def test_returns_none_on_http_error(self):
        import requests as req
        err_resp = MagicMock()
        err_resp.status_code = 503
        with patch(
            "requests.get",
            side_effect=req.exceptions.HTTPError(response=err_resp),
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            result = _call_api({"page": 1})

        assert result is None

    def test_returns_none_on_network_error(self):
        import requests as req
        with patch(
            "requests.get",
            side_effect=req.exceptions.ConnectionError("timeout"),
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            result = _call_api({"page": 1})

        assert result is None

    def test_returns_none_on_invalid_json(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError("not json")
        with patch("requests.get", return_value=resp), patch(
            "src.crawlers.common.api_client_base.time.sleep"
        ):
            result = _call_api({"page": 1})

        assert result is None

    def test_passes_page_param(self):
        mock_resp = _mock_response(_make_api_response())
        with patch("requests.get", return_value=mock_resp) as mock_get:
            _call_api({"page": 3})

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["page"] == 3
        assert kwargs["allow_redirects"] is True


# ---------------------------------------------------------------------------
# fetch_arbeitnow / _fetch_page
# ---------------------------------------------------------------------------

class TestFetchArbeitnow:
    def test_saves_raw_job_postings(self, tmp_path):
        api_data = _make_api_response([_make_job("a-1"), _make_job("a-2")])
        with patch(
            "src.crawlers.arbeitnow.client._call_api", return_value=api_data,
        ), patch(
            "src.crawlers.arbeitnow.client.get_saved_ids", return_value=set(),
        ), patch(
            "src.crawlers.arbeitnow.client.save_documents"
        ) as mock_save:
            mock_save.return_value = tmp_path / "arbeitnow_page_1.json"
            path = fetch_arbeitnow(page=1, crawl_date="2026-07-30", save_path=str(tmp_path))

        assert path
        mock_save.assert_called_once()
        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 2
        assert saved_docs[0]["source_name"] == "arbeitnow"
        assert saved_docs[0]["source_job_id"] == "a-1"
        assert saved_docs[0]["raw_html"] == ""
        assert saved_docs[0]["parse_status"] == "PENDING"
        job = json.loads(saved_docs[0]["raw_text"])
        assert job["slug"] == "a-1"

    def test_skips_already_saved_ids(self, tmp_path):
        api_data = _make_api_response([_make_job("dup-1"), _make_job("new-2")])
        with patch(
            "src.crawlers.arbeitnow.client._call_api", return_value=api_data,
        ), patch(
            "src.crawlers.arbeitnow.client.get_saved_ids",
            return_value={("arbeitnow", "dup-1")},
        ), patch(
            "src.crawlers.arbeitnow.client.save_documents"
        ) as mock_save:
            mock_save.return_value = tmp_path / "out.json"
            fetch_arbeitnow(page=1, crawl_date="2026-07-30", save_path=str(tmp_path))

        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 1
        assert saved_docs[0]["source_job_id"] == "new-2"

    def test_returns_empty_on_api_failure(self):
        with patch("src.crawlers.arbeitnow.client._call_api", return_value=None):
            path = fetch_arbeitnow(page=1)
        assert path == ""

    def test_returns_empty_on_empty_data(self):
        with patch(
            "src.crawlers.arbeitnow.client._call_api",
            return_value=_make_api_response(jobs=[]),
        ):
            path = fetch_arbeitnow(page=1)
        assert path == ""

    def test_skips_jobs_without_slug(self, tmp_path):
        job = _make_job()
        job["slug"] = ""
        api_data = _make_api_response([job, _make_job("ok-1")])
        with patch(
            "src.crawlers.arbeitnow.client._call_api", return_value=api_data,
        ), patch(
            "src.crawlers.arbeitnow.client.get_saved_ids", return_value=set(),
        ), patch(
            "src.crawlers.arbeitnow.client.save_documents"
        ) as mock_save:
            mock_save.return_value = tmp_path / "out.json"
            fetch_arbeitnow(page=1, crawl_date="2026-07-30")

        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 1
        assert saved_docs[0]["source_job_id"] == "ok-1"

    def test_fetch_page_reports_has_next(self):
        api_data = _make_api_response(has_next=True)
        with patch(
            "src.crawlers.arbeitnow.client._call_api", return_value=api_data,
        ), patch(
            "src.crawlers.arbeitnow.client.get_saved_ids", return_value=set(),
        ), patch(
            "src.crawlers.arbeitnow.client.save_documents", return_value="/tmp/x.json",
        ):
            path, has_next = _fetch_page(page=1, crawl_date="2026-07-30", save_path=None)

        assert path
        assert has_next is True

    def test_fetch_page_reports_no_next(self):
        api_data = _make_api_response(has_next=False)
        with patch(
            "src.crawlers.arbeitnow.client._call_api", return_value=api_data,
        ), patch(
            "src.crawlers.arbeitnow.client.get_saved_ids", return_value=set(),
        ), patch(
            "src.crawlers.arbeitnow.client.save_documents", return_value="/tmp/x.json",
        ):
            _path, has_next = _fetch_page(page=1, crawl_date="2026-07-30", save_path=None)

        assert has_next is False

    def test_filename_includes_page_number(self, tmp_path):
        with patch(
            "src.crawlers.arbeitnow.client._call_api",
            return_value=_make_api_response(),
        ), patch(
            "src.crawlers.arbeitnow.client.get_saved_ids", return_value=set(),
        ), patch(
            "src.crawlers.arbeitnow.client.save_documents"
        ) as mock_save:
            mock_save.return_value = tmp_path / "out.json"
            fetch_arbeitnow(page=5, crawl_date="2026-07-30")

        assert mock_save.call_args[1]["filename"] == "arbeitnow_page_5"


# ---------------------------------------------------------------------------
# run_arbeitnow_batch
# ---------------------------------------------------------------------------

class TestRunArbeitnowBatch:
    def test_stops_when_no_next(self):
        calls = []

        def fake_fetch(**kwargs):
            calls.append(kwargs["page"])
            return "/tmp/x.json", False

        with patch(
            "src.crawlers.arbeitnow.client._fetch_page", side_effect=fake_fetch,
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            run_arbeitnow_batch(max_pages=10)

        assert calls == [1]

    def test_paginates_until_max_pages(self):
        calls = []

        def fake_fetch(**kwargs):
            calls.append(kwargs["page"])
            return "/tmp/x.json", True

        with patch(
            "src.crawlers.arbeitnow.client._fetch_page", side_effect=fake_fetch,
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            run_arbeitnow_batch(max_pages=3)

        assert calls == [1, 2, 3]

    def test_continues_after_single_failure(self):
        calls = []

        def fake_fetch(**kwargs):
            page = kwargs["page"]
            calls.append(page)
            if page == 1:
                return "", None  # API 실패
            return "/tmp/x.json", False

        with patch(
            "src.crawlers.arbeitnow.client._fetch_page", side_effect=fake_fetch,
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            run_arbeitnow_batch(max_pages=5)

        assert calls == [1, 2]

    def test_stops_after_consecutive_failures(self):
        calls = []

        def fake_fetch(**kwargs):
            calls.append(kwargs["page"])
            return "", None

        with patch(
            "src.crawlers.arbeitnow.client._fetch_page", side_effect=fake_fetch,
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            run_arbeitnow_batch(max_pages=10)

        assert calls == [1, 2, 3]
