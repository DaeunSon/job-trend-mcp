"""
crawlers/jumpit/client.py 유닛 테스트.
네트워크 호출은 unittest.mock으로 패치한다.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.crawlers.jumpit.client import (
    _JumpitCrawler,
    _is_blocked,
    _resolve_category_ids,
    fetch_jumpit,
    run_jumpit_batch,
)


# ---------------------------------------------------------------------------
# 테스트 픽스처 / 헬퍼
# ---------------------------------------------------------------------------

def _make_position(position_id: int = 12345) -> dict:
    """목록 API 응답의 position 항목 예시."""
    return {
        "id": position_id,
        "title": "백엔드 개발자",
        "companyName": "테스트 회사",
        "categories": [{"id": 1, "name": "서버/백엔드 개발자"}],
        "tags": [{"id": 1, "name": "Python"}, {"id": 2, "name": "Django"}],
        "minCareer": 3,
        "maxCareer": 7,
        "location": "서울 강남구",
        "closed": False,
        "closedAt": "2026-08-31T23:59:59",
        "companyId": 9999,
        "companyHashId": "OTk5OQ==",
        "employment": False,
        "likeCount": 10,
        "salary": 0,
        "reward": False,
        "scrap": False,
    }


def _make_list_result(
    positions: list[dict] | None = None,
    total_count: int = 100,
    etc: bool = False,
) -> dict:
    """목록 API 응답 result 딕셔너리."""
    return {
        "totalCount": total_count,
        "positions": positions or [_make_position()],
        "etc": etc,
    }


def _make_detail_result(position_id: int = 12345) -> dict:
    """상세 API 응답 result 딕셔너리."""
    return {
        "id": position_id,
        "title": "백엔드 개발자",
        "companyName": "테스트 회사",
        "companyId": 9999,
        "companyHashId": "OTk5OQ==",
        "companyLogo": "https://cdn.jumpit.co.kr/logo.png",
        "repImage": "https://cdn.jumpit.co.kr/rep.png",
        "images": [],
        "tags": [
            {"id": 1, "name": "Python", "imageUrl": "https://cdn.jumpit.co.kr/python.png"},
            {"id": 2, "name": "Django", "imageUrl": "https://cdn.jumpit.co.kr/django.png"},
        ],
        "mainTask": "• Django 기반 백엔드 개발\n• RESTful API 설계 및 구현",
        "qualification": "• Python/Django 실무 경험 3년 이상",
        "preferredPoint": "• AWS 경험 우대",
        "benefit": "• 자유로운 연차 사용\n• 재택근무 가능",
        "applicationProcess": "서류 → 기술 면접 → 최종",
        "employment": False,
        "minCareer": 3,
        "maxCareer": 7,
        "location": "서울 강남구 테헤란로 123",
        "locationCode": 101010,
        "openedAt": "2026-07-01 00:00:00",
        "closedAt": "2026-08-31T23:59:59",
        "companyWebsite": "https://test.example.com",
        "salary": 600,
        "education": "무관",
        "categories": [{"id": 1, "name": "서버/백엔드 개발자"}],
        "companyFoundedAt": "2010년 1월 설립",
        "closed": False,
        "scrap": False,
        "reward": False,
    }


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"status": 200, "result": data}
    resp.text = json.dumps({"status": 200, "result": data})
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _is_blocked
# ---------------------------------------------------------------------------

class TestIsBlocked:
    def test_not_blocked_for_normal_json(self):
        assert _is_blocked('{"status": 200, "result": {}}') is False

    def test_detects_access_denied(self):
        assert _is_blocked("Access Denied") is True

    def test_detects_korean_block_message(self):
        assert _is_blocked("비정상적인 접근이 감지되었습니다.") is True

    def test_case_insensitive(self):
        assert _is_blocked("JUST A MOMENT...") is True


# ---------------------------------------------------------------------------
# _resolve_category_ids
# ---------------------------------------------------------------------------

class TestResolveCategoryIds:
    def test_none_returns_empty(self):
        assert _resolve_category_ids(None) == []

    def test_empty_string_returns_empty(self):
        assert _resolve_category_ids("") == []

    def test_numeric_string_parsed(self):
        assert _resolve_category_ids("1") == [1]

    def test_comma_separated_numeric(self):
        result = _resolve_category_ids("1,9")
        assert result == [1, 9]

    def test_taxonomy_english_name(self):
        result = _resolve_category_ids("Backend Engineer")
        assert isinstance(result, list)
        assert len(result) > 0
        assert 1 in result  # 서버/백엔드 개발자 = 1

    def test_korean_category_name(self):
        result = _resolve_category_ids("백엔드 개발자")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_devops_english_returns_ids(self):
        result = _resolve_category_ids("DevOps / Platform Engineer")
        assert 9 in result  # devops/시스템 엔지니어 = 9

    def test_unknown_returns_empty(self):
        result = _resolve_category_ids("NonExistentJob12345")
        assert result == []


# ---------------------------------------------------------------------------
# _JumpitCrawler.extract_position_ids
# ---------------------------------------------------------------------------

class TestExtractPositionIds:
    def setup_method(self):
        # 실제 HTTP 요청을 막기 위해 세션 패치
        with patch("src.crawlers.jumpit.client._JumpitCrawler._build_session"):
            self.crawler = _JumpitCrawler.__new__(_JumpitCrawler)
            self.crawler._session = MagicMock()
            self.crawler._robots_cache = {}

    def test_extracts_ids_from_positions(self):
        page_result = _make_list_result(
            positions=[_make_position(1), _make_position(2), _make_position(3)],
        )
        ids = self.crawler.extract_position_ids(page_result)
        assert ids == [1, 2, 3]

    def test_empty_positions_returns_empty(self):
        assert self.crawler.extract_position_ids({"positions": []}) == []

    def test_missing_positions_key_returns_empty(self):
        assert self.crawler.extract_position_ids({}) == []

    def test_skips_items_without_id(self):
        result = {"positions": [{"title": "no id"}, {"id": 42}]}
        assert self.crawler.extract_position_ids(result) == [42]


# ---------------------------------------------------------------------------
# _JumpitCrawler.has_next_page
# ---------------------------------------------------------------------------

class TestHasNextPage:
    def setup_method(self):
        with patch("src.crawlers.jumpit.client._JumpitCrawler._build_session"):
            self.crawler = _JumpitCrawler.__new__(_JumpitCrawler)
            self.crawler._session = MagicMock()
            self.crawler._robots_cache = {}

    def test_etc_false_means_no_more(self):
        result = _make_list_result(total_count=100, etc=False)
        assert self.crawler.has_next_page(result, current_page=1, page_size=20) is False

    def test_etc_true_means_more(self):
        result = _make_list_result(total_count=100, etc=True)
        assert self.crawler.has_next_page(result, current_page=1, page_size=20) is True

    def test_fetched_less_than_total_means_more(self):
        result = {"totalCount": 50, "positions": [], "etc": None}
        assert self.crawler.has_next_page(result, current_page=1, page_size=20) is True

    def test_fetched_equals_total_means_done(self):
        result = {"totalCount": 20, "positions": [], "etc": None}
        assert self.crawler.has_next_page(result, current_page=1, page_size=20) is False


# ---------------------------------------------------------------------------
# _JumpitCrawler.fetch_positions_page (네트워크 패치)
# ---------------------------------------------------------------------------

class TestFetchPositionsPage:
    @patch("src.crawlers.jumpit.client._JumpitCrawler.get")
    def test_returns_result_on_success(self, mock_get):
        expected_result = _make_list_result()
        mock_get.return_value = _mock_response(expected_result)

        with patch("src.crawlers.jumpit.client._JumpitCrawler._build_session"):
            crawler = _JumpitCrawler.__new__(_JumpitCrawler)
            crawler._session = MagicMock()
            crawler._robots_cache = {}

        result = crawler.fetch_positions_page(job_category_id=1, page=1)
        assert result is not None
        assert result.get("totalCount") == expected_result["totalCount"]

    @patch("src.crawlers.jumpit.client._JumpitCrawler.get")
    def test_returns_none_on_request_exception(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("timeout")

        with patch("src.crawlers.jumpit.client._JumpitCrawler._build_session"):
            crawler = _JumpitCrawler.__new__(_JumpitCrawler)
            crawler._session = MagicMock()
            crawler._robots_cache = {}

        result = crawler.fetch_positions_page(job_category_id=1, page=1)
        assert result is None

    @patch("src.crawlers.jumpit.client._JumpitCrawler.get")
    def test_returns_none_when_blocked(self, mock_get):
        blocked_resp = MagicMock()
        blocked_resp.text = "Access Denied"
        blocked_resp.json.return_value = {}
        blocked_resp.raise_for_status = MagicMock()
        mock_get.return_value = blocked_resp

        with patch("src.crawlers.jumpit.client._JumpitCrawler._build_session"):
            crawler = _JumpitCrawler.__new__(_JumpitCrawler)
            crawler._session = MagicMock()
            crawler._robots_cache = {}

        result = crawler.fetch_positions_page(job_category_id=1, page=1)
        assert result is None


# ---------------------------------------------------------------------------
# fetch_jumpit (E2E, 파일 저장까지)
# ---------------------------------------------------------------------------

class TestCrawlJumpit:
    @patch("src.crawlers.jumpit.client._JumpitCrawler.get")
    def test_saves_file_on_success(self, mock_get):
        detail_result = _make_detail_result(position_id=12345)
        list_result   = _make_list_result(
            positions=[_make_position(12345)],
            total_count=1,
            etc=False,
        )

        responses = [
            _mock_response(list_result),    # 목록 API
            _mock_response(detail_result),  # 상세 API
        ]
        mock_get.side_effect = responses

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_jumpit(
                query="1",
                crawl_date="2026-07-28",
                save_path=tmpdir,
            )

            assert result != ""
            saved = Path(result)
            assert saved.exists()
            # save_documents 는 문서당 1파일 — 반환 경로는 마지막 저장 파일
            doc = json.loads(saved.read_text(encoding="utf-8"))
            assert isinstance(doc, dict)
            assert doc["source_name"] == "jumpit"
            assert doc["source_job_id"] == "12345"
            assert doc["parse_status"] == "PENDING"
            saved_files = list(Path(tmpdir).rglob("*.json"))
            assert len(saved_files) == 1

    @patch("src.crawlers.jumpit.client._JumpitCrawler.get")
    def test_skips_already_saved_ids(self, mock_get):
        """이미 저장된 position_id는 상세 API를 호출하지 않는다."""
        list_result = _make_list_result(
            positions=[_make_position(99999)],
            total_count=1,
            etc=False,
        )
        mock_get.return_value = _mock_response(list_result)

        with tempfile.TemporaryDirectory() as tmpdir:
            # 미리 저장된 ID 세트를 갖도록 get_saved_ids 패치
            with patch(
                "src.crawlers.jumpit.client.get_saved_ids",
                return_value={("jumpit", "99999")},
            ):
                result = fetch_jumpit(
                    query="1",
                    crawl_date="2026-07-28",
                    save_path=tmpdir,
                )

        # 목록 API만 호출, 상세 API는 호출 없음
        assert mock_get.call_count == 1
        assert result == ""

    def test_returns_empty_for_unmapped_query(self):
        result = fetch_jumpit(query="NonExistentJobXYZ999")
        assert result == ""

    @patch("src.crawlers.jumpit.client.fetch_jumpit")
    def test_run_batch_calls_crawl_per_function(self, mock_crawl):
        mock_crawl.return_value = "/tmp/saved.json"
        functions = ["Backend Engineer", "Frontend Engineer"]
        run_jumpit_batch(functions, crawl_date="2026-07-28", save_dir="/tmp")
        assert mock_crawl.call_count == 2

    @patch("src.crawlers.jumpit.client.fetch_jumpit")
    def test_run_batch_continues_on_error(self, mock_crawl):
        """한 항목이 실패해도 나머지는 계속 진행한다."""
        mock_crawl.side_effect = [Exception("API 오류"), "/tmp/saved.json"]
        functions = ["Backend Engineer", "Frontend Engineer"]
        # 예외 없이 정상 종료해야 한다
        run_jumpit_batch(functions, crawl_date="2026-07-28", save_dir="/tmp")
        assert mock_crawl.call_count == 2

    @patch("src.crawlers.jumpit.client._JumpitCrawler.get")
    def test_max_jobs_limits_collection(self, mock_get):
        """max_jobs=1이면 첫 공고만 수집하고 중단한다."""
        positions = [_make_position(i) for i in range(1, 6)]
        list_result = _make_list_result(positions=positions, total_count=5, etc=True)
        detail_result = _make_detail_result(position_id=1)

        mock_get.side_effect = [
            _mock_response(list_result),
            _mock_response(detail_result),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = fetch_jumpit(
                query="1",
                crawl_date="2026-07-28",
                save_path=tmpdir,
                max_jobs=1,
            )

            assert result != ""
            saved_files = list(Path(tmpdir).rglob("*.json"))
            assert len(saved_files) == 1
            doc = json.loads(saved_files[0].read_text(encoding="utf-8"))
            assert doc["source_job_id"] == "1"
