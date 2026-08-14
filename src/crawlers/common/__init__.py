"""
HTML/requests 계열 크롤러 공유 유틸.

saramin · jobkorea 등 동일 패턴(SERP→detail, 차단 감지, 배치 루프)에서 사용한다.
사이트별 셀렉터·URL·중복 정책(force/incremental)은 각 크롤러에 남긴다.
"""
from __future__ import annotations

from src.crawlers.common.api_client_base import ApiCallResult, ApiClientBase, RateLimitPolicy
from src.crawlers.common.batch import run_query_batch
from src.crawlers.common.curl_cffi_client import (
    CurlCffiClient,
    default_browser_headers,
    random_delay,
)
from src.crawlers.common.filenames import build_crawl_filename
from src.crawlers.common.html_serp import DuplicateMode, HtmlSerpCrawler
from src.crawlers.common.http_utils import (
    BROWSER_USER_AGENT,
    DEFAULT_BLOCK_SIGNALS,
    html_description_to_text,
    html_to_text,
    is_blocked,
    parse_total_count,
)
from src.crawlers.common.json_api import JsonApiCrawler, PageCursor

__all__ = [
    "ApiCallResult",
    "ApiClientBase",
    "BROWSER_USER_AGENT",
    "CurlCffiClient",
    "DEFAULT_BLOCK_SIGNALS",
    "DuplicateMode",
    "HtmlSerpCrawler",
    "JsonApiCrawler",
    "PageCursor",
    "RateLimitPolicy",
    "build_crawl_filename",
    "default_browser_headers",
    "html_description_to_text",
    "html_to_text",
    "is_blocked",
    "parse_total_count",
    "random_delay",
    "run_query_batch",
]
