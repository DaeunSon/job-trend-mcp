"""
근무 형태(work_arrangement) 공통 탐지 정책.

사람인 파서에서 검증된 규칙을 모든 국내·API 파서가 공유한다.
Remotive는 사이트 성격상 예외로 파서에서 REMOTE를 직접 설정한다.
"""
from __future__ import annotations

import re

_WORK_CTX = ("근무", "출근", "형태", "방식")


def detect_work_arrangement(text: str) -> str | None:
    """
    채용 정보 텍스트에서 근무 형태(ONSITE/REMOTE/HYBRID)를 탐지한다.

    정책
    ----
    - HYBRID → REMOTE → ONSITE 순으로 검사
    - hybrid/하이브리드: 주변 ±30자에 근무 문맥('근무','출근','형태','방식') 필요
    - "재택근무", "원격근무" 복합어는 문맥 없이도 REMOTE
    - ONSITE: "현장근무", "현장 근무", "사무실 출근", on-site/onsite 만 인정
      ("근무지" 단독, bare "현장"/"출근" 은 무시)
    - 명시적 언급 없으면 None (추측으로 ONSITE 채우지 않음)
    """
    if not text or not text.strip():
        return None

    text_lower = text.lower()

    def _near_work(keyword: str, window: int = 30) -> bool:
        for m in re.finditer(re.escape(keyword), text_lower):
            surround = text_lower[max(0, m.start() - window) : m.end() + window]
            if any(ctx in surround for ctx in _WORK_CTX):
                return True
        return False

    def _has_remote_signal() -> bool:
        if re.search(r"재택\s*근무|원격\s*근무", text_lower):
            return True
        if any(kw in text_lower for kw in ["work from home", "wfh", "풀 리모트", "full remote"]):
            return True
        return _near_work("remote") or _near_work("재택") or _near_work("원격")

    def _has_onsite_signal() -> bool:
        if re.search(
            r"사무실\s*출근|대면\s*출근|주\s*\d+\s*회.*출근|office\s*day",
            text_lower,
        ):
            return True
        return any(
            kw in text_lower
            for kw in ["현장근무", "현장 근무", "on-site", "onsite"]
        )

    # HYBRID — REMOTE보다 먼저
    if re.search(r"주\s*\d+\s*회.*출근", text_lower):
        return "HYBRID"
    if _has_remote_signal() and _has_onsite_signal():
        return "HYBRID"
    if re.search(r"하이브리드\s*근무|hybrid\s*근무", text_lower):
        return "HYBRID"
    if _near_work("하이브리드") or _near_work("hybrid"):
        return "HYBRID"

    # REMOTE
    if re.search(r"재택\s*근무|원격\s*근무", text_lower):
        return "REMOTE"
    if any(kw in text_lower for kw in ["work from home", "wfh", "풀 리모트", "full remote"]):
        return "REMOTE"
    if _near_work("remote") or _near_work("재택") or _near_work("원격"):
        return "REMOTE"

    # ONSITE — 복합어만
    if any(
        kw in text_lower
        for kw in ["현장근무", "현장 근무", "사무실 출근", "on-site", "onsite"]
    ):
        return "ONSITE"

    return None


def scoped_text_from_selectors(
    soup: object,
    selectors: list[str],
    fallback: str = "",
) -> str:
    """
    BeautifulSoup 객체에서 selector 목록 순으로 본문 텍스트를 추출한다.
    """
    for sel in selectors:
        tag = soup.select_one(sel)  # type: ignore[attr-defined]
        if tag:
            return tag.get_text(separator=" ", strip=True)
    return fallback
