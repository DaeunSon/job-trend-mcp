"""고용24 검색 결과(목록) HTML 파서."""
from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_DETAIL_BASE_URL = "https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do"

def extract_total_count(html: str) -> int:
    """
    검색 결과 HTML에서 총 공고 건수를 추출한다.
    파싱 실패 시 0 반환.
    """
    soup = BeautifulSoup(html, "lxml")

    # 1순위: "검색건수 N건" 패턴 (고용24 실제 UI)
    for pattern in [
        r"검색건수\s*([\d,]+)\s*건",
        r"총\s*([\d,]+)\s*건",
        r"([\d,]+)\s*건",
    ]:
        m = re.search(pattern, soup.get_text())
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                continue

    # 2순위: 특정 셀렉터
    for sel in [
        ".resultCnt",
        ".total-count",
        ".cnt_result",
        ".cnt-result",
        "#resultCnt",
        "span.cnt",
    ]:
        tag = soup.select_one(sel)
        if tag:
            m = re.search(r"[\d,]+", tag.get_text())
            if m:
                try:
                    return int(m.group().replace(",", ""))
                except ValueError:
                    continue

    return 0


def extract_list_cards(html: str) -> list[dict[str, str]]:
    """
    검색 결과 페이지 HTML에서 공고 카드 목록을 추출한다.

    Returns
    -------
    list of dict:
      - wanted_auth_no: str   공고 고유 ID (source_job_id 로 사용)
      - info_type_cd: str     원본 출처 코드 (EXCLUDED_INFO_TYPE_CDS 와 비교용)
      - title_raw: str        공고 제목 원문
      - company_raw: str      회사명 원문
      - detail_url: str       상세 페이지 URL
      - info_type_group: str  infoTypeGroup 파라미터 (상세 URL 구성용)
      - provider_text: str    정보제공처 텍스트 (이미지 alt 또는 텍스트)
    """
    soup = BeautifulSoup(html, "lxml")
    cards: list[dict[str, str]] = []
    seen: set[str] = set()

    # 상세 링크에서 wantedAuthNo + infoTypeCd 를 추출하는 패턴
    href_pattern = re.compile(
        r"wantedAuthNo=([^&]+).*?infoTypeCd=([^&]+)",
        re.IGNORECASE,
    )

    # 고용24 링크 후보: href 에 wantedAuthNo 가 포함된 <a> 태그 전체 탐색
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        m = href_pattern.search(href)
        if not m:
            continue

        wanted_auth_no = m.group(1).strip()
        info_type_cd = m.group(2).strip()

        if not wanted_auth_no or wanted_auth_no in seen:
            continue
        seen.add(wanted_auth_no)

        # infoTypeGroup 파라미터 추출 (상세 URL 재구성용)
        info_type_group_m = re.search(r"infoTypeGroup=([^&]+)", href)
        info_type_group = info_type_group_m.group(1) if info_type_group_m else "tb_workinfogubun"

        detail_url = (
            f"{_DETAIL_BASE_URL}"
            f"?wantedAuthNo={wanted_auth_no}"
            f"&infoTypeCd={info_type_cd}"
            f"&infoTypeGroup={info_type_group}"
        )

        title_raw = a_tag.get_text(strip=True)
        if not title_raw:
            continue

        # 부모 또는 조상에서 회사명 탐색
        company_raw = _extract_company_from_surrounding(a_tag)

        # 같은 행(tr)에서 정보제공처 이미지 alt 텍스트 탐색
        provider_text = _extract_provider_from_surrounding(a_tag)

        cards.append(
            {
                "wanted_auth_no": wanted_auth_no,
                "info_type_cd": info_type_cd,
                "info_type_group": info_type_group,
                "title_raw": title_raw,
                "company_raw": company_raw,
                "detail_url": detail_url,
                "provider_text": provider_text,
            }
        )

    if not cards:
        logger.debug("[work24] extract_list_cards: 링크 패턴 없음 — HTML 구조 변경 확인 필요")

    return cards


def _extract_company_from_surrounding(a_tag: Any) -> str:
    """
    <a> 태그 주변(부모 tr/li/div)에서 회사명을 탐색한다.
    고용24 검색 결과 HTML 구조에 따라 여러 패턴을 시도한다.
    """
    # 공통 회사명 셀렉터 후보
    company_selectors = [
        "strong.cp_name",
        ".cp-name",
        ".company-name",
        ".corp-name",
        ".cname",
        "dt.cp_name",
        "span.corp",
    ]

    # 조상 탐색 범위: tr → li → div (최대 5단계)
    node = a_tag.parent
    for _ in range(5):
        if node is None:
            break
        for sel in company_selectors:
            tag = node.select_one(sel)
            if tag:
                text = tag.get_text(strip=True)
                if text:
                    return text
        node = node.parent

    return ""


def _extract_provider_from_surrounding(a_tag: Any) -> str:
    """
    <a> 태그 주변에서 정보제공처 이미지 alt 텍스트 또는 텍스트를 탐색한다.
    """
    node = a_tag.parent
    for _ in range(5):
        if node is None:
            break
        # 정보제공처 이미지 alt 속성
        for img in node.find_all("img"):
            alt = img.get("alt", "")
            if alt.startswith("[") and alt.endswith("]"):
                return alt[1:-1]
            title_attr = img.get("title", "")
            if title_attr:
                return title_attr
        # 정보제공처 텍스트 셀렉터
        for sel in [".info-source", ".site-name", ".provider", ".source-tag"]:
            tag = node.select_one(sel)
            if tag:
                return tag.get_text(strip=True)
        node = node.parent

    return ""

