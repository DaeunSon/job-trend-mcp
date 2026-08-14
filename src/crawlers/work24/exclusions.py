"""고용24 정보제공처(타 사이트 중복) 필터."""
from __future__ import annotations

#: 이 코드의 공고는 저장하지 않고 건너뛴다.
#: siteClcd 실측 결과 (2026-07-29):
#:   CSI → 32,045건  사람인  (GET ?siteClcd=CSI 확인)
#:   CWT → 2,441건   원티드  (GET ?siteClcd=CWT 확인)
#:   WK  → 0건       고용24 자체등록 (IT 직종 없음)
#:   CJK  → 미측정, infoTypeCd=CJK 패턴으로 추론
EXCLUDED_INFO_TYPE_CDS: frozenset[str] = frozenset(
    {
        "CSI",   # 사람인 (siteClcd=CSI로 32,045건 확인)
        "CJK",   # 잡코리아 (infoTypeCd 패턴으로 확인됨)
        "CWT",   # 원티드   (siteClcd=CWT로 2,441건 확인)
    }
)

#: 고용24 검색 API siteClcd 파라미터 — 사람인/잡코리아/원티드 제외용.
#: GET 요청에서 동작 확인됨 (2026-07-29).
#: crawler.py POST 요청에도 함께 전달한다.
EXCLUDED_SITE_CLCDS: frozenset[str] = frozenset(
    {
        "CSI",   # 사람인 (확인)
        "CJK",   # 잡코리아 (infoTypeCd 패턴)
        "CWT",   # 원티드 (확인)
    }
)


def is_excluded_source(info_type_cd: str) -> bool:
    """infoTypeCd 가 이미 직접 수집 중인 사이트(사람인/잡코리아/원티드)이면 True."""
    return info_type_cd.upper() in EXCLUDED_INFO_TYPE_CDS
