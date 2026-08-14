"""
crawlers/rallit/client.py 유닛 테스트.
네트워크 호출은 unittest.mock으로 패치한다.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.crawlers.rallit.client import (
    _RallitCrawler,
    _is_blocked,
    _resolve_keywords,
    fetch_rallit,
    run_rallit_batch,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처 / 헬퍼
# ---------------------------------------------------------------------------

def _make_position(position_id: int = 4233) -> dict:
    """목록 API 응답의 item 예시."""
    return {
        "id": position_id,
        "title": "백엔드 개발자",
        "jobLevel": "IRRELEVANT",
        "jobLevels": ["SENIOR", "MIDDLE"],
        "startedAt": "1970-01-01",
        "endedAt": "9999-12-31",
        "companyId": 293,
        "companyName": "테스트 회사",
        "addressRegion": {"code": "GANGNAM", "name": "강남"},
        "companyRepresentativeImage": "https://cdn.rallit.com/logo.png",
        "isBookmarked": False,
        "status": {"code": "HIRING", "name": "모집 중"},
        "url": f"https://www.rallit.com/positions/{position_id}",
        "joinReward": "0",
        "jobSkillKeywords": ["Python", "Django"],
        "partnerLogo": "",
        "isPartner": False,
    }


def _make_list_data(
    items: list[dict] | None = None,
    total_count: int = 100,
    total_page: int = 5,
    page_number: int = 1,
) -> dict:
    """목록 API 응답의 data 딕셔너리."""
    return {
        "pageNumber": page_number,
        "pageSize": 20,
        "totalCount": total_count,
        "totalPage": total_page,
        "items": items if items is not None else [_make_position()],
    }


def _make_detail_data(position_id: int = 4233) -> dict:
    """상세 API 응답의 data 딕셔너리."""
    return {
        "id": position_id,
        "title": "백엔드 개발자",
        "companyName": "테스트 회사",
        "companyId": 293,
        "companyLogo": "https://cdn.rallit.com/logo.png",
        "companyRepresentativeImages": [],
        "companyTags": ["코드 리뷰"],
        "companyDescription": "<p>좋은 회사입니다</p>",
        "description": "<p>회사 소개</p>",
        "responsibilities": "<ul><li>백엔드 개발</li></ul>",
        "basicQualifications": "<ul><li>Python 3년 이상</li></ul>",
        "preferredQualifications": "<ul><li>AWS 경험 우대</li></ul>",
        "benefits": "<p>자유로운 연차</p>",
        "additionalComments": "",
        "salaryType": "UNKNOWN_SALARY",
        "minimumSalary": None,
        "jobs": [{"code": "BACKEND_DEVELOPER", "name": "백엔드/서버 개발자"}],
        "jobLevel": "IRRELEVANT",
        "jobLevels": ["SENIOR", "MIDDLE"],
        "jobSkillKeywords": ["Python", "Django", "PostgreSQL"],
        "addressMain": "서울 강남구 테헤란로 123",
        "addressDetail": "10층",
        "addressBuildingName": "테스트빌딩",
        "addressRegion": {"code": "GANGNAM", "name": "강남"},
        "zipCode": "",
        "startedAt": "1970-01-01",
        "endedAt": "9999-12-31",
        "homepage": "https://test.example.com",
        "latitude": 37.5,
        "longitude": 127.0,
        "status": {"code": "HIRING", "name": "모집 중"},
        "isAlwaysHiring": True,
        "isBookmarked": False,
        "isPartner": False,
        "partnerLogo": "",
        "joinReward": "0",
        "freeQuestions": [],
        "positionSteps": ["서류 검토", "1차인터뷰"],
        "approvedAt": "",
        "bookmarkCount": 5,
        "submitStatus": "NONE",
        "content": "",
    }


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """requests.Response 모의 객체."""
    resp = MagicMock()
    resp.status_code = status_code
    body = {"statusCode": 200, "message": "success", "data": data, "errorCode": None}
    resp.json.return_value = body
    resp.text = json.dumps(body)
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _is_blocked
# ---------------------------------------------------------------------------

class TestIsBlocked:
    def test_not_blocked_for_normal_json(self):
        assert _is_blocked('{"statusCode": 200, "data": {}}') is False

    def test_detects_access_denied(self):
        assert _is_blocked("Access Denied") is True

    def test_detects_korean_block_message(self):
        assert _is_blocked("비정상적인 접근이 감지되었습니다.") is True

    def test_detects_cloudflare(self):
        assert _is_blocked("Just a moment... Cloudflare") is True

    def test_case_insensitive(self):
        assert _is_blocked("JUST A MOMENT...") is True


# ---------------------------------------------------------------------------
# _resolve_keywords
# ---------------------------------------------------------------------------

class TestResolveKeywords:
    def test_none_returns_none_in_list(self):
        result = _resolve_keywords(None)
        assert result == [None]

    def test_empty_string_returns_none(self):
        result = _resolve_keywords("")
        assert result == [None]

    def test_numeric_string_returns_none_for_keyword(self):
        # 숫자 ID는 keyword 필터 불필요
        result = _resolve_keywords("4233,4234")
        assert result == [None]

    def test_taxonomy_english_name(self):
        result = _resolve_keywords("Backend Engineer")
        assert isinstance(result, list)
        assert len(result) > 0
        assert None not in result  # 실제 keyword 값이어야 함

    def test_korean_alias(self):
        result = _resolve_keywords("백엔드 개발자")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_unknown_query_falls_back_to_itself(self):
        result = _resolve_keywords("NonExistentJobXYZ999")
        assert result == ["NonExistentJobXYZ999"]


# ---------------------------------------------------------------------------
# _RallitCrawler.extract_position_ids
# ---------------------------------------------------------------------------

class TestExtractPositionIds:
    def setup_method(self):
        with patch("src.crawlers.rallit.client._RallitCrawler._build_session"):
            self.crawler = _RallitCrawler.__new__(_RallitCrawler)
            self.crawler._session = MagicMock()
            self.crawler._robots_cache = {}

    def test_extracts_ids_from_items(self):
        page_data = _make_list_data(
            items=[_make_position(1), _make_position(2), _make_position(3)],
        )
        ids = self.crawler.extract_position_ids(page_data)
        assert ids == [1, 2, 3]

    def test_empty_items_returns_empty(self):
        assert self.crawler.extract_position_ids({"items": []}) == []

    def test_missing_items_key_returns_empty(self):
        assert self.crawler.extract_position_ids({}) == []

    def test_skips_items_without_id(self):
        page_data = {"items": [{"title": "no id"}, {"id": 42}]}
        assert self.crawler.extract_position_ids(page_data) == [42]


# ---------------------------------------------------------------------------
# _RallitCrawler.has_next_page
# ---------------------------------------------------------------------------

class TestHasNextPage:
    def setup_method(self):
        with patch("src.crawlers.rallit.client._RallitCrawler._build_session"):
            self.crawler = _RallitCrawler.__new__(_RallitCrawler)
            self.crawler._session = MagicMock()
            self.crawler._robots_cache = {}

    def test_current_page_less_than_total_means_more(self):
        page_data = _make_list_data(total_page=5)
        assert self.crawler.has_next_page(page_data, current_page=1) is True

    def test_current_page_equals_total_means_done(self):
        page_data = _make_list_data(total_page=5)
        assert self.crawler.has_next_page(page_data, current_page=5) is False

    def test_current_page_exceeds_total_means_done(self):
        page_data = _make_list_data(total_page=3)
        assert self.crawler.has_next_page(page_data, current_page=4) is False

    def test_total_page_zero_means_done(self):
        page_data = _make_list_data(total_page=0)
        assert self.crawler.has_next_page(page_data, current_page=1) is False


# ---------------------------------------------------------------------------
# _RallitCrawler session headers
# ---------------------------------------------------------------------------

class TestRallitSessionHeaders:
    def test_does_not_advertise_brotli(self):
        crawler = _RallitCrawler()
        try:
            enc = crawler._session.headers.get("Accept-Encoding", "")
            assert "br" not in enc.replace(" ", "")
            assert "gzip" in enc
        finally:
            crawler.close()


# ---------------------------------------------------------------------------
# _RallitCrawler.fetch_positions_page (네트워크 패치)
# ---------------------------------------------------------------------------

class TestFetchPositionsPage:
    @patch("src.crawlers.rallit.client._RallitCrawler.get")
    def test_returns_data_on_success(self, mock_get):
        expected_data = _make_list_data()
        mock_get.return_value = _mock_response(expected_data)

        with patch("src.crawlers.rallit.client._RallitCrawler._build_session"):
            crawler = _RallitCrawler.__new__(_RallitCrawler)
            crawler._session = MagicMock()
            crawler._robots_cache = {}

        result = crawler.fetch_positions_page(keyword="백엔드", page=1)
        assert result is not None
        assert result.get("totalCount") == expected_data["totalCount"]

    @patch("src.crawlers.rallit.client._RallitCrawler.get")
    def test_returns_none_on_request_exception(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("timeout")

        with patch("src.crawlers.rallit.client._RallitCrawler._build_session"):
            crawler = _RallitCrawler.__new__(_RallitCrawler)
            crawler._session = MagicMock()
            crawler._robots_cache = {}

        result = crawler.fetch_positions_page(keyword="백엔드", page=1)
        assert result is None

    @patch("src.crawlers.rallit.client._RallitCrawler.get")
    def test_returns_none_when_blocked(self, mock_get):
        blocked_resp = MagicMock()
        blocked_resp.text = "Access Denied"
        blocked_resp.json.return_value = {}
        blocked_resp.raise_for_status = MagicMock()
        mock_get.return_value = blocked_resp

        with patch("src.crawlers.rallit.client._RallitCrawler._build_session"):
            crawler = _RallitCrawler.__new__(_RallitCrawler)
            crawler._session = MagicMock()
            crawler._robots_cache = {}

        result = crawler.fetch_positions_page(keyword="백엔드", page=1)
        assert result is None


# ---------------------------------------------------------------------------
# fetch_rallit (E2E, 파일 저장까지)
# ---------------------------------------------------------------------------

class TestCrawlRallit:
    @patch("src.crawlers.rallit.client._RallitCrawler.get")
    def test_saves_file_on_success(self, mock_get):
        detail_data = _make_detail_data(position_id=4233)
        list_data = _make_list_data(
            items=[_make_position(4233)],
            total_count=1,
            total_page=1,
        )

        mock_get.side_effect = [
            _mock_response(list_data),   # 목록 API
            _mock_response(detail_data), # 상세 API
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_rallit(
                query="백엔드",  # keyword 직접 전달
                crawl_date="2026-07-29",
                save_path=tmpdir,
            )

            assert result != ""
            saved = Path(result)
            assert saved.exists()
            doc = json.loads(saved.read_text(encoding="utf-8"))
            assert isinstance(doc, dict)
            assert doc["source_name"] == "rallit"
            assert doc["source_job_id"] == "4233"
            assert doc["parse_status"] == "PENDING"
            assert len(list(Path(tmpdir).rglob("*.json"))) == 1

    @patch("src.crawlers.rallit.client._RallitCrawler.get")
    def test_skips_already_saved_ids(self, mock_get):
        """이미 저장된 position_id는 상세 API를 호출하지 않는다."""
        list_data = _make_list_data(
            items=[_make_position(99999)],
            total_count=1,
            total_page=1,
        )
        mock_get.return_value = _mock_response(list_data)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "src.crawlers.rallit.client.get_saved_ids",
                return_value={("rallit", "99999")},
            ):
                result = fetch_rallit(
                    query="백엔드",
                    crawl_date="2026-07-29",
                    save_path=tmpdir,
                )

        # 목록 API만 호출, 상세 API는 호출 없음
        assert mock_get.call_count == 1
        assert result == ""

    def test_none_query_uses_no_keyword(self):
        """query=None 이면 keyword 없이 전체 목록 수집."""
        keywords = _resolve_keywords(None)
        assert keywords == [None]

    @patch("src.crawlers.rallit.client.fetch_rallit")
    def test_run_batch_calls_crawl_per_function(self, mock_crawl):
        mock_crawl.return_value = "/tmp/saved.json"
        functions = ["Backend Engineer", "Frontend Engineer"]
        run_rallit_batch(functions, crawl_date="2026-07-29", save_dir="/tmp")
        assert mock_crawl.call_count == 2

    @patch("src.crawlers.rallit.client.fetch_rallit")
    def test_run_batch_continues_on_error(self, mock_crawl):
        """한 항목이 실패해도 나머지는 계속 진행한다."""
        mock_crawl.side_effect = [Exception("API 오류"), "/tmp/saved.json"]
        functions = ["Backend Engineer", "Frontend Engineer"]
        run_rallit_batch(functions, crawl_date="2026-07-29", save_dir="/tmp")
        assert mock_crawl.call_count == 2

    @patch("src.crawlers.rallit.client._RallitCrawler.get")
    def test_max_jobs_limits_collection(self, mock_get):
        """max_jobs=1 이면 첫 공고만 수집하고 중단한다."""
        positions = [_make_position(i) for i in range(1, 6)]
        list_data = _make_list_data(items=positions, total_count=5, total_page=1)
        detail_data = _make_detail_data(position_id=1)

        mock_get.side_effect = [
            _mock_response(list_data),
            _mock_response(detail_data),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_rallit(
                query="백엔드",
                crawl_date="2026-07-29",
                save_path=tmpdir,
                max_jobs=1,
            )

            assert result != ""
            saved_files = list(Path(tmpdir).rglob("*.json"))
            assert len(saved_files) == 1
            doc = json.loads(saved_files[0].read_text(encoding="utf-8"))
            assert doc["source_job_id"] == "1"

    @patch("src.crawlers.rallit.client._RallitCrawler.get")
    def test_detail_failure_skips_gracefully(self, mock_get):
        """상세 API 실패 시 해당 공고를 건너뛰고 계속 진행한다."""
        import requests

        list_data = _make_list_data(
            items=[_make_position(1), _make_position(2)],
            total_count=2,
            total_page=1,
        )

        mock_get.side_effect = [
            _mock_response(list_data),                         # 목록 API
            requests.exceptions.ConnectionError("timeout"),    # 상세 API (1) 실패
            _mock_response(_make_detail_data(position_id=2)), # 상세 API (2) 성공
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_rallit(
                query="백엔드",
                crawl_date="2026-07-29",
                save_path=tmpdir,
            )

            assert result != ""
            saved_files = list(Path(tmpdir).rglob("*.json"))
            assert len(saved_files) == 1
            doc = json.loads(saved_files[0].read_text(encoding="utf-8"))
            assert doc["source_job_id"] == "2"
