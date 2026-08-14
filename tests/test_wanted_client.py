"""
crawlers/wanted/client.py 유닛 테스트.
네트워크 호출은 unittest.mock으로 패치한다.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from src.crawlers.wanted.client import (
    _WantedCrawler,
    _is_blocked,
    _resolve_tag_ids,
    fetch_wanted,
    run_wanted_batch,
)
from src.crawlers.wanted.search_queries import (
    get_tag_ids_for_function,
    get_all_function_names,
    get_all_tag_ids,
)


# ---------------------------------------------------------------------------
# _is_blocked
# ---------------------------------------------------------------------------

class TestIsBlocked:
    def test_access_denied(self):
        assert _is_blocked("<html><body>Access Denied</body></html>")

    def test_human_verification(self):
        assert _is_blocked("human verification required")

    def test_normal_json(self):
        data = json.dumps({"job": {"id": 1, "position": "Backend Engineer"}})
        assert not _is_blocked(data)

    def test_empty(self):
        assert not _is_blocked("")

    def test_case_insensitive(self):
        assert _is_blocked("JUST A MOMENT")

    def test_korean_block(self):
        assert _is_blocked("자동화된 접근이 감지되었습니다.")

    def test_bot_detection(self):
        assert _is_blocked("bot detection activated")

    def test_normal_korean(self):
        assert not _is_blocked('{"job": {"position": "백엔드 개발자"}}')


# ---------------------------------------------------------------------------
# _resolve_tag_ids
# ---------------------------------------------------------------------------

class TestResolveTagIds:
    def test_known_function(self):
        ids = _resolve_tag_ids("Backend Engineer")
        assert isinstance(ids, list)
        assert len(ids) > 0
        assert all(isinstance(i, int) for i in ids)

    def test_numeric_string(self):
        ids = _resolve_tag_ids("872,873")
        assert ids == [872, 873]

    def test_single_numeric(self):
        ids = _resolve_tag_ids("872")
        assert ids == [872]

    def test_unknown_function(self):
        ids = _resolve_tag_ids("Nonexistent Job 99999")
        assert ids == []

    def test_empty_string(self):
        ids = _resolve_tag_ids("")
        assert ids == []

    def test_whitespace_stripped(self):
        ids = _resolve_tag_ids("  Backend Engineer  ")
        assert isinstance(ids, list)
        assert len(ids) > 0


# ---------------------------------------------------------------------------
# search_queries
# ---------------------------------------------------------------------------

class TestSearchQueries:
    def test_get_all_function_names_nonempty(self):
        names = get_all_function_names()
        assert len(names) > 0

    def test_backend_engineer_in_mapping(self):
        ids = get_tag_ids_for_function("Backend Engineer")
        assert 872 in ids  # 서버 개발자

    def test_frontend_engineer_in_mapping(self):
        ids = get_tag_ids_for_function("Frontend Engineer")
        assert 669 in ids  # 프론트엔드 개발자

    def test_mobile_engineer_has_multiple(self):
        ids = get_tag_ids_for_function("Mobile Engineer")
        assert len(ids) >= 2  # iOS + 안드로이드 최소 2개

    def test_unknown_function_returns_empty(self):
        ids = get_tag_ids_for_function("Unknown Job Function XYZ")
        assert ids == []

    def test_all_tag_ids_unique(self):
        all_ids = get_all_tag_ids()
        assert len(all_ids) == len(set(all_ids))

    def test_all_ids_are_positive_ints(self):
        for tag_id in get_all_tag_ids():
            assert isinstance(tag_id, int)
            assert tag_id > 0


# ---------------------------------------------------------------------------
# _WantedCrawler.extract_job_ids
# ---------------------------------------------------------------------------

class TestExtractJobIds:
    def setup_method(self):
        with patch.object(_WantedCrawler, "__init__", lambda self: None):
            self.crawler = _WantedCrawler.__new__(_WantedCrawler)

    def test_normal_response(self):
        page_data = {
            "data": [
                {"id": 100, "position": "Backend Dev"},
                {"id": 200, "position": "Frontend Dev"},
            ],
            "links": {"next": None, "prev": None},
        }
        ids = self.crawler.extract_job_ids(page_data)
        assert ids == [100, 200]

    def test_empty_data(self):
        page_data = {"data": [], "links": {"next": None}}
        ids = self.crawler.extract_job_ids(page_data)
        assert ids == []

    def test_missing_id_skipped(self):
        page_data = {
            "data": [
                {"id": 100, "position": "Dev"},
                {"position": "No ID"},   # id 없음 — 건너뜀
            ],
            "links": {},
        }
        ids = self.crawler.extract_job_ids(page_data)
        assert ids == [100]

    def test_string_id_converted_to_int(self):
        page_data = {"data": [{"id": "999", "position": "Dev"}], "links": {}}
        ids = self.crawler.extract_job_ids(page_data)
        assert ids == [999]


# ---------------------------------------------------------------------------
# _WantedCrawler.has_next_page
# ---------------------------------------------------------------------------

class TestHasNextPage:
    def setup_method(self):
        with patch.object(_WantedCrawler, "__init__", lambda self: None):
            self.crawler = _WantedCrawler.__new__(_WantedCrawler)

    def test_has_next_when_next_is_set(self):
        page_data = {"links": {"next": "/api/v4/jobs?offset=20", "prev": None}}
        assert self.crawler.has_next_page(page_data) is True

    def test_no_next_when_next_is_null(self):
        page_data = {"links": {"next": None, "prev": None}}
        assert self.crawler.has_next_page(page_data) is False

    def test_no_next_when_links_missing(self):
        page_data = {}
        assert self.crawler.has_next_page(page_data) is False

    def test_no_next_when_next_is_empty(self):
        page_data = {"links": {"next": ""}}
        assert self.crawler.has_next_page(page_data) is False


# ---------------------------------------------------------------------------
# _WantedCrawler.collect_jobs (네트워크 모킹)
# ---------------------------------------------------------------------------

def _make_list_response(job_ids: list[int], has_next: bool = False) -> dict:
    return {
        "data": [{"id": jid, "position": f"Job {jid}"} for jid in job_ids],
        "links": {"next": "/api/v4/jobs?offset=20" if has_next else None},
    }


def _make_detail_response(job_id: int) -> dict:
    return {
        "job": {
            "id": job_id,
            "position": f"Backend Developer {job_id}",
            "status": "active",
            "company": {"id": 1, "name": "테스트컴퍼니", "industry_name": "IT, 컨텐츠"},
            "address": {
                "location": "서울",
                "district": "강남구",
                "country": "한국",
                "full_location": "서울 강남구",
                "location_key": "seoul",
                "district_key": "seoul.gangnam-gu",
            },
            "annual_from": 3,
            "annual_to": 7,
            "due_time": None,
            "skill_tags": [{"id": 100, "title": "Python"}, {"id": 101, "title": "Django"}],
            "category_tags": [{"parent_id": 518, "id": 872}],
            "company_tags": [],
            "detail": {
                "intro": "좋은 회사입니다.",
                "main_tasks": "서버 개발을 담당합니다.",
                "requirements": "Python 3년 이상",
                "preferred_points": "Django 경험자",
                "benefits": "4대 보험",
            },
            "reward": {"formatted_total": "100만원"},
            "like_count": 5,
        },
        "application": None,
    }


class TestCollectJobs:
    def _build_mock_crawler(self) -> _WantedCrawler:
        with patch.object(_WantedCrawler, "__init__", lambda self: None):
            c = _WantedCrawler.__new__(_WantedCrawler)
        c.source_name = "wanted"
        return c

    def test_single_page_two_jobs(self):
        crawler = self._build_mock_crawler()
        list_resp = _make_list_response([111, 222], has_next=False)
        detail_111 = _make_detail_response(111)
        detail_222 = _make_detail_response(222)

        crawler.fetch_jobs_page = MagicMock(return_value=list_resp)
        crawler.fetch_job_detail = MagicMock(side_effect=[detail_111, detail_222])

        results = crawler.collect_jobs(tag_type_ids=[872], saved_ids=set())

        assert len(results) == 2
        assert results[0].source_job_id == "111"
        assert results[1].source_job_id == "222"
        assert results[0].source_name == "wanted"

    def test_already_saved_skipped(self):
        crawler = self._build_mock_crawler()
        list_resp = _make_list_response([111, 222], has_next=False)
        detail_222 = _make_detail_response(222)

        crawler.fetch_jobs_page = MagicMock(return_value=list_resp)
        crawler.fetch_job_detail = MagicMock(return_value=detail_222)

        saved = {("wanted", "111")}
        results = crawler.collect_jobs(tag_type_ids=[872], saved_ids=saved)

        assert len(results) == 1
        assert results[0].source_job_id == "222"
        crawler.fetch_job_detail.assert_called_once()

    def test_list_api_none_returns_empty(self):
        crawler = self._build_mock_crawler()
        crawler.fetch_jobs_page = MagicMock(return_value=None)

        results = crawler.collect_jobs(tag_type_ids=[872], saved_ids=set())
        assert results == []

    def test_empty_list_returns_empty(self):
        crawler = self._build_mock_crawler()
        crawler.fetch_jobs_page = MagicMock(
            return_value={"data": [], "links": {"next": None}}
        )

        results = crawler.collect_jobs(tag_type_ids=[872], saved_ids=set())
        assert results == []

    def test_detail_failure_skipped(self):
        crawler = self._build_mock_crawler()
        list_resp = _make_list_response([111, 222], has_next=False)

        crawler.fetch_jobs_page = MagicMock(return_value=list_resp)
        crawler.fetch_job_detail = MagicMock(
            side_effect=[None, _make_detail_response(222)]
        )

        results = crawler.collect_jobs(tag_type_ids=[872], saved_ids=set())
        assert len(results) == 1
        assert results[0].source_job_id == "222"

    def test_raw_text_contains_json(self):
        crawler = self._build_mock_crawler()
        detail = _make_detail_response(999)
        crawler.fetch_jobs_page = MagicMock(
            return_value=_make_list_response([999], has_next=False)
        )
        crawler.fetch_job_detail = MagicMock(return_value=detail)

        results = crawler.collect_jobs(tag_type_ids=[872], saved_ids=set())
        assert len(results) == 1
        raw_text = results[0].raw_text
        parsed = json.loads(raw_text)
        assert parsed["job"]["id"] == 999

    def test_raw_html_is_empty(self):
        crawler = self._build_mock_crawler()
        crawler.fetch_jobs_page = MagicMock(
            return_value=_make_list_response([999], has_next=False)
        )
        crawler.fetch_job_detail = MagicMock(return_value=_make_detail_response(999))

        results = crawler.collect_jobs(tag_type_ids=[872], saved_ids=set())
        assert results[0].raw_html == ""

    def test_pagination_two_pages(self):
        crawler = self._build_mock_crawler()
        page1 = _make_list_response([1, 2], has_next=True)
        page2 = _make_list_response([3, 4], has_next=False)

        crawler.fetch_jobs_page = MagicMock(side_effect=[page1, page2])
        crawler.fetch_job_detail = MagicMock(
            side_effect=[
                _make_detail_response(i) for i in [1, 2, 3, 4]
            ]
        )

        results = crawler.collect_jobs(tag_type_ids=[872], saved_ids=set())
        assert len(results) == 4
        ids = {r.source_job_id for r in results}
        assert ids == {"1", "2", "3", "4"}

    def test_max_pages_respected(self):
        crawler = self._build_mock_crawler()
        always_has_next = _make_list_response([1], has_next=True)
        crawler.fetch_jobs_page = MagicMock(return_value=always_has_next)
        crawler.fetch_job_detail = MagicMock(
            side_effect=lambda jid: _make_detail_response(jid)
        )

        results = crawler.collect_jobs(
            tag_type_ids=[872], saved_ids=set(), max_pages=3
        )
        assert crawler.fetch_jobs_page.call_count == 3


# ---------------------------------------------------------------------------
# fetch_wanted (통합 모킹)
# ---------------------------------------------------------------------------

class TestCrawlWanted:
    @patch("src.crawlers.wanted.client.save_documents")
    @patch("src.crawlers.wanted.client.get_saved_ids", return_value=set())
    @patch("src.crawlers.wanted.client._WantedCrawler")
    def test_saves_documents_on_success(
        self, mock_crawler_cls, mock_get_saved, mock_save
    ):
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.collect_jobs.return_value = [
            MagicMock(to_dict=lambda: {"id": "x", "source_name": "wanted",
                                        "source_job_id": "111"})
        ]
        mock_crawler_cls.return_value = mock_instance
        mock_save.return_value = Path("/tmp/wanted_Backend_Engineer.json")

        result = fetch_wanted("Backend Engineer", crawl_date="2026-07-27")

        mock_save.assert_called_once()
        assert result != ""

    @patch("src.crawlers.wanted.client.get_saved_ids", return_value=set())
    @patch("src.crawlers.wanted.client._WantedCrawler")
    def test_empty_result_returns_empty_string(
        self, mock_crawler_cls, mock_get_saved
    ):
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.collect_jobs.return_value = []
        mock_crawler_cls.return_value = mock_instance

        result = fetch_wanted("Backend Engineer", crawl_date="2026-07-27")
        assert result == ""

    def test_unmapped_function_returns_empty(self):
        result = fetch_wanted("Unknown XYZ Job 9999", crawl_date="2026-07-27")
        assert result == ""


# ---------------------------------------------------------------------------
# run_wanted_batch (통합 모킹)
# ---------------------------------------------------------------------------

class TestRunWantedBatch:
    @patch("src.crawlers.wanted.client.fetch_wanted")
    @patch("time.sleep")
    def test_calls_crawl_for_each_function(self, mock_sleep, mock_crawl):
        mock_crawl.return_value = "/tmp/test.json"
        functions = ["Backend Engineer", "Frontend Engineer", "Data Engineer"]

        run_wanted_batch(job_functions=functions, crawl_date="2026-07-27")

        assert mock_crawl.call_count == 3

    @patch("src.crawlers.wanted.client.fetch_wanted")
    @patch("time.sleep")
    def test_continues_on_partial_failure(self, mock_sleep, mock_crawl):
        mock_crawl.side_effect = [
            Exception("네트워크 오류"),
            "/tmp/frontend.json",
        ]

        run_wanted_batch(
            job_functions=["Backend Engineer", "Frontend Engineer"],
            crawl_date="2026-07-27",
        )

        assert mock_crawl.call_count == 2

    @patch("src.crawlers.wanted.client.fetch_wanted")
    @patch("time.sleep")
    def test_sleep_between_functions(self, mock_sleep, mock_crawl):
        mock_crawl.return_value = "/tmp/test.json"
        run_wanted_batch(
            job_functions=["Backend Engineer", "Frontend Engineer"],
            crawl_date="2026-07-27",
        )
        assert mock_sleep.call_count >= 1
