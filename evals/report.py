"""채점 결과(JSONL 행)를 모델 비교 리포트(markdown)로 만든다."""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any


def _pct(xs: list[bool]) -> str:
    return f"{sum(xs)}/{len(xs)} ({100 * sum(xs) / len(xs):.0f}%)" if xs else "-"


def _quantile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    idx = min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))
    return xs[idx]


def build_report(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)

    out: list[str] = []
    out.append(f"# MCP 도구 호출 평가 — {meta['run_id']}\n")
    out.append(
        "기준: 문항마다 정한 기준 호출을 현재 데이터에 실행한 값. "
        "시장 전체 정답이 아니라, 모델이 도구를 써서 그 값에 도달하는지를 본다.\n"
    )
    out.append("| 항목 | 값 |\n|---|---|")
    for key in ("dataset", "prompt_version", "prompt_hash", "tools_hash", "effort", "repeats", "n_cases"):
        out.append(f"| {key} | {meta.get(key)} |")
    out.append("")

    out.append("## 모델별 요약\n")
    out.append(
        "| 모델 | 도구 선택 | 파라미터 | 최종 답 | 함정 | 오류 | 지연 p50 | 지연 p95 | 입력 토큰(평균) | 출력 토큰(평균) | 문항당 비용 | 총 비용 |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for model, rs in by_model.items():
        lat = [r["latency_sec"] for r in rs if not r["error"]]
        cost = [r["cost_usd"] for r in rs]
        out.append(
            "| {m} | {t} | {c} | {a} | {trap} | {err} | {p50:.1f}s | {p95:.1f}s | {it:,.0f} | {ot:,.0f} | ${cpc:.4f} | ${tc:.3f} |".format(
                m=model,
                t=_pct([r["tool_ok"] for r in rs]),
                c=_pct([r["call_ok"] for r in rs]),
                a=_pct([r["answer_ok"] for r in rs]),
                trap=sum(r["trap_hit"] for r in rs),
                err=sum(1 for r in rs if r["error"]),
                p50=_quantile(lat, 0.5),
                p95=_quantile(lat, 0.95),
                it=statistics.mean(r["input_tokens"] for r in rs),
                ot=statistics.mean(r["output_tokens"] for r in rs),
                cpc=statistics.mean(cost),
                tc=sum(cost),
            )
        )
    out.append("")

    out.append("## 카테고리별 최종 답 정확도\n")
    cats = sorted({r["category"] for r in rows})
    out.append("| 카테고리 | " + " | ".join(by_model) + " |")
    out.append("|---|" + "---|" * len(by_model))
    for cat in cats:
        cells = [_pct([r["answer_ok"] for r in rs if r["category"] == cat]) for rs in by_model.values()]
        out.append(f"| {cat} | " + " | ".join(cells) + " |")
    out.append("")

    if meta.get("repeats", 1) > 1:
        out.append("## 반복 간 흔들림\n")
        out.append("같은 모델 · 같은 문항인데 반복마다 정답 여부가 달랐던 경우.\n")
        flaky = []
        for model, rs in by_model.items():
            per_case: dict[str, list[bool]] = defaultdict(list)
            for r in rs:
                per_case[r["case_id"]].append(r["answer_ok"])
            flaky += [f"- {model} · {cid}: {sum(v)}/{len(v)}" for cid, v in per_case.items() if 0 < sum(v) < len(v)]
        out.extend(flaky or ["- 없음"])
        out.append("")

    out.append("## 실패 사례\n")
    fails = [r for r in rows if not r["answer_ok"]]
    if not fails:
        out.append("- 없음")
    else:
        out.append("| 모델 | 문항 | 반복 | 원인 |\n|---|---|---|---|")
        for r in fails:
            reason = r["error"] or r["reason"]
            out.append(f"| {r['model']} | {r['case_id']} | {r['repeat']} | {reason} |")
    out.append("")
    out.append(
        "비용은 Anthropic API 정가로 입력 · 출력 토큰만 계산했다(프롬프트 캐시 미사용). "
        "지연은 문항 하나의 전체 왕복(모델 호출 + 도구 실행) 벽시계 시간이다.\n"
    )
    return "\n".join(out)
