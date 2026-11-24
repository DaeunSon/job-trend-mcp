"""적재 직전 재정규화: 스킬 noise 제거·표기 통일, 폐기된 직무 비우기."""
from __future__ import annotations

import copy
from typing import Any

from src.normalization.skill_noise_filter import is_skill_noise
from src.taxonomy.job_functions import is_valid_function
from src.taxonomy.skills import lookup_skill_canonical


def renormalize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """입력을 바꾸지 않고 재정규화한 새 dict 를 돌려준다."""
    out = copy.deepcopy(doc)

    skills = []
    for skill in out.get("skills") or []:
        raw = skill.get("raw_text") or ""
        if is_skill_noise(raw):
            continue
        canonical = lookup_skill_canonical(raw)
        if canonical:
            skill["canonical_name"] = canonical
        skills.append(skill)
    if "skills" in out:
        out["skills"] = skills

    function = out.get("job_function_name")
    if function and not is_valid_function(function):
        out["job_function_name"] = ""
        out["job_category_name"] = ""
    return out
