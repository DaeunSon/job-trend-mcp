"""
한국 주소 location 정규화 공통 유틸.

국내 사이트(사람인, 잡코리아, 점핏, 원티드)가 공유한다.
Remotive 등 해외/국가 단위 데이터는 이 모듈을 사용하지 않는다.
"""
from __future__ import annotations

import re


def trim_to_district(raw: str) -> str:
    """
    전체 주소에서 시/도 + 구/군/시 수준까지만 남긴다.

    "서울 성동구 성수2가3동 315-7 성문빌딩 8층 ..." → "서울 성동구"
    "(06072) 서울 강남구 영동대로137길 3, ..."     → "서울 강남구"
    "경기 성남시 분당구 황새울로 ..."               → "경기 성남시"
    """
    raw = re.sub(r"^\(\d{5}\)\s*", "", raw.strip())
    tokens = raw.split()
    result: list[str] = []
    for i, tok in enumerate(tokens):
        if re.fullmatch(r"\(\d{5}\)", tok):
            continue
        if re.search(r"\d", tok):
            break
        if tok.endswith(("로", "길")):
            break
        if tok.startswith("("):
            break
        result.append(tok)
        if re.search(r"[구군]$", tok):
            break
        if i >= 1 and tok.endswith("시"):
            break
    return " ".join(result).strip() if result else raw


_KO_REGIONS = [
    "서울", "경기", "인천", "부산", "대구", "대전",
    "광주", "울산", "세종", "강원", "충북", "충남",
    "전북", "전남", "경북", "경남", "제주",
]


def parse_korean_location(raw_text: str) -> tuple[str, str | None, str]:
    """
    위치 텍스트를 (city_name, region_name, country_name)로 파싱한다.

    city_name은 trim_to_district()로 구/시까지만 정규화한다.
    raw_text(전체 주소)는 호출 측에서 별도 보관한다.
    """
    raw = raw_text.strip()
    if not raw:
        return "", None, "대한민국"

    city = trim_to_district(raw)

    for region in _KO_REGIONS:
        if city.startswith(region) or raw.startswith(region):
            return city, region, "대한민국"

    if "전국" in raw:
        return city or raw, None, "대한민국"

    # 영문 패턴 fallback (서울 오피스 표기 등)
    m = re.match(r"^(.+?),\s*([A-Z]{2})\b", raw)
    if m:
        return m.group(1).strip(), m.group(2).strip(), "미국"

    return city or raw, None, "대한민국"
