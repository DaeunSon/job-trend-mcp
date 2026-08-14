"""
고용 형태(employment_type_name) 표준 taxonomy 및 정규화.

모든 사이트 파서는 원문에서 추출한 고용형태 문자열을
normalize_employment_type()으로 이 표준값 중 하나로 변환한다.
"""
from __future__ import annotations

EMPLOYMENT_TYPES: list[str] = [
    "Full-time",
    "Part-time",
    "Contract",
    "Internship",
    "Freelance",
]

# 원문(한글·영문·JSON-LD 코드 등) → 표준값
_EMPLOYMENT_ALIASES: dict[str, str] = {
    # Full-time
    "full-time": "Full-time",
    "full time": "Full-time",
    "full_time": "Full-time",
    "FULL_TIME": "Full-time",
    "정규직": "Full-time",
    "fulltime": "Full-time",
    # Part-time
    "part-time": "Part-time",
    "part time": "Part-time",
    "part_time": "Part-time",
    "PART_TIME": "Part-time",
    "파트타임": "Part-time",
    "아르바이트": "Part-time",
    "parttime": "Part-time",
    # Contract
    "contract": "Contract",
    "CONTRACT": "Contract",
    "CONTRACTOR": "Contract",
    "contractor": "Contract",
    "계약직": "Contract",
    "파견직": "Contract",
    "파견": "Contract",
    # Internship
    "internship": "Internship",
    "INTERN": "Internship",
    "INTERNSHIP": "Internship",
    "인턴": "Internship",
    "인턴십": "Internship",
    # Freelance
    "freelance": "Freelance",
    "FREELANCE": "Freelance",
    "프리랜서": "Freelance",
}


def normalize_employment_type(raw: str | None) -> str:
    """
    사이트별 원문 고용형태 문자열을 표준 employment_type_name으로 변환한다.

    매칭되지 않으면 빈 문자열을 반환한다 (추측으로 Full-time을 채우지 않음).
    """
    if not raw:
        return ""

    text = raw.strip()
    if not text:
        return ""

    # 정확 일치 (대소문자·별칭 테이블)
    if text in EMPLOYMENT_TYPES:
        return text

    upper = text.upper()
    if upper in _EMPLOYMENT_ALIASES:
        return _EMPLOYMENT_ALIASES[upper]

    lower = text.lower()
    if lower in _EMPLOYMENT_ALIASES:
        return _EMPLOYMENT_ALIASES[lower]

    if text in _EMPLOYMENT_ALIASES:
        return _EMPLOYMENT_ALIASES[text]

    # 부분 문자열 매칭 (한글 키워드)
    for keyword, standard in [
        ("프리랜서", "Freelance"),
        ("인턴십", "Internship"),
        ("인턴", "Internship"),
        ("파트타임", "Part-time"),
        ("아르바이트", "Part-time"),
        ("계약직,", "Contract"),
        ("기간의 정함이 없는", "Full-time"),   
        ("기간의 정함이 있는", "Contract"),    
        ("계약", "Contract"),
        ("파견직", "Contract"),
        ("정규직", "Full-time"),
    ]:
        if keyword in text:
            return standard

    for keyword, standard in [
        ("FREELANCE", "Freelance"),
        ("INTERN", "Internship"),
        ("PART_TIME", "Part-time"),
        ("PART-TIME", "Part-time"),
        ("CONTRACT", "Contract"),
        ("FULL_TIME", "Full-time"),
        ("FULL-TIME", "Full-time"),
    ]:
        if keyword in upper:
            return standard

    return ""
