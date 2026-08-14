"""
config/sources.py — ALL_SOURCES 등록 상태 유닛 테스트.
"""
from __future__ import annotations

from src.config.sources import (
    ADZUNA_SOURCE,
    ALL_SOURCES,
    WORK24_SOURCE,
)


class TestAllSources:
    def test_work24_registered(self):
        assert "work24" in {s.source_name for s in ALL_SOURCES}

    def test_adzuna_registered_active(self):
        assert "adzuna" in {s.source_name for s in ALL_SOURCES}
        assert ADZUNA_SOURCE.is_active is True
        assert ADZUNA_SOURCE.source_type == "WEB_CRAWLING"

    def test_removed_sites_not_registered(self):
        names = {s.source_name for s in ALL_SOURCES}
        assert "indeed" not in names
        assert "glassdoor" not in names

    def test_excluded_sites_not_registered(self):
        names = {s.source_name for s in ALL_SOURCES}
        assert "jobplanet" not in names
        assert "linkedin" not in names
        assert "rocketpunch" not in names

    def test_all_registered_are_active(self):
        assert len(ALL_SOURCES) == 11
        assert all(s.is_active for s in ALL_SOURCES)

    def test_work24_is_active(self):
        assert WORK24_SOURCE.is_active is True

    def test_source_names_unique(self):
        names = [s.source_name for s in ALL_SOURCES]
        assert len(names) == len(set(names))
