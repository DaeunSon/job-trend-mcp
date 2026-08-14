"""요청/응답 공통 헬퍼 — UA, 봇 차단 감지, 총 건수·텍스트 추출."""
from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Iterable

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 국내·해외 HTML 사이트에서 공통으로 쓰는 차단 징후 (대소문자 무시 매칭).
DEFAULT_BLOCK_SIGNALS: tuple[str, ...] = (
    "access denied",
    "robot or human",
    "just a moment",
    "please enable javascript",
    "human verification",
    "bot detection",
    "자동화된 접근",
    "비정상적인 접근",
    "비정상 접근",
    "잠시 후 다시",
)

_DEFAULT_COUNT_PATTERNS: tuple[str, ...] = (
    r"총\s*([\d,]+)\s*건",
    r"([\d,]+)\s*개의\s*공고",
)


def is_blocked(
    html: str,
    signals: Iterable[str] = DEFAULT_BLOCK_SIGNALS,
) -> bool:
    """HTML/텍스트 응답에서 봇 차단 징후를 확인한다."""
    if not html:
        return False
    lower = html.lower()
    return any(sig.lower() in lower for sig in signals)


def html_to_text(raw_html: str) -> str:
    """HTML을 줄바꿈 구분 텍스트로 변환한다."""
    return BeautifulSoup(raw_html, "lxml").get_text(separator="\n", strip=True)


def html_description_to_text(
    raw_html: str,
    *,
    unescape_entities: bool = False,
) -> str:
    """
    공식 API description/contents HTML → 평문 텍스트.

    themuse / remotive / arbeitnow 파서가 공유한다.
    BeautifulSoup(html.parser) 우선, 미설치 시 정규식 폴백.
    arbeitnow처럼 엔티티 인코딩된 HTML이면 unescape_entities=True.
    """
    if not raw_html:
        return ""
    text_in = html_lib.unescape(str(raw_html)) if unescape_entities else str(raw_html)
    try:
        soup = BeautifulSoup(text_in, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        # ImportError 등 — 정규식 폴백
        logger.debug("BeautifulSoup HTML 변환 실패 — 정규식 폴백", exc_info=True)
        text = re.sub(r"<[^>]+>", " ", text_in)
        text = re.sub(r"&[a-zA-Z]+;", " ", text)
        return re.sub(r"\s+", " ", text).strip()


def parse_total_count(
    soup: BeautifulSoup,
    selectors: Iterable[str] = (),
    text_patterns: Iterable[str] = _DEFAULT_COUNT_PATTERNS,
) -> int:
    """
    SERP에서 검색 결과 총 건수를 파싱한다.

    1) selectors 순회 → 태그 텍스트에서 숫자 추출
    2) 페이지 전체 텍스트에서 text_patterns regex fallback
    실패 시 0.
    """
    for sel in selectors:
        tag = soup.select_one(sel)
        if not tag:
            continue
        m = re.search(r"[\d,]+", tag.get_text(strip=True))
        if m:
            return int(m.group().replace(",", ""))

    full_text = soup.get_text()
    for pattern in text_patterns:
        m = re.search(pattern, full_text)
        if m:
            return int(m.group(1).replace(",", ""))

    return 0
