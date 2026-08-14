"""
회사명 / 공고 제목 정규화 유틸리티.

사람인·잡코리아 등 한국 취업 사이트 파서 공용.
"""
from __future__ import annotations

import re

# 반각·전각 괄호 패턴 헬퍼 (사람인은 전각 '（주）' 혼용)
_OPEN_PAREN  = r"[(\uff08]"   # ( 또는 （
_CLOSE_PAREN = r"[)\uff09]"   # ) 또는 ）

# 접두사 패턴: "(주)회사명", "（주）회사명", "㈜회사명", "주식회사 회사명", "사단법인 회사명"
_PREFIX_RE = re.compile(
    rf"^(?:{_OPEN_PAREN}주{_CLOSE_PAREN}|㈜|주식회사\s*|사단법인\s*)"
)

# 접미사 패턴: "회사명(주)", "회사명（주）", "회사명㈜", "회사명 주식회사", "회사명(유)", …
_SUFFIX_RE = re.compile(
    rf"(?:\s*{_OPEN_PAREN}주{_CLOSE_PAREN}|\s*㈜|\s*주식회사|\s*{_OPEN_PAREN}유{_CLOSE_PAREN}|\s*유한회사|\s*합자회사|\s*합명회사|\s*{_OPEN_PAREN}사{_CLOSE_PAREN})\s*$"
)


def normalize_company_name(raw_name: str) -> str:
    """
    회사명에서 법인 접미사/접두사를 제거해 사람이 읽기 좋은 이름을 반환한다.

    제거 대상 (접두/접미 모두 처리, 반각·전각 괄호 모두 처리):
      (주)/（주）, ㈜, 주식회사, (유)/(유), 유한회사, 합자회사, 합명회사, (사), 사단법인

    Examples
    --------
    >>> normalize_company_name("브레인즈컴퍼니(주)")
    '브레인즈컴퍼니'
    >>> normalize_company_name("(주)세르딕")
    '세르딕'
    >>> normalize_company_name("㈜카카오스타일")
    '카카오스타일'
    >>> normalize_company_name("와디즈㈜")
    '와디즈'
    >>> normalize_company_name("비바리퍼블리카(토스)")   # 브랜드명 괄호 → 제거 안 함
    '비바리퍼블리카(토스)'
    """
    name = raw_name.strip()
    name = _PREFIX_RE.sub("", name).strip()
    name = _SUFFIX_RE.sub("", name).strip()
    return name


# ---------------------------------------------------------------------------
# 공고 제목 정규화
# ---------------------------------------------------------------------------

# 경력 조건 괄호: "(신입/경력)", "(경력)", "(신입)", "(경력무관)", "(인턴)" …
_CAREER_PAREN_RE = re.compile(
    r"\s*\("
    r"(?:신입[·/]경력|경력[·/]신입|경력무관|신입|경력|인턴|계약직|아르바이트|파트타임|정규직|병역특례|전문연구요원)"
    r"(?:[·/](?:신입|경력|경력무관))?"
    r"\)\s*",
    re.IGNORECASE,
)

# 홍보/채용 관련 trailing 복합 구문 — "채용" 앞의 경력어와 뒤의 공고 노이즈를 제거,
# "채용" 자체는 보존한다.
# 예: "경력 채용 공고입니다" → " 채용"  /  "공고입니다" → ""
# 그룹 1: 선택적 "채용 " (보존 대상)
_PROMO_COMPOUND_RE = re.compile(
    r"\s+(?:(?:신입[·/]경력|경력[·/]신입|신입·경력|경력무관|신입|경력)\s+)?"
    r"(채용\s+)?(?:모집공고|공고입니다)\s*$",
    re.IGNORECASE,
)

# 단독 trailing 홍보 단어: "모집", "공고", "구인" — "채용"은 제거하지 않음
_PROMO_SINGLE_RE = re.compile(
    r"\s+(?:모집|공고|구인)\s*$",
    re.IGNORECASE,
)

# 단독 trailing 경력 구분어: "신입/경력", "신입·경력", "경력무관" (괄호 없이)
_CAREER_TRAILING_RE = re.compile(
    r"\s+(?:신입[·/]경력|경력[·/]신입|신입·경력|경력·신입|경력무관)\s*$",
    re.IGNORECASE,
)

# 제목 내 회사명 노이즈: "[플랫폼]", "OOO주식회사", "OOO회사 " (직무명 앞 접두)
_TITLE_PLATFORM_TAG_RE = re.compile(r"\[[^\]]+\]\s*")
_TITLE_JUSIK_RE = re.compile(r"[가-힣A-Za-z0-9]+(?:주식회사|유한회사)\s*")
_TITLE_COMPANY_SUFFIX_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}회사(?=\s+[가-힣A-Z])")

# 조사 + 채용 홍보 꼬리: "개발 전문가를 모집합니다" → "개발 전문가"
_PARTICLE_PROMO_TAIL_RE = re.compile(
    r"^(?P<core>.+?)(?:을|를|과|와|에|의|으로|로|에서|에게|께|한테)"
    r"(?:\s*(?:모집|채용|구인|공고|지원|바랍니다|합니다|드립니다).*)?$",
    re.IGNORECASE,
)


def normalize_job_title(raw_title: str) -> str:
    """
    공고 제목에서 부가 정보를 제거하고 핵심 직무명만 남긴다.

    제거 대상:
      - 대괄호 전체: "[상장사/성수역/대졸신입 초봉4천]", "[세르딕]"
      - 경력 조건 괄호: "(신입/경력)", "(경력무관)" 등
      - 홍보 suffix: "모집", "공고", "공고입니다", "모집공고", "구인" 등
      - 단독 경력 구분어 suffix: "신입/경력", "경력무관" 등 (괄호 없이)

    유지 대상:
      - "채용" — 직무 제목의 일부로 보존 ("백엔드 개발자 채용" 유지)
      - 기술 스택 괄호: "(Java / Spring Boot)", "(PHP/C++/Linux)"

    Examples
    --------
    >>> normalize_job_title("백엔드 개발자 채용")
    '백엔드 개발자 채용'
    >>> normalize_job_title("클라우드 백엔드 개발자 모집")
    '클라우드 백엔드 개발자'
    >>> normalize_job_title("JAVA 백엔드 개발자 경력 채용 공고입니다")
    'JAVA 백엔드 개발자 채용'
    >>> normalize_job_title("백엔드 개발자 채용 공고")
    '백엔드 개발자 채용'
    >>> normalize_job_title("[상장사/성수역/대졸신입 초봉4천] 백엔드 개발자 (신입/경력)")
    '백엔드 개발자'
    >>> normalize_job_title("백엔드 개발자(PHP/C++/Linux) 채용")
    '백엔드 개발자(PHP/C++/Linux) 채용'
    """
    title = raw_title.strip().rstrip(".")
    # 플랫폼/홍보 대괄호 태그 제거: "[일자리매칭플랫폼]"
    title = _TITLE_PLATFORM_TAG_RE.sub("", title)
    # 제목에 끼어든 회사명 제거: "제일일렉트릭주식회사 조명스위치..."
    title = _TITLE_JUSIK_RE.sub("", title)
    title = _TITLE_COMPANY_SUFFIX_RE.sub("", title)
    # 나머지 대괄호 블록 제거
    title = re.sub(r"\[.*?\]", "", title)
    # 경력 조건 괄호 제거
    title = _CAREER_PAREN_RE.sub(" ", title)
    # 복합 홍보 구문 제거 — "채용" 앞의 경력어와 뒤의 공고 노이즈만 제거, 채용 자체는 보존
    for _ in range(3):
        prev = title
        title = _PROMO_COMPOUND_RE.sub(
            lambda m: (" 채용" if m.group(1) else ""), title
        )
        title = _PROMO_SINGLE_RE.sub("", title)
        title = _CAREER_TRAILING_RE.sub("", title)
        if title == prev:
            break
    # 조사(을/를/과 등) 뒤 채용 홍보 꼬리 제거
    m = _PARTICLE_PROMO_TAIL_RE.match(title.strip())
    if m:
        title = m.group("core").strip()
    title = re.sub(r"\s{2,}", " ", title).strip()
    return title
