#!/usr/bin/env python3
"""
job_taxonomy_seed / skills 의 alias 매핑을
data/normalization_aliases.json 에 merge 한다.

기존 alias 는 유지하고, 동일 (alias_type, raw_text) 키가 없을 때만 추가한다.
SKILL 의 경우 무효 canonical(표준 목록 밖) MANUAL 후보는 seed 로 교정한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.schemas import NormalizationAlias
from src.storage.json_writer import _BASE_DATA_DIR, _write_json
from src.taxonomy.job_categories import is_valid_category
from src.taxonomy.job_functions import is_valid_function
from src.taxonomy.job_taxonomy_seed import JOB_CATEGORY_SEEDS, JOB_FUNCTION_SEEDS
from src.taxonomy.skills import SKILL_SEEDS, is_valid_skill, lookup_skill_canonical

_ALIASES_FILE = _BASE_DATA_DIR / "normalization_aliases.json"


def _load_aliases() -> list[dict]:
    if not _ALIASES_FILE.exists():
        return []
    with open(_ALIASES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _merge_seed(
    aliases: list[dict],
    alias_type: str,
    seeds: dict[str, str],
) -> int:
    existing = {
        (a.get("alias_type", "").upper(), a.get("raw_text", ""))
        for a in aliases
    }
    added = 0
    seen: set[tuple[str, str]] = set()
    for raw_text, canonical in seeds.items():
        key = (alias_type, raw_text)
        if key in existing or key in seen:
            continue
        seen.add(key)
        aliases.append(
            NormalizationAlias(
                alias_type=alias_type,
                raw_text=raw_text,
                canonical_name=canonical,
                source_name="seed",
                match_method="EXACT",
            ).to_dict()
        )
        added += 1
    return added


def _lookup_seed_canonical(alias_type: str, raw_text: str) -> str | None:
    at = alias_type.upper()
    if at == "SKILL":
        return lookup_skill_canonical(raw_text)
    if at == "JOB_FUNCTION":
        return JOB_FUNCTION_SEEDS.get(raw_text) or JOB_FUNCTION_SEEDS.get(raw_text.lower())
    if at == "JOB_CATEGORY":
        return JOB_CATEGORY_SEEDS.get(raw_text) or JOB_CATEGORY_SEEDS.get(raw_text.lower())
    return None


def _is_valid_canonical(alias_type: str, canonical: str) -> bool:
    at = alias_type.upper()
    if at == "SKILL":
        return is_valid_skill(canonical)
    if at == "JOB_FUNCTION":
        return is_valid_function(canonical)
    if at == "JOB_CATEGORY":
        return is_valid_category(canonical)
    return bool(canonical)


def _repair_aliases_from_seed(aliases: list[dict], alias_type: str) -> int:
    """
    seed 와 다른(또는 무효한) canonical 을 seed 값으로 교정한다.

    - SKILL: 표준 목록 밖 canonical 만 교정
    - JOB_FUNCTION / JOB_CATEGORY: seed 가 있으면 seed 우선 (taxonomy 확장 반영)
    """
    repaired = 0
    at = alias_type.upper()
    for alias in aliases:
        if (alias.get("alias_type") or "").upper() != at:
            continue
        raw = alias.get("raw_text") or ""
        canonical = alias.get("canonical_name") or ""
        mapped = _lookup_seed_canonical(at, raw)
        if not mapped or not _is_valid_canonical(at, mapped):
            continue

        if at == "SKILL":
            if _is_valid_canonical(at, canonical):
                continue
        elif canonical == mapped:
            continue

        alias["canonical_name"] = mapped
        alias["match_method"] = "EXACT"
        if not alias.get("source_name") or alias.get("source_name") == "seed":
            alias["source_name"] = "seed"
        repaired += 1
    return repaired


def main() -> None:
    aliases = _load_aliases()
    fn_added = _merge_seed(aliases, "JOB_FUNCTION", JOB_FUNCTION_SEEDS)
    cat_added = _merge_seed(aliases, "JOB_CATEGORY", JOB_CATEGORY_SEEDS)
    skill_added = _merge_seed(aliases, "SKILL", SKILL_SEEDS)
    fn_repaired = _repair_aliases_from_seed(aliases, "JOB_FUNCTION")
    cat_repaired = _repair_aliases_from_seed(aliases, "JOB_CATEGORY")
    skill_repaired = _repair_aliases_from_seed(aliases, "SKILL")
    _ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _write_json(_ALIASES_FILE, aliases)
    print(f"JOB_FUNCTION: {fn_added} added, {fn_repaired} repaired")
    print(f"JOB_CATEGORY: {cat_added} added, {cat_repaired} repaired")
    print(f"SKILL: {skill_added} added, {skill_repaired} repaired")
    print(f"Total aliases: {len(aliases)}")


if __name__ == "__main__":
    main()
