"""
코드 채점. LLM 채점을 쓰지 않는다.

시스템 프롬프트가 답 마지막 줄을 `정답: <값>` 형식으로 쓰게 하므로, 그 줄만 파싱한다.
채점 항목:
  tool_ok   — 기준 도구를 한 번이라도 호출했는가
  call_ok   — 그 도구 호출 중 하나가 정답과 같은 값을 돌려받았는가 (= 파라미터가 맞았는가)
  answer_ok — 최종 답의 값이 정답과 같은가
  trap_hit  — 최종 답이 흔한 실수 값(예: 사이트 필터를 빼먹은 통합 건수)과 같은가
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from evals.cases import Case, GroundTruth, extract_value

_ANSWER_LINE = re.compile(r"정답\s*[:：]\s*(.+)")
_INT = re.compile(r"-?\d[\d,]*")


def parse_answer(text: str, kind: str) -> Any:
    """답 본문에서 마지막 `정답:` 줄을 찾아 문항 유형에 맞는 값으로 바꾼다. 없으면 None."""
    matches = _ANSWER_LINE.findall(text or "")
    if not matches:
        return None
    raw = matches[-1].strip().strip("`*").strip()
    if kind == "abstain" or raw.startswith("없음"):
        return "없음" if raw.startswith("없음") else raw
    if kind in {"count", "category_count"}:
        m = _INT.search(raw)
        return int(m.group().replace(",", "")) if m else None
    if kind == "top_skills":
        parts = re.split(r"[,，、/]", raw)
        return [re.sub(r"\s*\(.*?\)\s*$", "", p).strip() for p in parts if p.strip()]
    return raw


def _same(kind: str, got: Any, want: Any, k: int = 3) -> bool:
    if got is None or want is None:
        return False
    if kind == "top_skills":
        # 공동 순위가 있으면 순서가 흔들릴 수 있어 상위 k 개 집합으로 비교한다
        norm = lambda xs: {x.strip().lower() for x in xs[:k]}  # noqa: E731
        return len(got) >= k and norm(got) == norm(want)
    return got == want


@dataclass
class Grade:
    tool_ok: bool
    call_ok: bool
    answer_ok: bool
    trap_hit: bool
    parsed_answer: Any
    reason: str


def grade(case: Case, gt: GroundTruth, tool_calls: list[dict[str, Any]], final_text: str) -> Grade:
    exp = case.expect
    kind = exp["type"]
    k = exp.get("k", 3)

    target_calls = [c for c in tool_calls if c["name"] == exp["tool"]]
    tool_ok = bool(target_calls)
    call_ok = any(_same(kind, extract_value(exp, c["result"]), gt.value, k) for c in target_calls)

    parsed = parse_answer(final_text, kind)
    answer_ok = _same(kind, parsed, gt.value, k)
    trap_hit = (
        gt.trap_value is not None
        and gt.trap_value != gt.value
        and _same(kind, parsed, gt.trap_value, k)
    )

    if answer_ok:
        reason = "ok"
    elif not tool_ok:
        used = sorted({c["name"] for c in tool_calls}) or ["없음"]
        reason = f"기준 도구 {exp['tool']} 미호출 (호출: {', '.join(used)})"
    elif trap_hit:
        reason = f"함정 값 {gt.trap_value} 으로 답함 (정답 {gt.value})"
    elif not call_ok:
        reason = f"도구는 맞지만 파라미터가 달라 정답 값을 받지 못함 (정답 {gt.value})"
    elif parsed is None:
        reason = "`정답:` 줄이 없거나 파싱 실패"
    else:
        reason = f"도구 결과는 맞았지만 답을 {parsed} 로 씀 (정답 {gt.value})"
    return Grade(tool_ok, call_ok, answer_ok, trap_hit, parsed, reason)
