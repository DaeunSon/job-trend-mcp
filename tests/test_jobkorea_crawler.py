"""
crawlers/jobkorea/crawler.py 유닛 테스트.
네트워크 호출은 unittest.mock으로 패치한다.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.crawlers.jobkorea.crawler import (
    _build_filename,
    _extract_job_id_from_card,
    _is_blocked,
    crawl_jobkorea,
    run_jobkorea_batch,
    _JobkoreaCrawler,
)
from src.crawlers.jobkorea.search_queries import (
    get_all_queries,
    get_queries_for_function,
)
from bs4 import BeautifulSoup


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# _build_filename
# ---------------------------------------------------------------------------

class TestBuildFilename:
    def test_spaces_replaced(self):
        assert _build_filename("백엔드 개발자") == "jobkorea_백엔드_개발자"

    def test_single_word(self):
        assert _build_filename("DevOps") == "jobkorea_DevOps"

    def test_prefix_present(self):
        assert _build_filename("anything").startswith("jobkorea_")


# ---------------------------------------------------------------------------
# _is_blocked
# ---------------------------------------------------------------------------

class TestIsBlocked:
    def test_access_denied(self):
        assert _is_blocked("<html><body>Access Denied</body></html>")

    def test_human_verification(self):
        assert _is_blocked("human verification required")

    def test_normal_page(self):
        assert not _is_blocked("<html><body><h1>백엔드 개발자 모집</h1></body></html>")

    def test_empty(self):
        assert not _is_blocked("")

    def test_case_insensitive(self):
        assert _is_blocked("JUST A MOMENT")


# ---------------------------------------------------------------------------
# _extract_job_id_from_card
# ---------------------------------------------------------------------------

class TestExtractJobIdFromCard:
    def test_data_gno_attribute(self):
        card = _soup('<li data-gno="24115438"><a href="#">공고</a></li>').select_one("li")
        assert _extract_job_id_from_card(card) == "24115438"

    def test_gi_read_href(self):
        card = _soup(
            '<div><a href="/Recruit/GI_Read/99887766">공고제목</a></div>'
        ).select_one("div")
        assert _extract_job_id_from_card(card) == "99887766"

    def test_no_id_returns_none(self):
        card = _soup('<div><a href="/about">소개</a></div>').select_one("div")
        assert _extract_job_id_from_card(card) is None

    def test_non_digit_data_gno_ignored(self):
        card = _soup('<li data-gno="abc"><a href="#">공고</a></li>').select_one("li")
        assert _extract_job_id_from_card(card) is None


# ---------------------------------------------------------------------------
# extract_job_cards
# ---------------------------------------------------------------------------

class TestExtractJobCards:
    # 실제 잡코리아 SERP 구조 (2026년 기준 — Next.js + Tailwind CSS)
    _CARD_HTML = """
    <html><body>
      <div data-sentry-component="CardJob">
        <a href="https://www.jobkorea.co.kr/Recruit/GI_Read/11111111?listno=1"
           data-sentry-component="Title">
          <span class="truncate">백엔드 개발자</span>
        </a>
        <span class="text-typo-b2-16">카카오</span>
        <div data-sentry-component="GrayChip">
          <span class="truncate">서울 강남구</span>
        </div>
        <div data-sentry-component="GrayChip">
          <span class="truncate">IT·인터넷, 백엔드개발자</span>
        </div>
        <span class="text-typo-c1-13">경력 3년 이상</span>
      </div>
    </body></html>
    """

    def test_extracts_from_card_job(self):
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        cards = crawler.extract_job_cards(_soup(self._CARD_HTML))
        assert len(cards) == 1
        assert cards[0]["job_id"] == "11111111"
        assert cards[0]["title"] == "백엔드 개발자"
        assert cards[0]["company"] == "카카오"
        assert cards[0]["location"] == "서울 강남구"
        assert cards[0]["career_type"] == "경력 3년 이상"

    def test_deduplication(self):
        html = """
        <html><body>
          <div data-sentry-component="CardJob">
            <a href="/Recruit/GI_Read/22222222?listno=1" data-sentry-component="Title">
              <span>공고A</span></a>
            <span class="text-typo-b2-16">회사A</span>
          </div>
          <div data-sentry-component="CardJob">
            <a href="/Recruit/GI_Read/22222222?listno=2" data-sentry-component="Title">
              <span>공고A 중복</span></a>
            <span class="text-typo-b2-16">회사A</span>
          </div>
        </body></html>
        """
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        cards = crawler.extract_job_cards(_soup(html))
        assert len(cards) == 1

    def test_fallback_to_old_structure(self):
        """구 HTML 구조(data-gno)도 처리 가능한지 확인."""
        html = """
        <html><body>
          <li data-gno="33333333">
            <a href="/Recruit/GI_Read/33333333">구 구조 공고</a>
          </li>
        </body></html>
        """
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        cards = crawler.extract_job_cards(_soup(html))
        assert len(cards) == 1
        assert cards[0]["job_id"] == "33333333"

    def test_empty_serp(self):
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        cards = crawler.extract_job_cards(_soup("<html><body><p>결과 없음</p></body></html>"))
        assert cards == []


# ---------------------------------------------------------------------------
# get_total_count
# ---------------------------------------------------------------------------

class TestGetTotalCount:
    def test_korean_total_pattern(self):
        html = "<html><body><p>총 1,234건의 채용공고</p></body></html>"
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        assert crawler.get_total_count(_soup(html)) == 1234

    def test_recruit_totalNum_selector(self):
        html = '<html><body><span class="recruit-totalNum">567</span></body></html>'
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        assert crawler.get_total_count(_soup(html)) == 567

    def test_returns_zero_when_not_found(self):
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        assert crawler.get_total_count(_soup("<html><body><p>no results</p></body></html>")) == 0


# ---------------------------------------------------------------------------
# crawl_jobkorea (mock)
# ---------------------------------------------------------------------------

class TestCrawlJobkorea:
    def test_empty_query_raises(self):
        with pytest.raises(ValueError, match="query"):
            crawl_jobkorea("")

    def test_whitespace_query_raises(self):
        with pytest.raises(ValueError):
            crawl_jobkorea("   ")

    def test_returns_empty_when_no_new_docs(self, tmp_path):
        mock_crawler = MagicMock()
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)
        # collect_jobs_paged는 generator — 빈 배치를 yield하는 이터러블로 모킹
        mock_crawler.collect_jobs_paged.return_value = iter([[]])

        with patch("src.crawlers.jobkorea.crawler._JobkoreaCrawler", return_value=mock_crawler):
            result = crawl_jobkorea(
                query="백엔드 개발자",
                crawl_date="2026-07-27",
                save_path=str(tmp_path),
            )
        assert result == ""

    def test_saves_and_returns_path(self, tmp_path):
        from src.models.schemas import RawJobPosting

        fake_raw = RawJobPosting(
            source_name="jobkorea",
            source_job_id="24115438",
            original_url="https://www.jobkorea.co.kr/Recruit/GI_Read/24115438",
            raw_html="<html><body>백엔드 개발자 모집</body></html>",
            raw_text="백엔드 개발자 모집",
        )
        mock_crawler = MagicMock()
        mock_crawler.__enter__ = MagicMock(return_value=mock_crawler)
        mock_crawler.__exit__ = MagicMock(return_value=False)
        # collect_jobs_paged는 generator — 한 페이지 배치를 yield하는 이터러블로 모킹
        mock_crawler.collect_jobs_paged.return_value = iter([[fake_raw]])

        with patch("src.crawlers.jobkorea.crawler._JobkoreaCrawler", return_value=mock_crawler):
            result = crawl_jobkorea(
                query="백엔드 개발자",
                crawl_date="2026-07-27",
                save_path=str(tmp_path),
            )

        assert result != ""
        assert Path(result).exists()
        assert Path(result).suffix == ".json"


# ---------------------------------------------------------------------------
# run_jobkorea_batch
# ---------------------------------------------------------------------------

class TestRunJobkoreaBatch:
    def test_empty_list_no_error(self, tmp_path):
        run_jobkorea_batch(job_functions=[], save_dir=str(tmp_path))

    def test_partial_failure_continues(self, tmp_path):
        call_count = 0

        def fake_crawl(query, crawl_date=None, save_path=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if query == "실패_검색어":
                raise RuntimeError("의도적 실패")
            return ""

        with patch("src.crawlers.jobkorea.crawler.crawl_jobkorea", side_effect=fake_crawl):
            with patch("src.crawlers.common.batch.time.sleep"):
                run_jobkorea_batch(
                    job_functions=["백엔드 개발자", "실패_검색어", "데이터 분석가"],
                    save_dir=str(tmp_path),
                )
        assert call_count == 3


# ---------------------------------------------------------------------------
# collect_jobs — 증분 수집 동작 확인
# ---------------------------------------------------------------------------

class TestCollectJobsIncremental:
    """incremental 플래그에 따른 중단/계속 동작을 검증한다."""

    def _make_cards(self, job_ids: list[str]) -> list[dict]:
        return [
            {
                "job_id": jid,
                "title": f"공고{jid}",
                "company": "테스트",
                "location": "서울",
                "career_type": "경력",
                "education": "",
                "deadline": "",
                "detail_url": f"https://www.jobkorea.co.kr/Recruit/GI_Read/{jid}",
            }
            for jid in job_ids
        ]

    def test_incremental_stops_on_first_duplicate(self):
        """최신순 페이지 1에서 이미 저장된 job_id를 만나면 즉시 중단한다."""
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        crawler._session = MagicMock()

        page1_cards = self._make_cards(["99999", "88888", "77777"])
        saved_ids: set[tuple[str, str]] = {("jobkorea", "88888")}  # 88888은 기존 공고

        def fake_fetch_serp(query, page):
            if page == 1:
                return MagicMock()  # soup (내용 무관 — extract_job_cards 패치)
            return None

        def fake_extract(soup):
            return page1_cards

        def fake_get_total_count(soup):
            return 60  # 3페이지 분량

        def fake_fetch_detail(job_id, query):
            return f"<html>{job_id}</html>", job_id

        crawler.fetch_serp = fake_fetch_serp
        crawler.extract_job_cards = fake_extract
        crawler.get_total_count = fake_get_total_count
        crawler.fetch_detail = fake_fetch_detail

        results = crawler.collect_jobs(
            query="테스트",
            saved_ids=saved_ids,
            incremental=True,
        )
        # 99999만 수집, 88888에서 중단 → 77777은 수집하지 않음
        collected_ids = {r.source_job_id for r in results}
        assert "99999" in collected_ids
        assert "88888" not in collected_ids
        assert "77777" not in collected_ids

    def test_full_mode_skips_but_continues(self):
        """incremental=False 이면 기존 공고를 건너뛰되 중단하지 않는다."""
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        crawler._session = MagicMock()

        page1_cards = self._make_cards(["99999", "88888", "77777"])
        saved_ids: set[tuple[str, str]] = {("jobkorea", "88888")}

        def fake_fetch_serp(query, page):
            if page == 1:
                return MagicMock()
            return None

        def fake_extract(soup):
            return page1_cards

        def fake_get_total_count(soup):
            return 60

        def fake_fetch_detail(job_id, query):
            return f"<html>{job_id}</html>", job_id

        crawler.fetch_serp = fake_fetch_serp
        crawler.extract_job_cards = fake_extract
        crawler.get_total_count = fake_get_total_count
        crawler.fetch_detail = fake_fetch_detail

        results = crawler.collect_jobs(
            query="테스트",
            saved_ids=saved_ids,
            incremental=False,
        )
        collected_ids = {r.source_job_id for r in results}
        assert "99999" in collected_ids
        assert "88888" not in collected_ids  # 중복이므로 건너뜀
        assert "77777" in collected_ids      # 중단 없이 계속 수집

    def test_incremental_collects_all_when_no_duplicates(self):
        """기존 공고가 없으면 증분 모드에서도 모두 수집한다."""
        crawler = _JobkoreaCrawler.__new__(_JobkoreaCrawler)
        crawler._session = MagicMock()

        page1_cards = self._make_cards(["111", "222", "333"])
        saved_ids: set[tuple[str, str]] = set()

        def fake_fetch_serp(query, page):
            return MagicMock() if page == 1 else None

        def fake_extract(soup):
            return page1_cards

        def fake_get_total_count(soup):
            return 3

        def fake_fetch_detail(job_id, query):
            return f"<html>{job_id}</html>", job_id

        crawler.fetch_serp = fake_fetch_serp
        crawler.extract_job_cards = fake_extract
        crawler.get_total_count = fake_get_total_count
        crawler.fetch_detail = fake_fetch_detail

        results = crawler.collect_jobs(
            query="테스트",
            saved_ids=saved_ids,
            incremental=True,
        )
        assert len(results) == 3


# ---------------------------------------------------------------------------
# search_queries
# ---------------------------------------------------------------------------

class TestSearchQueries:
    def test_no_duplicates(self):
        queries = get_all_queries()
        assert len(queries) == len(set(queries))

    def test_not_empty(self):
        assert len(get_all_queries()) > 0

    def test_korean_queries_present(self):
        queries = get_all_queries()
        assert any("개발자" in q for q in queries)

    def test_known_function(self):
        queries = get_queries_for_function("Backend Engineer")
        assert any("백엔드" in q for q in queries)

    def test_unknown_function(self):
        assert get_queries_for_function("Unknown XYZ") == []
