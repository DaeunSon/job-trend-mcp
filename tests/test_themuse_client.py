"""
crawlers/themuse/client.py 유닛 테스트.
네트워크 호출은 unittest.mock으로 패치한다.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.crawlers.themuse.client import (
    _call_api,
    _parse_int_header,
    fetch_themuse,
    run_themuse_batch,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처 / 헬퍼
# ---------------------------------------------------------------------------

def _make_job(job_id: int = 101, title: str = "Senior Backend Engineer") -> dict:
    return {
        "id": job_id,
        "name": title,
        "contents": "<p>We need a <strong>Python</strong> developer with 5+ years.</p>",
        "type": "external",
        "publication_date": "2026-07-29T10:00:00Z",
        "short_name": f"senior-backend-engineer-{job_id}",
        "model_type": "jobs",
        "locations": [{"name": "New York, NY"}],
        "categories": [{"name": "Software Engineering"}],
        "levels": [{"name": "Senior Level", "short_name": "senior"}],
        "tags": ["python", "backend"],
        "refs": {"landing_page": f"https://www.themuse.com/jobs/acme/senior-backend-{job_id}"},
        "company": {"id": 9999, "short_name": "acme", "name": "Acme Corp"},
    }


def _make_api_response(
    jobs: list[dict] | None = None,
    page: int = 1,
    page_count: int = 1,
    total: int | None = None,
) -> dict:
    jobs = jobs or [_make_job()]
    return {
        "page": page,
        "page_count": page_count,
        "items_per_page": 20,
        "took": 10,
        "timed_out": False,
        "total": total if total is not None else len(jobs),
        "results": jobs,
        "aggregations": {},
    }


def _mock_response(
    data: dict,
    status_code: int = 200,
    rate_remaining: int = 499,
    rate_reset: int = 3600,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    resp.headers = {
        "X-Ratelimit-Remaining": str(rate_remaining),
        "X-Ratelimit-Limit": "500",
        "X-Ratelimit-Reset": str(rate_reset),
    }
    return resp


# ---------------------------------------------------------------------------
# _parse_int_header
# ---------------------------------------------------------------------------

class TestParseIntHeader:
    def test_valid_header(self):
        resp = MagicMock()
        resp.headers = {"X-Ratelimit-Remaining": "123"}
        assert _parse_int_header(resp, "X-Ratelimit-Remaining") == 123

    def test_missing_header_returns_none(self):
        resp = MagicMock()
        resp.headers = {}
        assert _parse_int_header(resp, "X-Ratelimit-Remaining") is None

    def test_non_numeric_header_returns_none(self):
        resp = MagicMock()
        resp.headers = {"X-Ratelimit-Remaining": "unlimited"}
        assert _parse_int_header(resp, "X-Ratelimit-Remaining") is None


# ---------------------------------------------------------------------------
# _call_api
# ---------------------------------------------------------------------------

class TestCallApi:
    def test_success_returns_data_and_rate_headers(self):
        expected = _make_api_response()
        mock_resp = _mock_response(expected, rate_remaining=450, rate_reset=3600)
        with patch("requests.get", return_value=mock_resp):
            data, remaining, reset = _call_api({"page": 1})

        assert data == expected
        assert remaining == 450
        assert reset == 3600

    def test_returns_none_on_http_error(self):
        import requests as req
        err_resp = MagicMock()
        err_resp.status_code = 503
        err_resp.headers = {}
        with patch(
            "requests.get",
            side_effect=req.exceptions.HTTPError(response=err_resp),
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            data, remaining, reset = _call_api({"page": 1})

        assert data is None
        assert remaining is None
        assert reset is None

    def test_returns_none_on_network_error(self):
        import requests as req
        with patch(
            "requests.get",
            side_effect=req.exceptions.ConnectionError("timeout"),
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            data, remaining, reset = _call_api({"page": 1})

        assert data is None

    def test_passes_page_param(self):
        mock_resp = _mock_response(_make_api_response())
        with patch("requests.get", return_value=mock_resp) as mock_get:
            _call_api({"page": 3, "category": "Software Engineering"})

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["page"] == 3
        assert kwargs["params"]["category"] == "Software Engineering"

    def test_429_sleeps_for_reset_duration(self):
        import requests as req
        err_resp = MagicMock()
        err_resp.status_code = 429
        err_resp.headers = {"X-Ratelimit-Reset": "120"}

        sleep_calls = []
        ok_resp = _mock_response(_make_api_response())

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise req.exceptions.HTTPError(response=err_resp)
            return ok_resp

        with patch("requests.get", side_effect=side_effect), patch(
            "src.crawlers.common.api_client_base.time.sleep",
            side_effect=lambda s: sleep_calls.append(s),
        ):
            data, _, _ = _call_api({"page": 1})

        assert any(s >= 60 for s in sleep_calls), f"sleep calls: {sleep_calls}"


# ---------------------------------------------------------------------------
# fetch_themuse
# ---------------------------------------------------------------------------

class TestFetchThemuse:
    def test_saves_raw_job_postings(self, tmp_path):
        api_data = _make_api_response([_make_job(1), _make_job(2)])
        mock_resp = _mock_response(api_data)
        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ) as mock_save:
            fetch_themuse(
                category="Software Engineering",
                crawl_date="2026-07-29",
                save_path=str(tmp_path),
                page_count=1,
            )

        mock_save.assert_called_once()
        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 2

    def test_skips_already_saved_ids(self):
        api_data = _make_api_response([_make_job(1), _make_job(2)])
        saved = {("themuse", "1")}

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=saved
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ) as mock_save:
            fetch_themuse(category="Software Engineering", page_count=1)

        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 1
        assert saved_docs[0]["source_job_id"] == "2"

    def test_returns_empty_string_when_no_new_jobs(self):
        api_data = _make_api_response([_make_job(1)])
        saved = {("themuse", "1")}

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=saved
        ):
            result = fetch_themuse(category="Software Engineering", page_count=1)

        assert result == ""

    def test_returns_empty_string_on_api_failure(self):
        with patch(
            "src.crawlers.themuse.client._call_api", return_value=(None, None, None)
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ):
            result = fetch_themuse(category="Software Engineering", page_count=1)

        assert result == ""

    def test_raw_html_is_empty_string(self):
        api_data = _make_api_response([_make_job(1)])

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ) as mock_save:
            fetch_themuse(category="Software Engineering", page_count=1)

        doc = mock_save.call_args[1]["documents"][0]
        assert doc["raw_html"] == ""

    def test_raw_text_is_valid_json_with_original_fields(self):
        job = _make_job(99)
        api_data = _make_api_response([job])

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ) as mock_save:
            fetch_themuse(category="Software Engineering", page_count=1)

        doc = mock_save.call_args[1]["documents"][0]
        parsed = json.loads(doc["raw_text"])
        assert parsed["id"] == 99
        assert parsed["name"] == job["name"]
        assert "contents" in parsed

    def test_source_name_is_themuse(self):
        api_data = _make_api_response([_make_job(1)])

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ) as mock_save:
            fetch_themuse(category="Software Engineering", page_count=1)

        doc = mock_save.call_args[1]["documents"][0]
        assert doc["source_name"] == "themuse"

    def test_parse_status_is_pending(self):
        api_data = _make_api_response([_make_job(1)])

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ) as mock_save:
            fetch_themuse(category="Software Engineering", page_count=1)

        doc = mock_save.call_args[1]["documents"][0]
        assert doc["parse_status"] == "PENDING"

    def test_original_url_uses_refs_landing_page(self):
        job = _make_job(55)
        api_data = _make_api_response([job])

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ) as mock_save:
            fetch_themuse(category="Software Engineering", page_count=1)

        doc = mock_save.call_args[1]["documents"][0]
        assert doc["original_url"] == job["refs"]["landing_page"]

    def test_filename_uses_category(self):
        api_data = _make_api_response([_make_job(1)])

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 490, 3600),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ) as mock_save:
            fetch_themuse(category="Software Engineering", page_count=1)

        assert mock_save.call_args[1]["filename"] == "themuse_Software_Engineering"

    def test_stops_at_api_page_count(self):
        """API page_count보다 많은 page_count를 지정해도 실제 API 페이지 수에서 멈춘다."""
        api_data_p1 = _make_api_response(
            [_make_job(1)], page=1, page_count=2, total=2
        )
        api_data_p2 = _make_api_response(
            [_make_job(2)], page=2, page_count=2, total=2
        )
        call_num = 0

        def mock_call(params):
            nonlocal call_num
            call_num += 1
            if params["page"] == 1:
                return api_data_p1, 490, 3600
            if params["page"] == 2:
                return api_data_p2, 489, 3600
            return None, None, None

        with patch(
            "src.crawlers.themuse.client._call_api", side_effect=mock_call
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            fetch_themuse(category="Software Engineering", page_count=10)

        assert call_num == 2

    def test_waits_when_rate_limit_low(self):
        """X-Ratelimit-Remaining ≤ 50 이면 대기한다."""
        api_data = _make_api_response([_make_job(1)], page_count=1)
        sleep_calls = []

        with patch(
            "src.crawlers.themuse.client._call_api",
            return_value=(api_data, 30, 120),
        ), patch(
            "src.crawlers.themuse.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.themuse.client.save_documents"
        ), patch(
            "src.crawlers.common.api_client_base.time.sleep",
            side_effect=lambda s: sleep_calls.append(s),
        ):
            fetch_themuse(category="Software Engineering", page_count=1)

        assert any(s >= 60 for s in sleep_calls), f"sleep calls: {sleep_calls}"


# ---------------------------------------------------------------------------
# run_themuse_batch
# ---------------------------------------------------------------------------

class TestRunThemmuseBatch:
    def test_calls_fetch_for_each_category(self):
        categories = ["Software Engineering", "Data and Analytics", "Product Management"]

        with patch(
            "src.crawlers.themuse.client.fetch_themuse", return_value="some/path"
        ) as mock_fetch:
            run_themuse_batch(categories=categories, crawl_date="2026-07-29")

        assert mock_fetch.call_count == 3
        called_cats = [c[1]["category"] for c in mock_fetch.call_args_list]
        assert called_cats == categories

    def test_continues_on_partial_failure(self):
        """한 카테고리 실패해도 나머지 계속 진행."""
        categories = ["Software Engineering", "Data and Analytics", "Product Management"]
        call_count = 0

        def flaky_fetch(category, **_):
            nonlocal call_count
            call_count += 1
            if category == "Data and Analytics":
                raise RuntimeError("network error")
            return "ok"

        with patch("src.crawlers.themuse.client.fetch_themuse", side_effect=flaky_fetch):
            run_themuse_batch(categories=categories)

        assert call_count == 3

    def test_uses_default_categories_when_none(self):
        from src.crawlers.themuse.search_queries import DEFAULT_BATCH_CATEGORIES

        with patch(
            "src.crawlers.themuse.client.fetch_themuse", return_value=""
        ) as mock_fetch:
            run_themuse_batch(categories=None)

        assert mock_fetch.call_count == len(DEFAULT_BATCH_CATEGORIES)

    def test_passes_page_count_to_fetch(self):
        categories = ["Software Engineering", "Data and Analytics"]

        with patch(
            "src.crawlers.themuse.client.fetch_themuse", return_value=""
        ) as mock_fetch:
            run_themuse_batch(categories=categories, page_count=3)

        for call in mock_fetch.call_args_list:
            assert call[1]["page_count"] == 3

    def test_passes_api_key_to_fetch(self):
        categories = ["Software Engineering"]

        with patch(
            "src.crawlers.themuse.client.fetch_themuse", return_value=""
        ) as mock_fetch:
            run_themuse_batch(categories=categories, api_key="test-key-123")

        assert mock_fetch.call_args[1]["api_key"] == "test-key-123"
