"""
사람인 검색어 목록.

국내 공통 맵(KR_JOB_SEARCH_QUERIES)을 재수출한다.
사람인 전용 변형이 필요하면 이 모듈에서 override 한다.
"""
from __future__ import annotations

from src.crawlers.common.kr_search_queries import (
    KR_JOB_SEARCH_QUERIES,
    get_all_queries,
    get_queries_for_function,
)

# 하위 호환 — 기존 import 경로 유지
SARAMIN_SEARCH_QUERIES = KR_JOB_SEARCH_QUERIES

__all__ = [
    "SARAMIN_SEARCH_QUERIES",
    "get_all_queries",
    "get_queries_for_function",
]
