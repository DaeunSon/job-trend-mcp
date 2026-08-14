"""고용24 상세 페이지 HTML 파서."""
from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from src.crawlers.work24.field_parsers import (
    _normalize_date,
    _parse_expires_at,
    _parse_salary,
)

logger = logging.getLogger(__name__)

def extract_detail_fields(raw_html: str, card_meta: dict[str, str] | None = None) -> dict[str, Any]:
    """
    상세 페이지 HTML에서 공고 정보를 추출한다.

    Parameters
    ----------
    raw_html  : 상세 페이지 HTML 원문
    card_meta : 검색 결과 카드에서 추출한 메타데이터 (title, company 등 fallback 용)

    Returns
    -------
    dict (모두 원문값 — 정규화 전):
      title, company, description,
      location_raw, employment_type_raw, career_raw, education_raw,
      salary_raw, salary_min, salary_max, salary_currency, salary_period,
      posted_at, expires_at,
      has_remote_work,  # bool | None
      info_type_cd, company_type_raw
    """
    soup = BeautifulSoup(raw_html, "lxml")
    meta = card_meta or {}

    # --- 제목 ---
    title = _extract_title_from_detail(soup) or meta.get("title_raw", "")

    # --- 회사명 ---
    company = _extract_company_from_detail(soup) or meta.get("company_raw", "")

    # --- 본문 설명 ---
    description = _extract_description(soup)

    # --- 조건 테이블 파싱 (th → td 쌍) ---
    cond = _extract_conditions_table(soup)

    # --- 개별 필드 ---
    # 고용24 실측 테이블 키 (공백 포함)와 fallback 키 모두 시도
    employment_type_raw = (
        cond.get("고용 형태")          # 실측: 근무조건 상세 테이블
        or cond.get("고용형태")        # 요약 카드 / 구조 변경 대비
        or cond.get("근무형태", "")
    )
    career_raw = cond.get("경력", cond.get("경력조건", ""))
    education_raw = cond.get("학력", cond.get("학력조건", ""))
    occupation_raw = cond.get("모집 직종", cond.get("모집직종", ""))
    location_raw = (
        cond.get("근무 예정지")        # 실측: 근무조건 상세 테이블
        or cond.get("지역")            # 요약 카드 fallback
        or cond.get("근무지역")
        or cond.get("근무위치", meta.get("location_raw", ""))
    )
    # "지도 보기", "길찾기" 링크 텍스트 노이즈 제거
    if location_raw:
        location_raw = re.sub(r"\s*(지도\s*보기|길찾기)\s*", " ", location_raw).strip()
    salary_raw_text = (
        cond.get("임금 조건")          # 실측: 근무조건 상세 테이블
        or cond.get("임금")            # 요약 카드 fallback
        or cond.get("급여", "")
    )
    company_type_raw = cond.get(
        "기업형태",
        cond.get("기업규모", cond.get("회사유형", "")),
    )
    # 마감일: th/td 테이블이 아닌 별도 DOM 요소에 있음
    expires_at_raw = (
        cond.get("접수 마감일")        # 구조 변경 시 테이블에 들어올 경우 대비
        or cond.get("마감일")
        or cond.get("접수마감일", "")
        or _extract_expires_at_from_dom(soup)
    )
    posted_at_raw = (
        cond.get("채용공고 등록일시")   # 실측: 인증기관 정보 테이블
        or cond.get("등록일시")
        or cond.get("등록일")
        or cond.get("공고등록일", meta.get("posted_at", ""))
    )

    # --- 재택근무 가능 여부 ---
    has_remote_work = _extract_remote_work_flag(soup, cond)

    # --- 급여 파싱 ---
    salary_min, salary_max, salary_period = _parse_salary(salary_raw_text)

    # --- 날짜 정규화 ---
    posted_at = _normalize_date(posted_at_raw)
    expires_at = _parse_expires_at(expires_at_raw) if expires_at_raw else None

    return {
        "title": title,
        "company": company,
        "description": description,
        "location_raw": location_raw,
        "employment_type_raw": employment_type_raw,
        "career_raw": career_raw,
        "education_raw": education_raw,
        "occupation_raw": occupation_raw,
        "salary_raw": salary_raw_text,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": "KRW" if salary_raw_text else None,
        "salary_period": salary_period,
        "posted_at": posted_at,
        "expires_at": expires_at,
        "has_remote_work": has_remote_work,
        "info_type_cd": meta.get("info_type_cd", ""),
        "company_type_raw": company_type_raw,
    }


def _extract_title_from_detail(soup: BeautifulSoup) -> str:
    """상세 페이지 HTML에서 공고 제목을 추출한다."""
    # 1순위: 고용24 실측 셀렉터 (2026-07-29 확인)
    # <strong class="title">공고명</strong>
    tag = soup.select_one("strong.title")
    if tag:
        text = tag.get_text(strip=True)
        if text and len(text) < 300:
            return text

    # 2순위: 기타 헤딩 셀렉터 (구조 변경 대비)
    for sel in [
        "h1.job-title",
        "h1.recruit-title",
        ".jb-tit h1",
        ".job-view-tit",
        "#jobTitle",
        "h2.job-tit",
        ".title-area h1",
        ".cp-title",
    ]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            if text and len(text) < 300:
                return text

    # 3순위: <title> 태그에서 공고명 추출 (예: "공고명 | 고용24")
    # 단, "채용정보 상세" 같은 제네릭 페이지 제목은 제외
    _GENERIC_TITLES = {"채용정보 상세", "채용정보", "고용24"}
    title_tag = soup.find("title")
    if title_tag:
        text = title_tag.get_text(strip=True)
        parts = re.split(r"\s*[\|｜]\s*", text)
        if parts:
            candidate = parts[0].strip()
            if candidate and candidate not in _GENERIC_TITLES and len(candidate) < 300:
                return candidate

    return ""


def _extract_company_from_detail(soup: BeautifulSoup) -> str:
    """상세 페이지 HTML에서 회사명을 추출한다."""
    # 1순위: 고용24 실측 구조 (2026-07-29 확인)
    # <strong>(회사명)</strong>
    # <strong class="title">(공고명)</strong>
    # → strong.title 바로 이전의 class 없는 <strong> 태그가 회사명
    title_tag = soup.select_one("strong.title")
    if title_tag:
        prev = title_tag.find_previous_sibling("strong")
        if prev and not prev.get("class"):
            text = prev.get_text(strip=True)
            if text:
                return text
        # 같은 부모 컨테이너 안의 첫 번째 class-less strong
        parent = title_tag.parent
        if parent:
            for strong in parent.find_all("strong"):
                if not strong.get("class"):
                    text = strong.get_text(strip=True)
                    if text:
                        return text

    # 2순위: 기타 셀렉터 (구조 변경 대비)
    for sel in [
        "a.cp-name",
        ".company-name a",
        ".company-name",
        ".corp-name",
        ".cp_name",
        "span.corp",
        "#companyName",
        ".jb-cp-tit",
        "h2.corp",
    ]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            if text:
                return text
    return ""


def _extract_description(soup: BeautifulSoup) -> str:
    """공고 본문 텍스트를 추출한다."""
    # 1순위: 고용24 실측 셀렉터 (2026-07-29 확인)
    # 직무내용이 들어있는 div.scroll → 모집요강 탭 본문
    tag = soup.select_one("div.scroll")
    if tag:
        return tag.get_text(separator="\n", strip=True)

    # 2순위: 메인 콘텐츠 컨테이너
    for sel in [
        "section#container",
        "div#contents",
        "#duty_wrap",
        ".jb-detail",
        ".job-desc",
        ".recruit-detail",
        "#jobDetail",
        ".detail-content",
        ".emp-detail-wrap",
        "div.detail",
    ]:
        tag = soup.select_one(sel)
        if tag:
            return tag.get_text(separator="\n", strip=True)

    # 3순위: body 전체 (노이즈 많음 — 최후 수단)
    body = soup.find("body")
    if body:
        return body.get_text(separator="\n", strip=True)

    return soup.get_text(separator="\n", strip=True)


def _extract_expires_at_from_dom(soup: BeautifulSoup) -> str:
    """
    상세 페이지 DOM에서 접수 마감일 텍스트를 추출한다.

    고용24 실측:
      <strong>접수 기간</strong><p>2026.07.30 (목)<br>~ 2026.08.31 (월)</p>
      <div class="left_area br js_s">접수 마감일채용시까지 ...</div>
    """
    for strong in soup.find_all("strong"):
        label = strong.get_text(strip=True)
        if "접수 기간" in label or "접수 마감일" in label:
            parent = strong.parent
            if parent:
                p = parent.find("p")
                if p:
                    return p.get_text(separator=" ", strip=True)
            nxt = strong.find_next_sibling("p")
            if nxt:
                return nxt.get_text(separator=" ", strip=True)
            nxt = strong.find_next_sibling()
            if nxt:
                return nxt.get_text(strip=True)
            if parent:
                return parent.get_text(separator=" ", strip=True)

    for tag in soup.find_all("div"):
        classes = set(tag.get("class") or [])
        if "left_area" in classes and "js_s" in classes:
            text = tag.get_text(strip=True)
            if "마감일" in text or "마감" in text or "접수 기간" in text:
                return text

    return ""


def _extract_conditions_table(soup: BeautifulSoup) -> dict[str, str]:
    """
    th → td 쌍으로 이루어진 조건 테이블을 파싱해 dict 로 반환한다.
    여러 테이블 구조를 순회한다.
    """
    result: dict[str, str] = {}

    # 방법 1: table 내 tr > th + td 쌍
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            ths = tr.find_all("th")
            tds = tr.find_all("td")
            for th, td in zip(ths, tds):
                key = th.get_text(strip=True).rstrip(":")
                val = td.get_text(separator=" ", strip=True)
                if key and val:
                    result[key] = val

    # 방법 2: dl > dt + dd 쌍 (dl-based layout)
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            key = dt.get_text(strip=True).rstrip(":")
            val = dd.get_text(separator=" ", strip=True)
            if key and val:
                result.setdefault(key, val)

    return result


def _extract_remote_work_flag(
    soup: BeautifulSoup,
    cond: dict[str, str],
) -> bool | None:
    """
    재택근무 가능 여부를 구조화된 방식으로 추출한다.

    Returns
    -------
    True  — 재택근무 가능 명시됨
    False — 재택근무 불가 명시됨
    None  — 명시적 정보 없음 (detect_work_arrangement 에 위임)
    """
    # 1순위: 조건 테이블에 재택근무 항목이 있는 경우
    for key in ("재택근무", "재택근무가능여부", "근무형태상세", "근무형태"):
        val = cond.get(key, "")
        if val:
            v_lower = val.lower()
            if "가능" in v_lower or "허용" in v_lower or "remote" in v_lower:
                return True
            if "불가" in v_lower or "불허" in v_lower:
                return False

    # 2순위: 페이지 내 재택근무 체크박스/배지 요소
    for sel in [
        "[data-remote-work]",
        ".remote-badge",
        ".badge-remote",
        "#remoteWork",
    ]:
        tag = soup.select_one(sel)
        if tag:
            val = (
                tag.get("data-remote-work")
                or tag.get("data-value")
                or tag.get_text(strip=True)
            )
            if val in ("Y", "true", "1", "가능"):
                return True
            if val in ("N", "false", "0", "불가"):
                return False

    return None

