"""
고용24 전용 HTML 추출기 (facade).

내부 구현은 exclusions / list_parser / detail_parser / field_parsers / parse 로 분리.
공개 import 경로는 이 모듈로 유지한다.
"""
from __future__ import annotations

from src.crawlers.work24.detail_parser import extract_detail_fields
from src.crawlers.work24.exclusions import (
    EXCLUDED_INFO_TYPE_CDS,
    EXCLUDED_SITE_CLCDS,
    is_excluded_source,
)
from src.crawlers.work24.field_parsers import (
    _extract_education_from_description,
    _normalize_date,
    _normalize_education,
    _parse_career,
    _parse_expires_at,
    _parse_salary,
    _resolve_education_raw,
)
from src.crawlers.work24.list_parser import extract_list_cards, extract_total_count
from src.crawlers.work24.parse import parse_raw_posting, run_work24_parse

__all__ = [
    "EXCLUDED_INFO_TYPE_CDS",
    "EXCLUDED_SITE_CLCDS",
    "extract_detail_fields",
    "extract_list_cards",
    "extract_total_count",
    "is_excluded_source",
    "parse_raw_posting",
    "run_work24_parse",
    # 테스트 호환 private 심볼
    "_extract_education_from_description",
    "_normalize_date",
    "_normalize_education",
    "_parse_career",
    "_parse_expires_at",
    "_parse_salary",
    "_resolve_education_raw",
]
