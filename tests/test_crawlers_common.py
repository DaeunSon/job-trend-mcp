"""공통 크롤러 유틸 단위 테스트."""
from __future__ import annotations

from bs4 import BeautifulSoup

from src.crawlers.common import (
    build_crawl_filename,
    html_to_text,
    is_blocked,
    parse_total_count,
)
from src.crawlers.common.kr_search_queries import (
    KR_JOB_SEARCH_QUERIES,
    get_all_queries,
    get_queries_for_function,
)


class TestIsBlocked:
    def test_access_denied(self):
        assert is_blocked("<html>Access Denied</html>")

    def test_korean_signal(self):
        assert is_blocked("비정상 접근으로 차단")

    def test_normal(self):
        assert not is_blocked("<html><body>채용공고</body></html>")


class TestParseTotalCount:
    def test_selector(self):
        soup = BeautifulSoup(
            '<span class="cnt_result">총 1,234건</span>', "lxml"
        )
        assert parse_total_count(soup, selectors=("span.cnt_result",)) == 1234

    def test_text_fallback(self):
        soup = BeautifulSoup("<div>검색결과 총 56건 입니다</div>", "lxml")
        assert parse_total_count(soup) == 56


class TestBuildCrawlFilename:
    def test_slug(self):
        assert build_crawl_filename("saramin", "백엔드 개발자") == "saramin_백엔드_개발자"


class TestHtmlToText:
    def test_strips_tags(self):
        assert "hello" in html_to_text("<p>hello</p>")


class TestKrSearchQueries:
    def test_not_empty(self):
        assert len(KR_JOB_SEARCH_QUERIES) > 0

    def test_get_all_no_duplicates(self):
        qs = get_all_queries()
        assert len(qs) == len(set(qs))

    def test_backend_function(self):
        assert "백엔드 개발자" in get_queries_for_function("Backend Engineer")


class TestJsonApiCrawler:
    def test_collect_json_jobs_skips_saved_and_respects_max_jobs(self):
        from src.crawlers.common.json_api import JsonApiCrawler, PageCursor
        from src.models.schemas import RawJobPosting

        class _Fake(JsonApiCrawler):
            source_name = "fake"
            page_size = 2
            default_max_pages = 10

            def __init__(self):
                # BaseCrawler.__init__ 스킵 — 네트워크 불필요
                pass

            def fetch_list_page(self, cursor: PageCursor):
                return {"ids": [1, 2, 3]}

            def extract_ids(self, page_data):
                return list(page_data["ids"])

            def advance_cursor(self, cursor, page_data, ids):
                return None

            def fetch_detail_json(self, job_id: int):
                return {"id": job_id, "title": f"Job {job_id}"}

            def build_original_url(self, job_id: int):
                return f"https://example.com/{job_id}"

        crawler = _Fake()
        saved: set[tuple[str, str]] = {("fake", "1")}
        results = crawler.collect_json_jobs(
            PageCursor(),
            saved,
            max_pages=1,
            max_jobs=1,
        )
        assert len(results) == 1
        assert results[0].source_job_id == "2"
        assert isinstance(results[0], RawJobPosting)
