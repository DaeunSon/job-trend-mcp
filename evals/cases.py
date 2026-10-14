"""
평가 문항과 정답 계산.

정답은 문항마다 정한 "기준 호출"(canonical call)을 지금 데이터에 실행해 얻는다.
데이터를 다시 수집해도 문항 파일은 그대로 두고 정답만 새로 계산된다.

이 평가가 재는 것은 "모델이 도구를 써서 기준 호출과 같은 값에 도달하는가"이다.
시장 전체의 정답이 아니라, 도구 설명 · 모델 선택이 바뀌었을 때의 회귀를 잡기 위한 기준이다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evals.bridge import McpBridge

CASES_PATH = Path(__file__).with_name("cases.json")

# expect.type 별로 도구 응답에서 비교할 값을 꺼낸다.
COUNT_FIELDS = {
    "search_job_postings": "total_matched",
    "get_salary_summary": "salary_data_count",
    "get_company_hiring_activity": "matched_postings",
}


@dataclass
class Case:
    id: str
    category: str
    question: str
    expect: dict[str, Any]
    note: str = ""


@dataclass
class GroundTruth:
    case_id: str
    value: Any  # int | list[str] | "없음"
    status: str
    trap_value: Any = None  # 흔한 실수를 했을 때 나오는 값 (예: source_name 누락 시 통합 건수)
    warnings: list[str] = field(default_factory=list)


def load_cases(path: Path = CASES_PATH, only: list[str] | None = None) -> list[Case]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = [Case(**c) for c in raw["cases"]]
    if only:
        wanted = set(only)
        cases = [c for c in cases if c.id in wanted or c.category in wanted]
    return cases


def extract_value(expect: dict[str, Any], result: dict[str, Any]) -> Any:
    """도구 응답에서 이 문항이 비교할 값을 꺼낸다. 꺼낼 수 없으면 None."""
    kind = expect["type"]
    status = result.get("status")
    if kind == "abstain":
        return "없음" if status in {"unknown_company", "empty", "no_salary_data"} else None
    if kind == "count" and status in {"ok", "empty"}:
        # empty 는 필터가 유효한 0건이다
        return result.get(COUNT_FIELDS[expect["tool"]], 0 if status == "empty" else None)
    if status != "ok":
        return None
    if kind == "top_skills":
        k = expect.get("k", 3)
        return [s["skill"] for s in result.get("skills", [])[:k]]
    if kind == "category_count":
        for row in result.get("categories", []):
            if row.get("category") == expect["category"]:
                return row.get("count")
        return None
    raise ValueError(f"unknown expect.type {kind!r}")


async def compute_ground_truth(bridge: McpBridge, case: Case) -> GroundTruth:
    exp = case.expect
    result = await bridge.call(exp["tool"], exp.get("args", {}))
    value = extract_value(exp, result)
    gt = GroundTruth(case.id, value, str(result.get("status")))

    if value is None:
        gt.warnings.append(f"기준 호출 결과에서 값을 꺼내지 못함 (status={gt.status})")
    elif exp["type"] == "count" and value == 0:
        gt.warnings.append("정답이 0건 — 문항 조건을 바꾸는 편이 낫다")
    elif exp["type"] == "count" and isinstance(value, int) and value < 5:
        gt.warnings.append(f"표본이 {value}건으로 작다")

    if exp["type"] == "top_skills" and value is not None:
        k = exp.get("k", 3)
        skills = result.get("skills", [])
        if len(skills) > k and skills[k - 1]["count"] == skills[k]["count"]:
            gt.warnings.append(
                f"{k}위와 {k + 1}위가 동률({skills[k]['count']}) — 정답이 모호하다"
            )

    if "trap_args" in exp:
        trap_result = await bridge.call(exp["tool"], exp["trap_args"])
        gt.trap_value = extract_value(exp, trap_result)
        if gt.trap_value == value:
            gt.warnings.append("함정 값이 정답과 같아 함정을 구분할 수 없다")
    return gt
