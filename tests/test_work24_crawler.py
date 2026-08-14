"""
crawlers/work24/crawler.py 유닛 테스트.
네트워크 호출은 unittest.mock 으로 패치한다.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.crawlers.work24.crawler import (
    _Work24Crawler,
    _is_blocked,
    _flatten_queries,
    crawl_work24,
    run_work24_batch,
)
from src.crawlers.work24.extractor import EXCLUDED_INFO_TYPE_CDS


# ---------------------------------------------------------------------------
# 헬퍼 / 픽스처
# ---------------------------------------------------------------------------

def _make_card(
    wanted_auth_no: str = "WK001",
    info_type_cd: str = "WK",
    title: str = "테스트 공고",
    company: str = "테스트 회사",
) -> dict:
    return {
        "wanted_auth_no": wanted_auth_no,
        "info_type_cd": info_type_cd,
        "info_type_group": "tb_workinfogubun",
        "title_raw": title,
        "company_raw": company,
        "detail_url": (
            f"https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do"
            f"?wantedAuthNo={wanted_auth_no}&infoTypeCd={info_type_cd}&infoTypeGroup=tb_workinfogubun"
        ),
        "provider_text": "",
    }


def _make_detail_html(title: str = "테스트 공고", company: str = "테스트 회사") -> str:
    return f"""
    <html><head><title>{title} | 고용24</title></head>
    <body>
      <h1 class="job-title">{title}</h1>
      <a class="cp-name">{company}</a>
      <table>
        <tr><th>급여</th><td>월급 300 만원</td></tr>
        <tr><th>경력</th><td>경력 3년 이상</td></tr>
        <tr><th>근무지역</th><td>서울특별시 강남구</td></tr>
        <tr><th>고용형태</th><td>기간의 정함이 없는 근로계약</td></tr>
        <tr><th>학력</th><td>대졸(4년)</td></tr>
        <tr><th>등록일</th><td>2026-07-01</td></tr>
        <tr><th>마감일</th><td>2026-08-31</td></tr>
      </table>
      <div id="duty_wrap">백엔드 개발 업무</div>
    </body></html>
    """


def _make_serp_html(cards: list[dict], total: int = 100) -> str:
    """검색 결과 목록 HTML 생성."""
    rows = ""
    for c in cards:
        rows += f"""
        <tr>
          <td>
            <strong class="cp_name">{c.get("company_raw", "")}</strong>
            <a href="/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo={c["wanted_auth_no"]}&infoTypeCd={c["info_type_cd"]}&infoTypeGroup=tb_workinfogubun">
              {c.get("title_raw", "공고")}
            </a>
          </td>
          <td>월급 300만원</td>
          <td>마감일 : 2026-08-31 등록일 : 2026-07-29</td>
        </tr>
        """
    return f"""
    <html><body>
      <span>검색건수 {total}건</span>
      <table><tbody>{rows}</tbody></table>
    </body></html>
    """


def _mock_response(html: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _is_blocked
# ---------------------------------------------------------------------------

class TestIsBlocked:
    def test_normal_html_not_blocked(self):
        assert _is_blocked("<html><body>공고 목록</body></html>") is False

    def test_access_denied_blocked(self):
        assert _is_blocked("Access Denied") is True

    def test_korean_block_signal(self):
        assert _is_blocked("비정상적인 접근이 감지되었습니다.") is True

    def test_just_a_moment_blocked(self):
        assert _is_blocked("Just a moment...") is True

    def test_case_insensitive(self):
        assert _is_blocked("JUST A MOMENT") is True


# ---------------------------------------------------------------------------
# _flatten_queries
# ---------------------------------------------------------------------------

class TestFlattenQueries:
    def test_deduplicates_queries(self):
        mapping = {
            "A": ["q1", "q2"],
            "B": ["q2", "q3"],
        }
        result = _flatten_queries(mapping)
        assert result == ["q1", "q2", "q3"]

    def test_empty_mapping(self):
        assert _flatten_queries({}) == []

    def test_preserves_order(self):
        mapping = {"A": ["q3", "q1", "q2"]}
        result = _flatten_queries(mapping)
        assert result == ["q3", "q1", "q2"]


# ---------------------------------------------------------------------------
# _Work24Crawler.fetch_serp
# ---------------------------------------------------------------------------

class TestFetchSerp:
    def test_returns_soup_on_success(self):
        html = _make_serp_html([_make_card()])
        resp = _mock_response(html)

        with patch.object(_Work24Crawler, "_wait"):
            crawler = _Work24Crawler.__new__(_Work24Crawler)
            crawler.timeout = (10, 30)
            crawler._session = MagicMock()
            crawler._session.post.return_value = resp
            crawler._session.get.return_value = resp
            crawler._robots_cache = {}
            crawler.source_name = "work24"

            result = crawler.fetch_serp("백엔드 개발자", 1)
            assert result is not None
            soup, text = result
            assert soup is not None
            assert "검색건수" in text

    def test_returns_none_on_block(self):
        resp = _mock_response("비정상적인 접근")

        with patch.object(_Work24Crawler, "_wait"):
            crawler = _Work24Crawler.__new__(_Work24Crawler)
            crawler.timeout = (10, 30)
            crawler._session = MagicMock()
            crawler._session.post.return_value = resp
            crawler._session.get.return_value = resp
            crawler._robots_cache = {}
            crawler.source_name = "work24"

            result = crawler.fetch_serp("백엔드 개발자", 1)
            assert result is None

    def test_falls_back_to_get_on_post_failure(self):
        import requests
        html = _make_serp_html([_make_card()])
        get_resp = _mock_response(html)

        with patch.object(_Work24Crawler, "_wait"):
            crawler = _Work24Crawler.__new__(_Work24Crawler)
            crawler.timeout = (10, 30)
            crawler._session = MagicMock()
            crawler._session.post.side_effect = requests.exceptions.RequestException("POST 실패")
            crawler._session.get.return_value = get_resp
            crawler._robots_cache = {}
            crawler.source_name = "work24"

            result = crawler.fetch_serp("백엔드 개발자", 1)
            assert result is not None

    def test_posts_src_keyword_as_search_filter(self):
        """keyword 단독이 아니라 srcKeyword 를 함께 전송해야 검색 필터가 적용된다."""
        html = _make_serp_html([_make_card()])
        resp = _mock_response(html)

        with patch.object(_Work24Crawler, "_wait"):
            crawler = _Work24Crawler.__new__(_Work24Crawler)
            crawler.timeout = (10, 30)
            crawler._session = MagicMock()
            crawler._session.post.return_value = resp
            crawler._robots_cache = {}
            crawler.source_name = "work24"

            crawler.fetch_serp("개발자", 1)

        _, kwargs = crawler._session.post.call_args
        form_data = kwargs["data"]
        assert form_data["srcKeyword"] == "개발자"
        assert form_data["keyword"] == "개발자"
        assert form_data["keywordWantedTitle"] == "Y"
        assert form_data["keywordJobCont"] == "Y"


# ---------------------------------------------------------------------------
# _Work24Crawler.collect_jobs (정보제공처 필터링 검증)
# ---------------------------------------------------------------------------

class TestCollectJobsSourceFiltering:
    """사람인/잡코리아/원티드 출처 공고가 실제로 건너뛰어지는지 검증."""

    def _setup_crawler(self) -> _Work24Crawler:
        crawler = _Work24Crawler.__new__(_Work24Crawler)
        crawler.timeout = (10, 30)
        crawler.retry_count = 1
        crawler.rate_limit_min = 0
        crawler.rate_limit_max = 0
        crawler._session = MagicMock()
        crawler._robots_cache = {}
        crawler.source_name = "work24"
        return crawler

    def test_excluded_source_skipped(self):
        """사람인(CSI) 출처 공고는 수집되지 않는다."""
        cards = [
            _make_card("SARAMIN001", "CSI", "사람인 공고"),
            _make_card("WK001", "WK", "고용24 공고"),
        ]
        serp_html = _make_serp_html(cards, total=2)
        detail_html = _make_detail_html()

        serp_resp = _mock_response(serp_html)
        detail_resp = _mock_response(detail_html)

        crawler = self._setup_crawler()
        crawler._session.post.return_value = serp_resp
        crawler._session.get.return_value = detail_resp

        with patch.object(crawler, "_wait"):
            collected = crawler.collect_jobs("테스트", saved_ids=set(), max_pages=1)

        ids = [d["source_job_id"] for d in collected]
        assert "SARAMIN001" not in ids, "사람인 공고가 수집되면 안 됨"
        assert "WK001" in ids, "고용24 공고는 수집되어야 함"

    def test_jobkorea_excluded(self):
        """잡코리아(CJK) 출처 공고는 수집되지 않는다."""
        cards = [_make_card("JK001", "CJK")]
        serp_html = _make_serp_html(cards, total=1)

        crawler = self._setup_crawler()
        crawler._session.post.return_value = _mock_response(serp_html)
        crawler._session.get.return_value = _mock_response(_make_detail_html())

        with patch.object(crawler, "_wait"):
            collected = crawler.collect_jobs("테스트", saved_ids=set(), max_pages=1)

        assert len(collected) == 0

    def test_wanted_excluded(self):
        """원티드(CWT) 출처 공고는 수집되지 않는다."""
        cards = [_make_card("WT001", "CWT")]
        serp_html = _make_serp_html(cards, total=1)

        crawler = self._setup_crawler()
        crawler._session.post.return_value = _mock_response(serp_html)
        crawler._session.get.return_value = _mock_response(_make_detail_html())

        with patch.object(crawler, "_wait"):
            collected = crawler.collect_jobs("테스트", saved_ids=set(), max_pages=1)

        assert len(collected) == 0

    def test_already_saved_skipped(self):
        """이미 저장된 (source_name, source_job_id) 는 건너뛴다."""
        cards = [_make_card("WK001", "WK")]
        serp_html = _make_serp_html(cards, total=1)

        crawler = self._setup_crawler()
        crawler._session.post.return_value = _mock_response(serp_html)
        crawler._session.get.return_value = _mock_response(_make_detail_html())

        # 이미 저장된 ID
        saved_ids = {("work24", "WK001")}

        with patch.object(crawler, "_wait"):
            collected = crawler.collect_jobs("테스트", saved_ids=saved_ids, max_pages=1)

        assert len(collected) == 0

    def test_new_card_added_to_saved_ids(self):
        """새로 수집된 공고는 saved_ids 에 추가된다."""
        cards = [_make_card("WK_NEW", "WK")]
        serp_html = _make_serp_html(cards, total=1)

        crawler = self._setup_crawler()
        crawler._session.post.return_value = _mock_response(serp_html)
        crawler._session.get.return_value = _mock_response(_make_detail_html())

        saved_ids: set = set()
        with patch.object(crawler, "_wait"):
            crawler.collect_jobs("테스트", saved_ids=saved_ids, max_pages=1)

        assert ("work24", "WK_NEW") in saved_ids

    def test_raw_text_contains_card_meta(self):
        """수집된 raw_text 에 카드 메타(search_query, card_meta)가 포함된다."""
        cards = [_make_card("WK_META", "WK")]
        serp_html = _make_serp_html(cards, total=1)

        crawler = self._setup_crawler()
        crawler._session.post.return_value = _mock_response(serp_html)
        crawler._session.get.return_value = _mock_response(_make_detail_html())

        with patch.object(crawler, "_wait"):
            collected = crawler.collect_jobs("백엔드 개발자", saved_ids=set(), max_pages=1)

        assert len(collected) == 1
        raw_meta = json.loads(collected[0]["raw_text"])
        assert raw_meta["search_query"] == "백엔드 개발자"
        assert raw_meta["card_meta"]["wanted_auth_no"] == "WK_META"

    def test_detail_failure_skips_card(self):
        """상세 페이지 수집 실패(None)면 해당 공고는 건너뛴다."""
        cards = [_make_card("WK_FAIL", "WK")]
        serp_html = _make_serp_html(cards, total=1)

        crawler = self._setup_crawler()
        crawler._session.post.return_value = _mock_response(serp_html)
        crawler._session.get.side_effect = Exception("네트워크 오류")

        with patch.object(crawler, "_wait"):
            collected = crawler.collect_jobs("테스트", saved_ids=set(), max_pages=1)

        assert len(collected) == 0

    def test_multiple_pages_collected(self):
        """페이지 2개에서 공고가 누적된다."""
        cards_p1 = [_make_card(f"WK_P1_{i}", "WK") for i in range(2)]
        cards_p2 = [_make_card(f"WK_P2_{i}", "WK") for i in range(2)]

        # total=20 → ceil(20/10)=2페이지 계산 → 2번째 페이지도 요청됨
        serp_p1 = _make_serp_html(cards_p1, total=20)
        serp_p2 = _make_serp_html(cards_p2, total=20)
        detail_html = _make_detail_html()

        call_count = {"post": 0}

        def _post_side_effect(url, **kwargs):
            call_count["post"] += 1
            if call_count["post"] == 1:
                return _mock_response(serp_p1)
            return _mock_response(serp_p2)

        crawler = self._setup_crawler()
        crawler._session.post.side_effect = _post_side_effect
        crawler._session.get.return_value = _mock_response(detail_html)

        with patch.object(crawler, "_wait"):
            collected = crawler.collect_jobs("테스트", saved_ids=set(), max_pages=2)

        assert len(collected) == 4


# ---------------------------------------------------------------------------
# crawl_work24 (공개 함수 통합 테스트)
# ---------------------------------------------------------------------------

class TestCrawlWork24:
    def test_returns_empty_string_when_no_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch(
                    "src.crawlers.work24.crawler.get_saved_ids",
                    return_value=set(),
                ),
                patch(
                    "src.crawlers.work24.crawler._Work24Crawler.collect_jobs",
                    return_value=[],
                ),
            ):
                result = crawl_work24(query="없는검색어", save_path=tmpdir)
                assert result == ""

    def test_returns_filepath_when_collected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_docs = [
                {
                    "source_name": "work24",
                    "source_job_id": "WK001",
                    "id": "uuid-001",
                    "collected_at": "2026-07-29T00:00:00+00:00",
                }
            ]
            with (
                patch(
                    "src.crawlers.work24.crawler.get_saved_ids",
                    return_value=set(),
                ),
                patch(
                    "src.crawlers.work24.crawler._Work24Crawler.collect_jobs",
                    return_value=fake_docs,
                ),
            ):
                result = crawl_work24(
                    query="백엔드 개발자",
                    crawl_date="2026-07-29",
                    save_path=tmpdir,
                )
                assert result != ""
                assert Path(result).exists()


# ---------------------------------------------------------------------------
# run_work24_batch (공개 함수 통합 테스트)
# ---------------------------------------------------------------------------

class TestRunWork24Batch:
    def test_calls_crawl_for_each_query(self):
        call_log: list[str] = []

        def _mock_crawl(query=None, **kwargs):
            call_log.append(query)
            return ""

        with (
            patch("src.crawlers.work24.crawler.crawl_work24", side_effect=_mock_crawl),
            patch("src.crawlers.work24.crawler.time.sleep"),
        ):
            run_work24_batch(
                job_functions=["Backend Engineer"],
            )

        from src.crawlers.work24.search_queries import get_queries_for_function
        expected = get_queries_for_function("Backend Engineer")
        for q in expected:
            assert q in call_log

    def test_partial_failure_continues(self):
        """한 검색어가 예외를 발생시켜도 나머지는 계속 실행된다."""
        call_log: list[str] = []
        fail_once = {"done": False}

        def _mock_crawl(query=None, **kwargs):
            if not fail_once["done"] and query == "백엔드 개발자":
                fail_once["done"] = True
                raise RuntimeError("의도적 실패")
            call_log.append(query)
            return ""

        with (
            patch("src.crawlers.work24.crawler.crawl_work24", side_effect=_mock_crawl),
            patch("src.crawlers.work24.crawler.time.sleep"),
        ):
            # 예외가 전파되지 않아야 함
            run_work24_batch(job_functions=["Backend Engineer"])

        # 실패한 쿼리 이외에 나머지가 실행됐는지 확인
        from src.crawlers.work24.search_queries import get_queries_for_function
        queries = get_queries_for_function("Backend Engineer")
        if len(queries) > 1:
            assert len(call_log) > 0

    def test_no_job_functions_uses_all_queries(self):
        """job_functions=None 이면 전체 taxonomy 검색어를 사용한다."""
        from src.crawlers.work24.search_queries import get_all_queries
        all_q = get_all_queries()

        call_log: list[str] = []

        def _mock_crawl(query=None, **kwargs):
            call_log.append(query)
            return ""

        with (
            patch("src.crawlers.work24.crawler.crawl_work24", side_effect=_mock_crawl),
            patch("src.crawlers.work24.crawler.time.sleep"),
        ):
            run_work24_batch(job_functions=None)

        assert set(call_log) == set(all_q)
