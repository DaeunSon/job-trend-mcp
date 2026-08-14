"""
경력 수준(career_level) 표준 taxonomy 및 정규화.

모든 사이트 파서는 원문 경력 정보(텍스트·연수)를
normalize_career_level()으로 아래 표준 label 중 하나로 변환한다.
"""
from __future__ import annotations

import re
from typing import Any

from src.models.schemas import CareerLevel

CAREER_LEVELS: list[dict[str, Any]] = [
    {"label": "Entry", "min_years": 0, "max_years": 0},
    {"label": "Junior", "min_years": 1, "max_years": 3},
    {"label": "Mid", "min_years": 3, "max_years": 5},
    {"label": "Senior", "min_years": 5, "max_years": None},
    {"label": "Any", "min_years": None, "max_years": None},
]

# 구(舊) 파서 영문 코드 → 표준 label
_LEGACY_LABEL_MAP: dict[str, str] = {
    "ENTRY": "Entry",
    "JUNIOR": "Junior",
    "MID": "Mid",
    "MID-LEVEL": "Mid",
    "SENIOR": "Senior",
    "ANY": "Any",
    "UNKNOWN": "Any",
    "EXPERIENCED": "Mid",
}


def normalize_career_level(
    *,
    raw_text: str | None = None,
    min_years: int | None = None,
    max_years: int | None = None,
    legacy_label: str | None = None,
) -> CareerLevel:
    """
    사이트별 원문 경력 정보를 표준 CareerLevel로 변환한다.

    Parameters
    ----------
    raw_text:
        "신입", "경력 3~5년", "경력무관", "Senior" 등 원문 텍스트
    min_years / max_years:
        API 등에서 제공하는 숫자 경력 연수
    legacy_label:
        구 파서가 반환하던 ENTRY/EXPERIENCED 등 (추출 단계 호환용)
    """
    text = (raw_text or "").strip()

    # API 연수 우선 (원티드 max_years >= 100 → 제한 없음)
    if max_years is not None and max_years >= 100:
        max_years = None

    if min_years is not None or max_years is not None:
        return _from_years(min_years, max_years, text)

    if legacy_label:
        mapped = _LEGACY_LABEL_MAP.get(legacy_label.upper(), legacy_label)
        if mapped in {lv["label"] for lv in CAREER_LEVELS}:
            return _make_level(mapped, min_years, max_years)

    if text:
        return _from_text(text)

    return CareerLevel(label="Any", min_years=None, max_years=None)


def _from_years(
    min_years: int | None,
    max_years: int | None,
    text: str = "",
) -> CareerLevel:
    """숫자 연수 기반 분류."""
    min_y = int(min_years) if min_years is not None else None
    max_y = int(max_years) if max_years is not None else None

    # 텍스트에 경력무관/신입·경력 힌트
    if text and _is_any_career(text):
        return CareerLevel(label="Any", min_years=None, max_years=None)

    if min_y == 0 and (max_y is None or max_y == 0):
        return CareerLevel(label="Entry", min_years=0, max_years=0)

    # 분류 기준: min_years (하한) 우선
    ref = min_y if min_y is not None else (max_y or 0)

    if ref >= 5:
        label = "Senior"
    elif ref >= 3:
        label = "Mid"
    elif ref >= 1:
        label = "Junior"
    else:
        label = "Entry"

    return CareerLevel(label=label, min_years=min_y, max_years=max_y)


def _from_text(text: str) -> CareerLevel:
    """한글·영문 경력 텍스트 기반 분류."""
    if _is_any_career(text):
        return CareerLevel(label="Any", min_years=None, max_years=None)

    if "신입" in text and "경력" not in text:
        return CareerLevel(label="Entry", min_years=0, max_years=0)

    # 영문 서술
    lower = text.lower()
    if any(kw in lower for kw in ["senior", "sr.", "lead", "principal", "staff"]):
        return CareerLevel(label="Senior", min_years=5, max_years=None)
    if any(kw in lower for kw in ["junior", "jr.", "entry", "graduate"]):
        return CareerLevel(label="Junior", min_years=1, max_years=3)
    if any(kw in lower for kw in ["mid-level", "mid level", "intermediate"]):
        return CareerLevel(label="Mid", min_years=3, max_years=5)
    if "intern" in lower:
        return CareerLevel(label="Entry", min_years=0, max_years=0)

    # "N+ years" / "N years experience"
    years_match = re.search(r"(\d+)\+?\s*years?\s*(?:of\s+)?experience", lower)
    if years_match:
        min_y = int(years_match.group(1))
        return _from_years(min_y, None, text)

    # "경력 N년~M년" / "N~M년"
    m = re.search(r"(\d+)\s*년?\s*[~\-]\s*(\d+)\s*년", text)
    if m:
        return _from_years(int(m.group(1)), int(m.group(2)), text)

    # "경력 N년 이상"
    m = re.search(r"(\d+)\s*년\s*이상", text)
    if m:
        return _from_years(int(m.group(1)), None, text)

    if "경력" in text:
        return CareerLevel(label="Mid", min_years=None, max_years=None)

    # 구 영문 코드가 텍스트로 들어온 경우
    upper = text.upper()
    if upper in _LEGACY_LABEL_MAP:
        label = _LEGACY_LABEL_MAP[upper]
        return _make_level(label, None, None)

    return CareerLevel(label="Any", min_years=None, max_years=None)


def _is_any_career(text: str) -> bool:
    return any(
        kw in text
        for kw in ["경력무관", "신입/경력", "신입·경력", "신입·경력", "경력·신입", "무관"]
    )


def _make_level(
    label: str,
    min_years: int | None,
    max_years: int | None,
) -> CareerLevel:
    for spec in CAREER_LEVELS:
        if spec["label"] == label:
            return CareerLevel(
                label=label,
                min_years=min_years if min_years is not None else spec["min_years"],
                max_years=max_years if max_years is not None else spec["max_years"],
            )
    return CareerLevel(label=label, min_years=min_years, max_years=max_years)
