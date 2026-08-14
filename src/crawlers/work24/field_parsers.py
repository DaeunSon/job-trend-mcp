"""고용24 급여·경력·학력·날짜 원시 문자열 파서."""
from __future__ import annotations

import re

_SALARY_PERIOD_MAP = {
    "시급": "HOURLY",
    "일급": "DAILY",
    "주급": "WEEKLY",
    "월급": "MONTHLY",
    "연봉": "ANNUAL",
}

_AMOUNT_RE = re.compile(r"([\d,]+)\s*만\s*원|([\d,]+)\s*원")


def _parse_salary(raw: str) -> tuple[str | None, str | None, str | None]:
    """
    급여 원문에서 (min_amount, max_amount, pay_period) 를 추출한다.
    금액 단위: 원(KRW) 기준 문자열.
    """
    if not raw or "협의" in raw or "미공개" in raw:
        return None, None, None

    period: str | None = None
    for kor, code in _SALARY_PERIOD_MAP.items():
        if kor in raw:
            period = code
            break

    amounts: list[int] = []
    for m in _AMOUNT_RE.finditer(raw):
        if m.group(1):  # 만원 단위
            val_str = m.group(1).replace(",", "")
            try:
                amounts.append(int(val_str) * 10000)
            except ValueError:
                pass
        elif m.group(2):  # 원 단위
            val_str = m.group(2).replace(",", "")
            try:
                amounts.append(int(val_str))
            except ValueError:
                pass

    if not amounts:
        return None, None, period

    amounts.sort()
    min_amt = str(amounts[0])
    max_amt = str(amounts[-1]) if len(amounts) > 1 else None

    return min_amt, max_amt, period


# ---------------------------------------------------------------------------
# 내부: 경력 파싱 헬퍼
# ---------------------------------------------------------------------------

_CAREER_YEAR_RE = re.compile(r"(\d+)\s*년")


def _parse_career(raw: str) -> tuple[int | None, int | None]:
    """
    경력 원문에서 (min_years, max_years) 를 추출한다.

    예시:
      "경력 3년 이상"   → (3, None)
      "경력 3년 ~ 7년"  → (3, 7)
      "신입"            → (0, 0)
      "경력무관"         → (None, None)
    """
    if not raw:
        return None, None

    raw_lower = raw.lower()

    if "경력무관" in raw or "관계없음" in raw:
        return None, None

    if "신입" in raw and "경력" not in raw:
        return 0, 0

    years = [int(m.group(1)) for m in _CAREER_YEAR_RE.finditer(raw)]
    if not years:
        return None, None

    years.sort()
    if len(years) == 1:
        # "이상" 이 있으면 min만 설정
        if "이상" in raw or "~" not in raw:
            return years[0], None
        return years[0], None
    return years[0], years[-1]


# ---------------------------------------------------------------------------
# 내부: 학력 추출 헬퍼
# ---------------------------------------------------------------------------

_GENERIC_EDUCATION = frozenset({"", "-", "무관", "학력무관", "관계없음"})

_EDUCATION_DESC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:^|\n|ㆍ)\s*학력\s*[:：]\s*([^\n]+)", re.MULTILINE),
    re.compile(r"공통자격요건[^\n]*\n(?:[^\n]*\n)*?\s*학력\s*[:：]\s*([^\n]+)", re.MULTILINE),
)


def _extract_education_from_description(description: str) -> str:
    """모집요강 본문(공통자격요건 등)에서 학력 원문을 추출한다."""
    if not description:
        return ""
    for pattern in _EDUCATION_DESC_PATTERNS:
        match = pattern.search(description)
        if not match:
            continue
        value = match.group(1).strip()
        if value and value not in _GENERIC_EDUCATION:
            return value
    return ""


def _resolve_education_raw(table_raw: str, description: str) -> str | None:
    """
    조건 테이블과 본문에서 학력 원문을 결정한다.

    테이블이 '학력무관' 등 일반값이면 본문(ㆍ학력 : 대졸 이상)을 우선한다.
    '무관' 계열은 null 이 아닌 '무관'으로 보존한다.
    범위 표기(대졸(4년)~석사)는 축약하지 않고 원문 그대로 반환한다.
    """
    table = (table_raw or "").strip()
    desc = _extract_education_from_description(description)

    _MOOGWAN = frozenset({"무관", "학력무관", "관계없음"})

    if table in _MOOGWAN:
        if desc and desc not in _MOOGWAN:
            return desc
        return "무관"

    if desc in _MOOGWAN:
        return "무관"

    if table in _GENERIC_EDUCATION:
        return desc or None
    if desc and table in _GENERIC_EDUCATION:
        return desc
    return table or desc or None


# ---------------------------------------------------------------------------
# 내부: 학력 정규화 헬퍼 (레거시 — work24 는 _resolve_education_raw 사용)
# ---------------------------------------------------------------------------

_EDUCATION_MAP = {
    "박사": "박사",
    "석사": "석사",
    "대졸(4년)": "대학교(4년)",
    "대졸(2~3년)": "대학교(2~3년)",
    "대학교": "대학교",
    "대졸": "대학교",
    "고졸": "고등학교",
    "고등학교": "고등학교",
    "중졸": "중학교",
    "무관": "",
    "학력무관": "",
}


def _normalize_education(raw: str) -> str:
    """학력 원문을 표준 문자열로 변환한다. 무관이면 빈 문자열."""
    for key, val in _EDUCATION_MAP.items():
        if key in raw:
            return val
    return ""


# ---------------------------------------------------------------------------
# 내부: 날짜 정규화 헬퍼
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def _normalize_date(raw: str) -> str:
    """
    날짜 원문에서 YYYY-MM-DD 형식을 추출한다.
    파싱 실패 시 빈 문자열 반환.
    """
    if not raw:
        return ""
    m = _DATE_RE.search(raw)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        return f"{y}-{mo}-{d}"
    return ""


_OPEN_ENDED_EXPIRY = ("채용시까지", "상시채용", "상시 채용", "수시채용", "수시 채용")


def _parse_expires_at(raw: str) -> str | None:
    """
    접수/마감 원문에서 마감일(YYYY-MM-DD)을 추출한다.

    접수 기간(시작~종료)이면 종료일을 사용한다.
    채용시까지·상시채용 등 구체 날짜가 없으면 None.
    """
    if not raw:
        return None

    dates = _DATE_RE.findall(raw)
    if not dates:
        return None

    if len(dates) >= 2 and re.search(r"[~～]", raw):
        y, mo, d = dates[-1]
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    if len(dates) >= 2 and ("접수" in raw or "기간" in raw):
        y, mo, d = dates[-1]
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    if len(dates) == 1 and any(kw in raw for kw in _OPEN_ENDED_EXPIRY):
        return None

    y, mo, d = dates[-1]
    return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
