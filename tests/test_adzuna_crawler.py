"""adzuna/crawler.py 유닛 테스트."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.crawlers.adzuna.crawler import (
    COUNTRY_DOMAINS,
    _build_filename,
    _parse_detail_to_job,
    _parse_salary,
    crawl_adzuna,
)


class TestBuildFilename:
    def test_basic(self):
        assert _build_filename("gb", "backend engineer", None) == \
            "adzuna_gb_backend_engineer"

    def test_with_where(self):
        assert "london" in _build_filename("gb", "python", "london")


class TestParseSalary:
    def test_range(self):
        assert _parse_salary("£50000 - £55000/ANNUM") == (50000.0, 55000.0)

    def test_single(self):
        assert _parse_salary("JOBSWORTH: £32,409 per year") == (32409.0, 32409.0)


class TestParseDetailToJob:
    def test_basic_html(self):
        html = """
        <html><body>
          <h1>Python Developer</h1>
          <div class="ui-company">Acme Corp</div>
          <div class="ui-location">London, UK</div>
          <div class="ui-salary">£60000 - £70000/annum</div>
          <div class="adp-body">Build APIs with FastAPI and PostgreSQL.</div>
        </body></html>
        """
        job = _parse_detail_to_job(html, "123", "https://www.adzuna.co.uk/jobs/details/123")
        assert job is not None
        assert job["title"] == "Python Developer"
        assert job["company"]["display_name"] == "Acme Corp"
        assert job["location"]["display_name"] == "London, UK"
        assert job["salary_min"] == 60000.0
        assert "FastAPI" in job["description"]
        assert job["_source"] == "html_crawl"


class TestCrawlAdzuna:
    def test_empty_what_raises(self):
        with pytest.raises(ValueError):
            crawl_adzuna("")

    def test_unsupported_country_raises(self):
        with pytest.raises(ValueError, match="지원하지 않는"):
            crawl_adzuna("python", country="us")

    def test_gb_domain_mapped(self):
        assert COUNTRY_DOMAINS["gb"] == "www.adzuna.co.uk"

    def test_saves_docs(self, tmp_path: Path):
        sample_raw = MagicMock()
        sample_raw.to_dict.return_value = {
            "source_name": "adzuna",
            "source_job_id": "123",
            "original_url": "https://www.adzuna.co.uk/jobs/details/123",
            "raw_html": "<html/>",
            "raw_text": '{"id":"123","title":"Backend"}',
        }

        mock_crawler = MagicMock()
        mock_crawler.__enter__.return_value = mock_crawler
        mock_crawler.__exit__.return_value = None
        mock_crawler.collect.return_value = [sample_raw]

        with patch("src.crawlers.adzuna.crawler.get_saved_ids", return_value=set()), \
             patch("src.crawlers.adzuna.crawler._AdzunaHttpCrawler", return_value=mock_crawler), \
             patch("src.crawlers.adzuna.crawler.save_documents") as mock_save:
            mock_save.return_value = tmp_path / "out.json"
            result = crawl_adzuna("backend", country="gb", save_path=str(tmp_path), max_pages=1)
            assert result != ""
            assert mock_save.called
