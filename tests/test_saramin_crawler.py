"""
crawlers/saramin/crawler.py 유닛 테스트.
네트워크 호출은 unittest.mock으로 패치한다.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from bs4 import BeautifulSoup

from src.crawlers.saramin.crawler import (
    _build_filename,
    _build_detail_url,
    _extract_rec_idx_from_card,
    _extract_title_from_card,
    _extract_company_from_card,
    _extract_conditions_from_card,
    _extract_deadline_from_card,
    _assign_conditions,
    _is_blocked,
    crawl_saramin,
    run_saramin_batch,
    _SaraminCrawler,
)
from src.crawlers.saramin.search_queries import (
    get_all_queries,
    get_queries_for_function,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# _build_filename
# ---------------------------------------------------------------------------

class TestBuildFilename:
    def test_spaces_replaced(self):
        assert _build_filename("백엔드 개발자") == "saramin_백엔드_개발자"

    def test_single_word(self):
        assert _build_filename("DevOps") == "saramin_DevOps"

    def test_prefix_present(self):
        assert _build_filename("anything").startswith("saramin_")

    def test_multiple_spaces(self):
        assert _build_filename("AI 엔지니어 채용") == "saramin_AI_엔지니어_채용"


# ---------------------------------------------------------------------------
# _build_detail_url
# ---------------------------------------------------------------------------

class TestBuildDetailUrl:
    def test_url_format(self):
        url = _build_detail_url("49283710")
        assert "saramin.co.kr" in url
        assert "rec_idx=49283710" in url

    def test_different_ids(self):
        url1 = _build_detail_url("11111111")
        url2 = _build_detail_url("22222222")
        assert "11111111" in url1
        assert "22222222" in url2
        assert url1 != url2


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

    def test_korean_block_signal(self):
        assert _is_blocked("비정상적인 접근이 감지되었습니다.")

    def test_비정상_접근(self):
        assert _is_blocked("비정상 접근으로 인해 차단되었습니다.")


# ---------------------------------------------------------------------------
# _extract_rec_idx_from_card
# ---------------------------------------------------------------------------

class TestExtractRecIdx:
    def test_data_rec_idx_attribute(self):
        card = _soup('<article data-rec-idx="49283710"><a href="#">공고</a></article>').select_one("article")
        assert _extract_rec_idx_from_card(card) == "49283710"

    def test_href_rec_idx_pattern(self):
        card = _soup(
            '<div><a href="/zf_user/jobs/relay/view?rec_idx=99887766">공고제목</a></div>'
        ).select_one("div")
        assert _extract_rec_idx_from_card(card) == "99887766"

    def test_href_with_extra_params(self):
        card = _soup(
            '<div><a href="/zf_user/jobs/relay/view?rec_idx=12345678&amp;listno=1">공고</a></div>'
        ).select_one("div")
        assert _extract_rec_idx_from_card(card) == "12345678"

    def test_no_id_returns_none(self):
        card = _soup('<div><a href="/about">소개</a></div>').select_one("div")
        assert _extract_rec_idx_from_card(card) is None

    def test_non_digit_data_attr_ignored(self):
        card = _soup('<article data-rec-idx="abc"><a href="#">공고</a></article>').select_one("article")
        assert _extract_rec_idx_from_card(card) is None

    def test_data_position_idx(self):
        card = _soup('<article data-position-idx="55667788"><a href="#">공고</a></article>').select_one("article")
        assert _extract_rec_idx_from_card(card) == "55667788"


# ---------------------------------------------------------------------------
# _extract_title_from_card
# ---------------------------------------------------------------------------

class TestExtractTitleFromCard:
    def test_str_tit_span(self):
        card = _soup(
            '<article><a class="str-tit" href="#"><span class="tit">백엔드 개발자 채용</span></a></article>'
        ).select_one("article")
        assert _extract_title_from_card(card) == "백엔드 개발자 채용"

    def test_str_tit_no_span(self):
        card = _soup(
            '<article><a class="str-tit" href="#">프론트엔드 개발자</a></article>'
        ).select_one("article")
        assert _extract_title_from_card(card) == "프론트엔드 개발자"

    def test_job_tit_fallback(self):
        card = _soup(
            '<article><div class="job-tit"><a href="#">데이터 엔지니어</a></div></article>'
        ).select_one("article")
        assert _extract_title_from_card(card) == "데이터 엔지니어"

    def test_no_title_returns_empty(self):
        card = _soup('<article><p>내용 없음</p></article>').select_one("article")
        assert _extract_title_from_card(card) == ""


# ---------------------------------------------------------------------------
# _extract_company_from_card
# ---------------------------------------------------------------------------

class TestExtractCompanyFromCard:
    def test_strong_corp_name_a(self):
        card = _soup(
            '<article><strong class="corp-name"><a href="#">(주)카카오</a></strong></article>'
        ).select_one("article")
        assert _extract_company_from_card(card) == "(주)카카오"

    def test_str_co_fallback(self):
        card = _soup(
            '<article><a class="str-co" href="#">네이버</a></article>'
        ).select_one("article")
        assert _extract_company_from_card(card) == "네이버"

    def test_no_company_returns_empty(self):
        card = _soup('<article><p>회사 정보 없음</p></article>').select_one("article")
        assert _extract_company_from_card(card) == ""


# ---------------------------------------------------------------------------
# _assign_conditions
# ---------------------------------------------------------------------------

class TestAssignConditions:
    def test_location_detected(self):
        loc, career, edu, emp = _assign_conditions(["서울 강남구", "경력 3~5년", "대졸", "정규직"])
        assert loc == "서울 강남구"

    def test_career_detected(self):
        loc, career, edu, emp = _assign_conditions(["서울 강남구", "경력 3~5년", "대졸", "정규직"])
        assert career == "경력 3~5년"

    def test_education_detected(self):
        loc, career, edu, emp = _assign_conditions(["서울 강남구", "경력 3~5년", "대졸", "정규직"])
        assert edu == "대졸"

    def test_employment_type_detected(self):
        loc, career, edu, emp = _assign_conditions(["서울 강남구", "경력 3~5년", "대졸", "정규직"])
        assert emp == "정규직"

    def test_entry_level(self):
        _, career, _, _ = _assign_conditions(["서울", "신입", "학력무관", "계약직"])
        assert career == "신입"

    def test_contract_employment(self):
        _, _, _, emp = _assign_conditions(["경기 성남시", "경력무관", "고졸", "계약직"])
        assert emp == "계약직"

    def test_empty_list(self):
        loc, career, edu, emp = _assign_conditions([])
        assert loc == career == edu == emp == ""

    def test_partial_list(self):
        loc, career, edu, emp = _assign_conditions(["서울", "신입"])
        assert loc == "서울"
        assert career == "신입"

    def test_intern_employment(self):
        _, _, _, emp = _assign_conditions(["서울", "신입", "대졸", "인턴직"])
        assert emp == "인턴직"

    def test_경기_region(self):
        loc, _, _, _ = _assign_conditions(["경기 수원시", "경력 1~3년", "대졸", "정규직"])
        assert loc == "경기 수원시"


# ---------------------------------------------------------------------------
# _extract_deadline_from_card
# ---------------------------------------------------------------------------

class TestExtractDeadline:
    def test_dday_format(self):
        card = _soup(
            '<article><div class="deadlines"><span class="date">D-15</span></div></article>'
        ).select_one("article")
        assert _extract_deadline_from_card(card) == "D-15"

    def test_date_format(self):
        card = _soup(
            '<article><span class="date">2026.08.31</span></article>'
        ).select_one("article")
        assert "2026" in _extract_deadline_from_card(card)

    def test_no_deadline(self):
        card = _soup('<article><p>마감일 정보 없음</p></article>').select_one("article")
        assert _extract_deadline_from_card(card) == ""


# ---------------------------------------------------------------------------
# extract_job_cards (SERP HTML 전체 구조 테스트)
# ---------------------------------------------------------------------------

class TestExtractJobCards:
    # 사람인 SERP 카드 구조 (article.list-post)
    _SERP_HTML = """
    <html><body>
      <div class="list-recruit">
        <article class="list-post" data-rec-idx="49283710">
          <div class="box-item">
            <div class="col-header">
              <a href="/zf_user/jobs/relay/view?rec_idx=49283710&amp;listno=1" class="str-tit">
                <span class="tit">백엔드 개발자 (Python)</span>
              </a>
            </div>
            <div class="col-mid">
              <strong class="corp-name"><a href="/zf_user/company-info/view?csn=123">카카오</a></strong>
              <dl class="job-condition">
                <dd><span>서울 강남구</span></dd>
                <dd><span>경력 3~5년</span></dd>
                <dd><span>대졸</span></dd>
                <dd><span>정규직</span></dd>
              </dl>
            </div>
            <div class="col-right">
              <div class="deadlines"><span class="date">D-10</span></div>
            </div>
          </div>
        </article>
        <article class="list-post" data-rec-idx="87654321">
          <div class="box-item">
            <div class="col-header">
              <a href="/zf_user/jobs/relay/view?rec_idx=87654321" class="str-tit">
                <span class="tit">프론트엔드 개발자</span>
              </a>
            </div>
            <div class="col-mid">
              <strong class="corp-name"><a href="#">네이버</a></strong>
              <dl class="job-condition">
                <dd><span>경기 성남시</span></dd>
                <dd><span>신입</span></dd>
                <dd><span>학력무관</span></dd>
                <dd><span>계약직</span></dd>
              </dl>
            </div>
            <div class="col-right">
              <div class="deadlines"><span class="date">상시채용</span></div>
            </div>
          </div>
        </article>
      </div>
    </html></body>
    """

    def _make_crawler(self) -> _SaraminCrawler:
        with patch.object(_SaraminCrawler, "__init__", lambda self: None):
            crawler = _SaraminCrawler.__new__(_SaraminCrawler)
        return crawler

    def test_two_cards_extracted(self):
        crawler = self._make_crawler()
        soup = _soup(self._SERP_HTML)
        cards = crawler.extract_job_cards(soup)
        assert len(cards) == 2

    def test_first_card_rec_idx(self):
        crawler = self._make_crawler()
        soup = _soup(self._SERP_HTML)
        cards = crawler.extract_job_cards(soup)
        assert cards[0]["rec_idx"] == "49283710"

    def test_first_card_title(self):
        crawler = self._make_crawler()
        soup = _soup(self._SERP_HTML)
        cards = crawler.extract_job_cards(soup)
        assert cards[0]["title"] == "백엔드 개발자 (Python)"

    def test_first_card_company(self):
        crawler = self._make_crawler()
        soup = _soup(self._SERP_HTML)
        cards = crawler.extract_job_cards(soup)
        assert cards[0]["company"] == "카카오"

    def test_first_card_location(self):
        crawler = self._make_crawler()
        soup = _soup(self._SERP_HTML)
        cards = crawler.extract_job_cards(soup)
        assert "서울" in cards[0]["location"]

    def test_first_card_career(self):
        crawler = self._make_crawler()
        soup = _soup(self._SERP_HTML)
        cards = crawler.extract_job_cards(soup)
        assert "경력" in cards[0]["career_type"]

    def test_first_card_employment_type(self):
        crawler = self._make_crawler()
        soup = _soup(self._SERP_HTML)
        cards = crawler.extract_job_cards(soup)
        assert "정규직" in cards[0]["employment_type"]

    def test_second_card_rec_idx(self):
        crawler = self._make_crawler()
        soup = _soup(self._SERP_HTML)
        cards = crawler.extract_job_cards(soup)
        assert cards[1]["rec_idx"] == "87654321"

    def test_no_duplicate_rec_idx(self):
        """동일한 rec_idx 카드가 중복 추출되지 않아야 한다."""
        html = self._SERP_HTML.replace(
            'data-rec-idx="87654321"', 'data-rec-idx="49283710"'
        )
        crawler = self._make_crawler()
        soup = _soup(html)
        cards = crawler.extract_job_cards(soup)
        rec_idxs = [c["rec_idx"] for c in cards]
        assert len(rec_idxs) == len(set(rec_idxs))

    def test_empty_serp_returns_empty_list(self):
        crawler = self._make_crawler()
        soup = _soup("<html><body><p>검색 결과 없음</p></body></html>")
        cards = crawler.extract_job_cards(soup)
        assert cards == []


# ---------------------------------------------------------------------------
# get_total_count
# ---------------------------------------------------------------------------

class TestGetTotalCount:
    def _make_crawler(self) -> _SaraminCrawler:
        with patch.object(_SaraminCrawler, "__init__", lambda self: None):
            crawler = _SaraminCrawler.__new__(_SaraminCrawler)
        return crawler

    def test_cnt_all_em(self):
        soup = _soup('<html><body><div class="cnt-all"><em>1,234</em></div></body></html>')
        crawler = self._make_crawler()
        assert crawler.get_total_count(soup) == 1234

    def test_fallback_총_n건(self):
        soup = _soup("<html><body><p>총 567건의 채용공고가 있습니다.</p></body></html>")
        crawler = self._make_crawler()
        assert crawler.get_total_count(soup) == 567

    def test_no_count_returns_zero(self):
        soup = _soup("<html><body><p>검색 결과가 없습니다.</p></body></html>")
        crawler = self._make_crawler()
        assert crawler.get_total_count(soup) == 0

    def test_comma_in_number(self):
        soup = _soup('<html><body><div class="cnt-all"><em>12,345</em></div></body></html>')
        crawler = self._make_crawler()
        assert crawler.get_total_count(soup) == 12345


# ---------------------------------------------------------------------------
# crawl_saramin — 통합 흐름 (mock)
# ---------------------------------------------------------------------------

class TestCrawlSaramin:
    def test_empty_query_raises(self):
        with pytest.raises(ValueError, match="query는 필수"):
            crawl_saramin("")

    def test_whitespace_query_raises(self):
        with pytest.raises(ValueError):
            crawl_saramin("   ")

    def test_returns_empty_string_when_no_new_docs(self, tmp_path):
        """이미 저장된 공고만 있으면 빈 문자열을 반환해야 한다."""
        with (
            patch("src.crawlers.saramin.crawler.get_saved_ids", return_value=set()),
            patch("src.crawlers.saramin.crawler._SaraminCrawler") as MockCrawler,
        ):
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            # collect_jobs_paged는 generator — 빈 배치를 yield하는 이터러블로 모킹
            mock_instance.collect_jobs_paged.return_value = iter([[]])
            MockCrawler.return_value = mock_instance

            result = crawl_saramin("백엔드 개발자", save_path=str(tmp_path))
            assert result == ""

    def test_saves_file_when_new_docs_found(self, tmp_path):
        """신규 공고가 있으면 파일 경로를 반환해야 한다."""
        from src.models.schemas import RawJobPosting
        mock_raw = RawJobPosting(
            source_name="saramin",
            source_job_id="12345678",
            original_url="https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=12345678",
            raw_html="<html>test</html>",
            raw_text="test",
        )

        with (
            patch("src.crawlers.saramin.crawler.get_saved_ids", return_value=set()),
            patch("src.crawlers.saramin.crawler._SaraminCrawler") as MockCrawler,
            patch("src.crawlers.saramin.crawler.save_documents") as mock_save,
        ):
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            # collect_jobs_paged는 generator — 한 페이지 배치를 yield하는 이터러블로 모킹
            mock_instance.collect_jobs_paged.return_value = iter([[mock_raw]])
            MockCrawler.return_value = mock_instance

            mock_save.return_value = tmp_path / "test.json"

            result = crawl_saramin("백엔드 개발자", save_path=str(tmp_path))
            assert result != ""
            mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# run_saramin_batch — 부분 실패 허용
# ---------------------------------------------------------------------------

class TestRunSaraminBatch:
    def test_batch_continues_after_failure(self, tmp_path):
        """한 검색어가 실패해도 나머지를 계속 처리해야 한다."""
        call_count = 0

        def mock_crawl(query, crawl_date=None, save_path=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("첫 번째 검색어 실패")
            return ""

        with patch("src.crawlers.saramin.crawler.crawl_saramin", side_effect=mock_crawl):
            with patch("src.crawlers.common.batch.time.sleep"):
                run_saramin_batch(
                    ["백엔드 개발자", "프론트엔드 개발자", "데이터 엔지니어"],
                    save_dir=str(tmp_path),
                )

        assert call_count == 3

    def test_batch_empty_list(self, tmp_path):
        """빈 목록으로 배치 실행해도 예외 없이 종료해야 한다."""
        with patch("src.crawlers.saramin.crawler.crawl_saramin") as mock_crawl:
            run_saramin_batch([], save_dir=str(tmp_path))
            mock_crawl.assert_not_called()


# ---------------------------------------------------------------------------
# search_queries
# ---------------------------------------------------------------------------

class TestSaraminSearchQueries:
    def test_get_all_queries_returns_list(self):
        queries = get_all_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_get_all_queries_no_duplicates(self):
        queries = get_all_queries()
        assert len(queries) == len(set(queries))

    def test_get_queries_for_function_known(self):
        queries = get_queries_for_function("Backend Engineer")
        assert isinstance(queries, list)
        assert len(queries) > 0
        assert any("백엔드" in q for q in queries)

    def test_get_queries_for_function_unknown(self):
        queries = get_queries_for_function("존재하지 않는 직무")
        assert queries == []

    def test_all_taxonomy_keys_have_queries(self):
        from src.crawlers.saramin.search_queries import SARAMIN_SEARCH_QUERIES
        for key, queries in SARAMIN_SEARCH_QUERIES.items():
            assert len(queries) > 0, f"{key!r}에 검색어가 없습니다."
