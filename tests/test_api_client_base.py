"""crawlers/common/api_client_base · html_description_to_text 유닛 테스트."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import requests

from src.crawlers.common.api_client_base import (
    ApiClientBase,
    ApiCallResult,
    RateLimitPolicy,
    parse_int_header,
)
from src.crawlers.common.http_utils import html_description_to_text


class _StubClient(ApiClientBase):
    source_name = "stub"
    base_url = "https://example.com"
    api_path = "/api/jobs"
    rate_limit = RateLimitPolicy(
        min_interval_seconds=0.0,
        max_retries=3,
        backoff_base=2.0,
        status_backoff_multipliers={429: 3.0},
    )

    def extract_jobs(self, page_data: dict[str, Any]) -> list[dict[str, Any]]:
        return list(page_data.get("jobs") or [])

    def extract_job_id(self, job: dict[str, Any]) -> str:
        return str(job.get("id") or "")

    def extract_original_url(self, job: dict[str, Any], source_job_id: str) -> str:
        return job.get("url") or f"https://example.com/jobs/{source_job_id}"


def _mock_resp(data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    resp.headers = {}
    return resp


class TestParseIntHeader:
    def test_ok(self):
        resp = MagicMock()
        resp.headers = {"X-Ratelimit-Remaining": "42"}
        assert parse_int_header(resp, "X-Ratelimit-Remaining") == 42

    def test_missing(self):
        resp = MagicMock()
        resp.headers = {}
        assert parse_int_header(resp, "X-Ratelimit-Remaining") is None


class TestCallApi:
    def test_success(self):
        client = _StubClient()
        payload = {"jobs": [{"id": 1}]}
        with patch("requests.get", return_value=_mock_resp(payload)) as mock_get:
            result = client.call_api({"page": 1})
        assert isinstance(result, ApiCallResult)
        assert result.data == payload
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {"page": 1}
        assert kwargs["timeout"] == client.timeout

    def test_retries_then_none(self):
        client = _StubClient()
        with patch(
            "requests.get",
            side_effect=requests.exceptions.ConnectionError("boom"),
        ), patch("src.crawlers.common.api_client_base.time.sleep") as mock_sleep:
            result = client.call_api({})
        assert result.data is None
        assert mock_sleep.call_count == 2  # retries 1,2 then fail on 3

    def test_rejects_non_dict_json(self):
        client = _StubClient()
        resp = _mock_resp({})
        resp.json.return_value = [1, 2, 3]
        with patch("requests.get", return_value=resp), patch(
            "src.crawlers.common.api_client_base.time.sleep"
        ):
            result = client.call_api({})
        assert result.data is None


class TestJobsToRawDicts:
    def test_dedup_and_max_jobs(self):
        client = _StubClient()
        jobs = [
            {"id": 1, "url": "https://example.com/1"},
            {"id": 2, "url": "https://example.com/2"},
            {"id": 3, "url": "https://example.com/3"},
        ]
        saved = {("stub", "1")}
        docs, skipped = client.jobs_to_raw_dicts(jobs, saved, max_jobs=1)
        assert skipped == 1
        assert len(docs) == 1
        assert docs[0]["source_job_id"] == "2"
        assert docs[0]["source_name"] == "stub"
        assert docs[0]["raw_html"] == ""
        assert '"id": 2' in docs[0]["raw_text"] or '"id":2' in docs[0]["raw_text"]


class TestRateLimitPolicyInjection:
    def test_site_intervals_differ(self):
        from src.crawlers.arbeitnow.client import ArbeitnowApiClient
        from src.crawlers.remotive.client import RemotiveApiClient
        from src.crawlers.themuse.client import ThemuseApiClient

        assert ThemuseApiClient.rate_limit.min_interval_seconds == 1.0
        assert RemotiveApiClient.rate_limit.min_interval_seconds == 35
        assert ArbeitnowApiClient.rate_limit.min_interval_seconds == 20
        # 공통 클래스에 하드코딩되지 않음
        assert ThemuseApiClient.rate_limit.min_interval_seconds != (
            RemotiveApiClient.rate_limit.min_interval_seconds
        )


class TestHtmlDescriptionToText:
    def test_strips_tags(self):
        text = html_description_to_text("<p>Hello <strong>World</strong></p>")
        assert "Hello" in text
        assert "World" in text
        assert "<" not in text

    def test_unescape_entities(self):
        text = html_description_to_text(
            "&lt;p&gt;Python&lt;/p&gt;",
            unescape_entities=True,
        )
        assert "Python" in text
        assert "&lt;" not in text

    def test_empty(self):
        assert html_description_to_text("") == ""
        assert html_description_to_text(None or "") == ""
