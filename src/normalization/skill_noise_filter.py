"""
스킬 추출 단계 노이즈 필터.

사이트 제공 태그(arbeitnow / remotive / jobkorea flight skills 등)를
그대로 skills[] 후보로 넣기 전에, A/C 단계에서 SKIP으로 확인된
비-스킬 항목을 제외한다.

주의
  - alias 매핑이 아니라 "후보 목록에 넣지 않는" 사전 필터다.
  - 목록은 실제 미매칭(SKIP) 데이터에서만 구성한다.
  - 한글은 인성/소프트스킬 명시 목록만 제외한다 (일반 한글 패턴 금지).
"""
from __future__ import annotations

from collections.abc import Iterable

# ── 1. 한글 인성/소프트스킬 (jobkorea SKIP 확인분) ─────────────────
KOREAN_SOFT_SKILLS: frozenset[str] = frozenset({
    "계획성",
    "성실성",
    "협동심",
    "꼼꼼함",
    "성취지향성",
    "적응성",
    "성장지향성",
    "창의성",
    "윤리의식",
    "스트레스관리",
})

# ── 2. 지명·도시명 (arbeitnow 태그로 실제 등장) ───────────────────
PLACE_NAMES: frozenset[str] = frozenset({
    "hamburg",
    "berlin",
    "münchen",
    "munich",
})

# ── 3. 독일어 직군/고용형태 노이즈 (arbeitnow) ────────────────────
GERMAN_ROLE_NOISE: frozenset[str] = frozenset({
    "werkstudent",
    "werkstudium",
    "werkstudierende",
    "werkstudentin",
    "praktikant",
    "studentenjob",
    "vertrieb",
    "vertireb",  # 오타 태그
    "beratung",
    "digitalisierung",
    "vollzeit",
    "teilzeit",
    "verkauf",
    "wärmewende",
    "wärmepumpe",
    "it-vertrieb",
    "technischer vertrieb",
})

# ── 4. 일반 명사·역할·직무 영역 (arbeitnow / remotive SKIP) ───────
GENERIC_ROLE_WORDS: frozenset[str] = frozenset({
    # remotive 일반어 (프롬프트·A단계 SKIP)
    "backend",
    "frontend",
    "documentation",
    "security",
    "marketplace",
    "engineering",
    "sales",
    "startup",
    "video",
    "research",
    "insurance",
    "chat",
    "social media",
    "graphic design",
    # arbeitnow 직무/카테고리
    "it",
    "consulting",
    "business development",
    "marketing",
    "operations",
    "people",
    "product management",
    "product",
    "join",
    "job",
    "software development",
    "software engineering",
    "strategy",
    "strategie",
    "execution",
    "management",
    "client teams",
    "clients",
    "directors",
    "chief executives",
    "account executives",
    "quality assurance",
    "public sector",
    "öffentliche verwaltung",
    "intern",
    "r&d engineering",
    "technical sales",
    "enterprise sales",
    "field sales",
    "emea sales - central",
    "emea field sales",
    "finance",
    "data",
    "global",
    "film",
    "equine",
    "small animal",
    "media management & delivery",
    "people and culture",
    "technology & data",
    "customer cluster finance",
    "value engineering",
    "security engineering",
    "creative design",
    "marketing manager",
    "team leader",
    "influencer",
    "compliance",
    "controlling",
    "hardware",
    "storage",
    "system and network administration",
    "podcast producer",
    # 고유 캠페인/비기술 태그
    "omr",
    "omr festival",
    "ramp106",
    "2024 dedrone r&d",
    "4508 tax",
    "1komma5grad",
    "1komma5°",
    "one platform",
})

# ── 5. 영문 소프트스킬·역량 표현 (remotive SKIP) ──────────────────
ENGLISH_SOFT_SKILLS: frozenset[str] = frozenset({
    "people management",
    "prototyping",
    "engineering management",
    "project management",
})

# 대소문자 무시 매칭용 통합 집합 (한글은 원문 그대로도 포함)
_NOISE_LOWER: frozenset[str] = frozenset(
    s.lower()
    for s in (
        *PLACE_NAMES,
        *GERMAN_ROLE_NOISE,
        *GENERIC_ROLE_WORDS,
        *ENGLISH_SOFT_SKILLS,
    )
)

_NOISE_EXACT: frozenset[str] = KOREAN_SOFT_SKILLS


def is_skill_noise(raw_text: str) -> bool:
    """태그 후보가 확인된 노이즈이면 True."""
    text = (raw_text or "").strip()
    if not text:
        return True
    if text in _NOISE_EXACT:
        return True
    return text.casefold() in _NOISE_LOWER


def filter_skill_candidates(names: Iterable[str]) -> list[str]:
    """노이즈가 아닌 스킬 후보만 순서·중복 없이 반환."""
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        text = (name or "").strip()
        if not text or is_skill_noise(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
