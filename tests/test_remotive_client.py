"""
crawlers/remotive/client.py 유닛 테스트.
네트워크 호출은 unittest.mock으로 패치한다.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.crawlers.remotive.client import (
    _call_api,
    fetch_remotive,
    run_remotive_batch,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처 / 헬퍼
# ---------------------------------------------------------------------------

def _make_job(job_id: int = 101, title: str = "Backend Developer") -> dict:
    return {
        "id": job_id,
        "url": f"https://remotive.com/remote-jobs/software-development/backend-{job_id}",
        "title": title,
        "company_name": "Acme Corp",
        "company_logo": "",
        "category": "Software Development",
        "job_type": "full_time",
        "publication_date": "2026-07-27T09:00:00",
        "candidate_required_location": "Worldwide",
        "salary": "$80,000 - $100,000",
        "description": "<p>We need a Python developer.</p>",
        "tags": ["python", "backend"],
    }


def _make_api_response(jobs: list[dict] | None = None) -> dict:
    jobs = jobs or [_make_job()]
    return {"job-count": len(jobs), "jobs": jobs}


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
        with patch("requests.get", return_value=_mock_response(expected)) as mock_get:
            result = _call_api({"category": "software-development"})

        assert result == expected
        mock_get.assert_called_once()

    def test_returns_none_on_http_error(self):
        err_resp = MagicMock()
        err_resp.status_code = 503
        import requests
        with patch(
            "requests.get",
            side_effect=requests.exceptions.HTTPError(response=err_resp),
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            result = _call_api({})

        assert result is None

    def test_returns_none_on_network_error(self):
        import requests
        with patch(
            "requests.get",
            side_effect=requests.exceptions.ConnectionError("timeout"),
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            result = _call_api({})

        assert result is None

    def test_no_params_calls_base_url(self):
        with patch("requests.get", return_value=_mock_response(_make_api_response())) as mock_get:
            _call_api({})

        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["params"] is None or call_kwargs[1]["params"] == {}

    def test_passes_category_param(self):
        with patch("requests.get", return_value=_mock_response(_make_api_response())) as mock_get:
            _call_api({"category": "devops"})

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["category"] == "devops"


# ---------------------------------------------------------------------------
# fetch_remotive
# ---------------------------------------------------------------------------

class TestFetchRemotive:
    def test_saves_raw_job_postings(self, tmp_path):
        api_data = _make_api_response([_make_job(1), _make_job(2)])
        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(
                category="software-development",
                crawl_date="2026-07-27",
                save_path=str(tmp_path),
            )

        mock_save.assert_called_once()
        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 2

    def test_skips_already_saved_ids(self):
        api_data = _make_api_response([_make_job(1), _make_job(2)])
        saved = {("remotive", "1")}

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=saved
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="software-development")

        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 1
        assert saved_docs[0]["source_job_id"] == "2"

    def test_returns_empty_string_when_no_new_jobs(self):
        api_data = _make_api_response([_make_job(1)])
        saved = {("remotive", "1")}

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=saved
        ):
            result = fetch_remotive(category="software-development")

        assert result == ""

    def test_returns_empty_string_on_api_failure(self):
        with patch("src.crawlers.remotive.client._call_api", return_value=None):
            result = fetch_remotive(category="software-development")

        assert result == ""

    def test_raw_text_is_json_string(self):
        job = _make_job(99)
        api_data = _make_api_response([job])

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="software-development")

        doc = mock_save.call_args[1]["documents"][0]
        parsed = json.loads(doc["raw_text"])
        assert parsed["id"] == 99
        assert parsed["title"] == job["title"]

    def test_raw_html_is_empty_string(self):
        api_data = _make_api_response([_make_job(1)])

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="software-development")

        doc = mock_save.call_args[1]["documents"][0]
        assert doc["raw_html"] == ""

    def test_source_name_is_remotive(self):
        api_data = _make_api_response([_make_job(1)])

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="software-development")

        doc = mock_save.call_args[1]["documents"][0]
        assert doc["source_name"] == "remotive"

    def test_parse_status_is_pending(self):
        api_data = _make_api_response([_make_job(1)])

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="software-development")

        doc = mock_save.call_args[1]["documents"][0]
        assert doc["parse_status"] == "PENDING"

    def test_filename_uses_category(self):
        api_data = _make_api_response([_make_job(1)])

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="devops")

        assert mock_save.call_args[1]["filename"] == "remotive_devops"

    def test_max_jobs_limits_saved_count(self):
        jobs = [_make_job(i) for i in range(1, 11)]  # 10건
        api_data = _make_api_response(jobs)

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="software-development", max_jobs=3)

        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 3

    def test_max_jobs_none_saves_all(self):
        jobs = [_make_job(i) for i in range(1, 6)]  # 5건
        api_data = _make_api_response(jobs)

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=set()
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="software-development", max_jobs=None)

        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 5

    def test_max_jobs_applied_after_dedup(self):
        """중복 제거 후 신규 건수 기준으로 max_jobs가 적용되어야 한다."""
        jobs = [_make_job(i) for i in range(1, 11)]  # 10건
        api_data = _make_api_response(jobs)
        # id 1~5는 이미 저장됨
        saved = {("remotive", str(i)) for i in range(1, 6)}

        with patch(
            "src.crawlers.remotive.client._call_api", return_value=api_data
        ), patch(
            "src.crawlers.remotive.client.get_saved_ids", return_value=saved
        ), patch(
            "src.crawlers.remotive.client.save_documents"
        ) as mock_save:
            fetch_remotive(category="software-development", max_jobs=3)

        # 신규 가능한 건(6~10, 5건) 중 max_jobs=3만 저장
        saved_docs = mock_save.call_args[1]["documents"]
        assert len(saved_docs) == 3
        saved_ids = {d["source_job_id"] for d in saved_docs}
        # 저장된 것은 신규(6~10) 중 앞 3개
        assert saved_ids == {"6", "7", "8"}


# ---------------------------------------------------------------------------
# run_remotive_batch
# ---------------------------------------------------------------------------

class TestRunRemotiveBatch:
    def test_calls_fetch_for_each_category(self):
        categories = ["software-development", "devops", "data"]

        with patch(
            "src.crawlers.remotive.client.fetch_remotive", return_value="some/path"
        ) as mock_fetch, patch(
            "src.crawlers.common.api_client_base.time.sleep"
        ):
            run_remotive_batch(categories=categories, crawl_date="2026-07-27")

        assert mock_fetch.call_count == 3
        called_cats = [c[1]["category"] for c in mock_fetch.call_args_list]
        assert called_cats == categories

    def test_sleeps_between_categories(self):
        """분당 2회 제한 준수 — 카테고리 간 sleep이 호출되어야 한다."""
        categories = ["software-development", "devops"]
        sleep_calls = []

        with patch(
            "src.crawlers.remotive.client.fetch_remotive", return_value=""
        ), patch(
            "src.crawlers.common.api_client_base.time.sleep",
            side_effect=lambda s: sleep_calls.append(s),
        ):
            run_remotive_batch(categories=categories)

        # 2개 카테고리 → sleep 1회 (마지막 카테고리 후에는 sleep 없음)
        assert len(sleep_calls) == 1
        assert sleep_calls[0] >= 30

    def test_no_sleep_for_single_category(self):
        sleep_calls = []
        with patch(
            "src.crawlers.remotive.client.fetch_remotive", return_value=""
        ), patch(
            "src.crawlers.common.api_client_base.time.sleep",
            side_effect=lambda s: sleep_calls.append(s),
        ):
            run_remotive_batch(categories=["software-development"])

        assert len(sleep_calls) == 0

    def test_continues_on_partial_failure(self):
        """한 카테고리 실패해도 나머지 계속 진행."""
        categories = ["software-development", "devops", "data"]
        call_count = 0

        def flaky_fetch(category, **_):
            nonlocal call_count
            call_count += 1
            if category == "devops":
                raise RuntimeError("network error")
            return "ok"

        with patch(
            "src.crawlers.remotive.client.fetch_remotive", side_effect=flaky_fetch
        ), patch("src.crawlers.common.api_client_base.time.sleep"):
            run_remotive_batch(categories=categories)

        assert call_count == 3

    def test_uses_default_categories_when_none(self):
        from src.crawlers.remotive.search_queries import DEFAULT_BATCH_CATEGORIES

        with patch(
            "src.crawlers.remotive.client.fetch_remotive", return_value=""
        ) as mock_fetch, patch("src.crawlers.common.api_client_base.time.sleep"):
            run_remotive_batch(categories=None)

        assert mock_fetch.call_count == len(DEFAULT_BATCH_CATEGORIES)

    def test_passes_max_jobs_to_fetch(self):
        categories = ["software-development", "devops"]

        with patch(
            "src.crawlers.remotive.client.fetch_remotive", return_value=""
        ) as mock_fetch, patch("src.crawlers.common.api_client_base.time.sleep"):
            run_remotive_batch(categories=categories, max_jobs=50)

        for call in mock_fetch.call_args_list:
            assert call[1]["max_jobs"] == 50

    def test_max_jobs_none_passes_through(self):
        categories = ["software-development"]

        with patch(
            "src.crawlers.remotive.client.fetch_remotive", return_value=""
        ) as mock_fetch, patch("src.crawlers.common.api_client_base.time.sleep"):
            run_remotive_batch(categories=categories, max_jobs=None)

        assert mock_fetch.call_args[1]["max_jobs"] is None
