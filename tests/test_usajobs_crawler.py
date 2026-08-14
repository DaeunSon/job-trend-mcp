"""
crawlers/usajobs/crawler.py 유닛 테스트.

네트워크 호출은 mock. 세션 쿠키 유지·고정 User-Agent를 명시적으로 검증한다.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from src.config.sources import USAJOBS_SOURCE, USAJOBS_USER_AGENT
from src.crawlers.usajobs.crawler import (
    _RESULTS_URL,
    _SEARCH_URL,
    _SOURCE_NAME,
    _USER_AGENT,
    _USAJobsCrawler,
    _has_next_page,
    _is_blocked,
    _resolve_keywords,
    crawl_usajobs,
    run_usajobs_batch,
)


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

def _make_job(doc_id: int = 878397800, title: str = "Software Engineer") -> dict:
    return {
        "DocumentID": doc_id,
        "Title": title,
        "Agency": "Social Security Administration",
        "Department": "Other Agencies and Independent Organizations",
        "PositionURI": f"https://www.usajobs.gov:443/job/{doc_id}",
        "SalaryDisplay": "Starting at $111,147 Per year (GS 13)",
        "WorkType": "Permanent",
        "WorkSchedule": "Full-time",
        "LocationName": "Woodlawn, Maryland",
        "HiringPath": [
            {
                "Code": "public",
                "SearchDisplay": "Open to the public",
                "Tooltip": "Jobs open to U.S. Citizens",
            }
        ],
        "JobCategoryCode": [{"Name": "Information Technology Management", "Code": "2210"}],
        "PositionStartDate": "2026-07-30T00:00:00.0000",
        "PositionEndDate": "2026-08-13T23:59:59.9970",
    }


def _make_search_response(
    jobs: list[dict] | None = None,
    total: str = "47",
    page: int = 1,
    num_pages: int = 1,
) -> dict:
    jobs = jobs if jobs is not None else [_make_job()]
    return {
        "TeaserName": "",
        "Total": total,
        "Pager": {
            "IsPaged": num_pages > 1,
            "NumberOfPages": num_pages,
            "NumberOfItems": int(total),
            "ItemsPerPage": 50,
            "CurrentPageIndex": page,
            "HasNextPage": page < num_pages,
            "HasPreviousPage": page > 1,
        },
        "Jobs": jobs,
        "Suggestion": [],
        "SortField": "startdate",
        "SortDirection": "desc",
        "IsRadialSearch": False,
        "UniqueSearchID": "test-id",
        "IsValid": True,
        "f": {},
    }


def _html_response(status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = "<html><body>USAJOBS Search Results</body></html>"
    resp.raise_for_status = MagicMock()
    return resp


def _json_response(data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = json.dumps(data)
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# User-Agent 고정
# ---------------------------------------------------------------------------

class TestFixedUserAgent:
    def test_crawler_ua_matches_sources_constant(self):
        assert _USER_AGENT == USAJOBS_USER_AGENT

    def test_sources_crawl_source_uses_same_ua(self):
        assert USAJOBS_SOURCE.user_agent == USAJOBS_USER_AGENT

    def test_ua_is_browser_chrome_string(self):
        assert "Mozilla/5.0" in USAJOBS_USER_AGENT
        assert "Chrome/124.0.0.0" in USAJOBS_USER_AGENT
        assert "Macintosh" in USAJOBS_USER_AGENT

    def test_crawler_session_sets_fixed_ua(self):
        with patch.object(_USAJobsCrawler, "_build_session") as build:
            session = requests.Session()
            build.return_value = session
            crawler = _USAJobsCrawler()
            assert crawler.user_agent == USAJOBS_USER_AGENT
            assert crawler._session.headers.get("User-Agent") == USAJOBS_USER_AGENT


# ---------------------------------------------------------------------------
# 세션 쿠키 유지
# ---------------------------------------------------------------------------

class TestSessionCookiePersistence:
    def test_seed_and_search_use_same_session_object(self):
        """GET 시드와 POST 검색이 동일 Session 인스턴스를 사용해야 한다."""
        session = MagicMock(spec=requests.Session)
        session.headers = {}
        session.cookies = MagicMock()
        session.cookies.keys.return_value = ["akavpau_usajobs"]

        seed_resp = _html_response()
        search_resp = _json_response(_make_search_response())
        session.get.return_value = seed_resp
        session.post.return_value = search_resp

        with patch.object(_USAJobsCrawler, "_build_session", return_value=session):
            crawler = _USAJobsCrawler()
            # rate limit 제거
            crawler.rate_limit_min = 0
            crawler.rate_limit_max = 0

            assert crawler.seed_session() is True
            data = crawler.execute_search("software engineer", page=1)

        assert data is not None
        assert data["Total"] == "47"

        # 동일 session 으로 get + post
        assert session.get.called
        assert session.post.called
        get_url = session.get.call_args[0][0]
        post_url = session.post.call_args[0][0]
        assert get_url == _RESULTS_URL
        assert post_url == _SEARCH_URL

        # Session 객체가 crawler에 그대로 유지
        assert crawler._session is session
        assert crawler._session_seeded is True

    def test_seed_skipped_on_second_call_without_force(self):
        session = MagicMock(spec=requests.Session)
        session.headers = {}
        session.cookies = MagicMock()
        session.cookies.keys.return_value = ["akavpau_usajobs"]
        session.get.return_value = _html_response()

        with patch.object(_USAJobsCrawler, "_build_session", return_value=session):
            crawler = _USAJobsCrawler()
            crawler.rate_limit_min = 0
            crawler.rate_limit_max = 0
            assert crawler.seed_session() is True
            assert crawler.seed_session() is True  # 재사용

        assert session.get.call_count == 1

    def test_force_reseed_calls_get_again(self):
        session = MagicMock(spec=requests.Session)
        session.headers = {}
        session.cookies = MagicMock()
        session.cookies.keys.return_value = ["akavpau_usajobs"]
        session.get.return_value = _html_response()

        with patch.object(_USAJobsCrawler, "_build_session", return_value=session):
            crawler = _USAJobsCrawler()
            crawler.rate_limit_min = 0
            crawler.rate_limit_max = 0
            crawler.seed_session()
            crawler.seed_session(force=True)

        assert session.get.call_count == 2

    def test_post_sends_json_payload_with_fixed_ua(self):
        session = MagicMock(spec=requests.Session)
        session.headers = {}
        session.cookies = MagicMock()
        session.cookies.keys.return_value = ["akavpau_usajobs"]
        session.get.return_value = _html_response()
        session.post.return_value = _json_response(_make_search_response())

        with patch.object(_USAJobsCrawler, "_build_session", return_value=session):
            crawler = _USAJobsCrawler()
            crawler.rate_limit_min = 0
            crawler.rate_limit_max = 0
            crawler.execute_search("data scientist", page=2, results_per_page=25)

        kwargs = session.post.call_args.kwargs
        assert kwargs["json"]["Keyword"] == "data scientist"
        assert kwargs["json"]["Page"] == "2"
        assert kwargs["json"]["ResultsPerPage"] == 25
        assert kwargs["json"]["HiringPath"] == ["public"]
        assert kwargs["headers"]["User-Agent"] == USAJOBS_USER_AGENT
        assert kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_is_blocked_detects_access_denied(self):
        assert _is_blocked("Access Denied") is True
        assert _is_blocked('{"Jobs":[]}') is False

    def test_has_next_page(self):
        assert _has_next_page({"HasNextPage": True, "NumberOfPages": 10}, 1) is True
        assert _has_next_page({"HasNextPage": False, "NumberOfPages": 1}, 1) is False
        assert _has_next_page({"NumberOfPages": 3}, 2) is True
        assert _has_next_page({"NumberOfPages": 3}, 3) is False

    def test_resolve_keywords_taxonomy(self):
        kws = _resolve_keywords("Software Engineer")
        assert "software engineer" in kws

    def test_resolve_keywords_fallback(self):
        assert _resolve_keywords("obscure federal role xyz") == ["obscure federal role xyz"]


# ---------------------------------------------------------------------------
# collect_jobs / crawl_usajobs
# ---------------------------------------------------------------------------

class TestCollectAndCrawl:
    def test_collect_jobs_skips_saved_ids(self):
        session = MagicMock(spec=requests.Session)
        session.headers = {}
        session.cookies = MagicMock()
        session.cookies.keys.return_value = ["akavpau_usajobs"]
        session.get.return_value = _html_response()
        jobs = [_make_job(1), _make_job(2)]
        session.post.return_value = _json_response(
            _make_search_response(jobs=jobs, total="2", num_pages=1),
        )

        with patch.object(_USAJobsCrawler, "_build_session", return_value=session):
            crawler = _USAJobsCrawler()
            crawler.rate_limit_min = 0
            crawler.rate_limit_max = 0
            saved = {(_SOURCE_NAME, "1")}
            results = crawler.collect_jobs("software engineer", saved_ids=saved)

        assert len(results) == 1
        assert results[0].source_job_id == "2"
        # 상세 페이지 HTML 을 raw_html 에 저장 (mock get 응답)
        assert results[0].raw_html
        assert json.loads(results[0].raw_text)["DocumentID"] == 2

    def test_crawl_usajobs_saves_json(self):
        session = MagicMock(spec=requests.Session)
        session.headers = {}
        session.cookies = MagicMock()
        session.cookies.keys.return_value = ["akavpau_usajobs"]
        session.get.return_value = _html_response()
        session.post.return_value = _json_response(
            _make_search_response(jobs=[_make_job(99)], total="1"),
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(_USAJobsCrawler, "_build_session", return_value=session):
                with patch(
                    "src.crawlers.usajobs.crawler.get_saved_ids",
                    return_value=set(),
                ):
                    path = crawl_usajobs(
                        query="software engineer",
                        crawl_date="2026-07-30",
                        save_path=tmp,
                        max_pages=1,
                        max_jobs=5,
                    )
            assert path
            saved = Path(path)
            assert saved.exists()
            # 공고당 1파일(dict). 경로: {job_function}/{source}/{date}_{source_job_id}.json
            assert saved.name == "2026-07-30_99.json"
            assert saved.parent.name == "usajobs"
            doc = json.loads(saved.read_text())
            assert isinstance(doc, dict)
            assert doc["source_name"] == "usajobs"
            assert doc["source_job_id"] == "99"

    def test_run_batch_continues_on_failure(self):
        calls: list[str] = []

        def fake_crawl(query, **kwargs):
            calls.append(query)
            if query == "bad":
                raise RuntimeError("boom")
            return "/tmp/ok.json"

        with patch("src.crawlers.usajobs.crawler.crawl_usajobs", side_effect=fake_crawl):
            with patch("src.crawlers.usajobs.crawler.time.sleep"):
                run_usajobs_batch(
                    ["ok1", "bad", "ok2"],
                    crawl_date="2026-07-30",
                    max_pages=1,
                )
        assert calls == ["ok1", "bad", "ok2"]
