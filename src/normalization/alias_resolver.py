"""
normalization_aliases 조회 및 신규 후보 기록.

현재 구현: JSON 파일 기반 (data/normalization_aliases.json).
DB 도입 시 _load_aliases / _save_aliases 만 교체하면 된다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.models.schemas import NormalizationAlias
from src.storage.json_writer import _BASE_DATA_DIR, _write_json

logger = logging.getLogger(__name__)

_ALIASES_FILE = _BASE_DATA_DIR / "normalization_aliases.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve(
    alias_type: str,
    raw_text: str,
    source_name: str | None = None,
) -> str:
    """
    raw_text에 대응하는 canonical_name을 반환한다.
    alias_type: 'COMPANY' | 'SKILL' | 'LOCATION' | 'JOB_FUNCTION' | 'JOB_CATEGORY'

    조회 순서: normalization_aliases.json → 내장 seed → MANUAL 후보 등록
    """
    aliases = _load_aliases()
    stripped = raw_text.strip()
    key = (alias_type.upper(), stripped)

    for alias in aliases:
        if (alias.get("alias_type", "").upper(), alias.get("raw_text", "")) == key:
            canonical = alias["canonical_name"]
            if _is_valid_taxonomy_canonical(alias_type, canonical):
                logger.debug("alias 히트: %s → %s", raw_text, canonical)
                return canonical
            logger.debug(
                "alias 무효 canonical (%s → %s), seed 재조회",
                raw_text,
                canonical,
            )
            break

    seed = _lookup_seed(alias_type, stripped)
    if seed:
        logger.debug("alias seed 히트: %s → %s", raw_text, seed)
        return seed

    logger.debug("alias 미스: %s (%s), MANUAL 후보로 등록", raw_text, alias_type)
    _register_candidate(alias_type, raw_text, source_name, aliases)
    return stripped


def bulk_resolve(
    alias_type: str,
    raw_texts: list[str],
    source_name: str | None = None,
) -> dict[str, str]:
    """여러 raw_text를 한 번에 resolve하여 {raw_text: canonical_name} 매핑을 반환한다."""
    return {t: resolve(alias_type, t, source_name) for t in raw_texts}


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _is_valid_taxonomy_canonical(alias_type: str, canonical: str) -> bool:
    """JOB_FUNCTION / JOB_CATEGORY / SKILL alias의 canonical이 표준 taxonomy 값인지 확인."""
    if not canonical:
        return False
    at = alias_type.upper()
    if at == "JOB_FUNCTION":
        from src.taxonomy.job_functions import is_valid_function

        return is_valid_function(canonical)
    if at == "JOB_CATEGORY":
        from src.taxonomy.job_categories import is_valid_category

        return is_valid_category(canonical)
    if at == "SKILL":
        from src.taxonomy.skills import is_valid_skill

        return is_valid_skill(canonical)
    return True


def _lookup_seed(alias_type: str, raw_text: str) -> str | None:
    """JOB_FUNCTION / JOB_CATEGORY / SKILL 내장 seed 조회."""
    if not raw_text:
        return None
    from src.taxonomy.job_taxonomy_seed import JOB_CATEGORY_SEEDS, JOB_FUNCTION_SEEDS
    from src.taxonomy.skills import lookup_skill_canonical

    at = alias_type.upper()
    if at == "JOB_FUNCTION":
        seeds = JOB_FUNCTION_SEEDS
        return seeds.get(raw_text) or seeds.get(raw_text.lower())
    if at == "JOB_CATEGORY":
        seeds = JOB_CATEGORY_SEEDS
        return seeds.get(raw_text) or seeds.get(raw_text.lower())
    if at == "SKILL":
        return lookup_skill_canonical(raw_text)
    return None


def _load_aliases() -> list[dict[str, Any]]:
    if not _ALIASES_FILE.exists():
        return []
    try:
        with open(_ALIASES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("alias 파일 읽기 실패: %s", exc)
        return []


def _register_candidate(
    alias_type: str,
    raw_text: str,
    source_name: str | None,
    current_aliases: list[dict[str, Any]],
) -> None:
    """아직 등록되지 않은 raw_text를 MANUAL 후보로 파일에 추가한다."""
    raw_text = raw_text.strip()
    key = (alias_type.upper(), raw_text)

    for alias in current_aliases:
        if (alias.get("alias_type", "").upper(), alias.get("raw_text", "")) == key:
            return  # 이미 존재

    new_alias = NormalizationAlias(
        alias_type=alias_type.upper(),
        raw_text=raw_text,
        canonical_name=raw_text,  # 기본값: 원문 그대로
        source_name=source_name,
        match_method="MANUAL",
    )
    current_aliases.append(new_alias.to_dict())

    try:
        _ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _write_json(_ALIASES_FILE, current_aliases)
    except Exception as exc:
        logger.warning("alias 후보 저장 실패: %s", exc)
