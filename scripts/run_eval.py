#!/usr/bin/env python3
"""
MCP 도구 호출 평가 · 모델 벤치마크.

같은 문항 세트를 모델별로 Claude API 에 보내, 도구 선택 · 파라미터 · 최종 답 정확도와
응답시간 · 토큰 · 비용을 함께 잰다. 결과는 evals/results/<run_id>/ 에 남는다.

사용:
  # API 호출 없이 문항별 정답만 계산 · 점검 (데이터를 새로 수집한 뒤 먼저 돌린다)
  PYTHONPATH=. python scripts/run_eval.py --dry-run

  # 모델 3개 비교, 문항당 2회 반복
  PYTHONPATH=. python scripts/run_eval.py \\
      --models claude-haiku-5-5 claude-sonnet-5-5 claude-opus-5-5 --repeats 2

  # 일부 문항 · 카테고리만
  PYTHONPATH=. python scripts/run_eval.py --only site_specific s01

인증: ANTHROPIC_API_KEY 또는 `ant auth login` 프로필.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.mcp_server import monitoring  # noqa: E402

PROMPTS_DIR = _ROOT / "evals" / "prompts"
RESULTS_DIR = _ROOT / "evals" / "results"
DEFAULT_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--repeats", type=int, default=1, help="문항당 반복 횟수")
    p.add_argument("--prompt", default="v1", help="evals/prompts/system_<버전>.md")
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--only", nargs="+", help="문항 id 또는 카테고리")
    p.add_argument("--concurrency", type=int, default=4, help="동시에 보낼 문항 수")
    p.add_argument("--dry-run", action="store_true", help="API 호출 없이 정답만 계산")
    return p.parse_args()


def _dataset_label(store) -> str:
    dates = sorted(str(d.get("created_at") or "")[:10] for d in store.postings if d.get("created_at"))
    span = f"{dates[0]}~{dates[-1]}" if dates else "?"
    return f"job_postings {len(store.postings)}건 (수집 {span})"


async def main() -> int:
    args = _parse_args()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{args.prompt}"
    out_dir = RESULTS_DIR / ("dry-run" if args.dry_run else run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 평가 중 도구 호출이 실사용 모니터링 로그에 섞이지 않게 한다
    monitoring.set_log_path(out_dir / "mcp_calls.jsonl")

    from evals.bridge import McpBridge
    from evals.cases import compute_ground_truth, load_cases
    from src.mcp_server.data_loader import get_store

    cases = load_cases(only=args.only)
    if not cases:
        print("문항이 없습니다.", file=sys.stderr)
        return 1

    async with McpBridge() as bridge:
        gts = {c.id: await compute_ground_truth(bridge, c) for c in cases}

        print(f"데이터: {_dataset_label(get_store())}")
        print(f"도구 {len(bridge.tool_defs)}개, tools_hash={bridge.tools_hash()}\n")
        print(f"{'id':<6} {'category':<16} {'정답':<36} 함정 / 경고")
        for c in cases:
            gt = gts[c.id]
            trap = f"함정={gt.trap_value}" if gt.trap_value is not None else ""
            print(f"{c.id:<6} {c.category:<16} {str(gt.value):<36} {trap} {' / '.join(gt.warnings)}")
        (out_dir / "ground_truth.json").write_text(
            json.dumps({cid: vars(g) for cid, g in gts.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if args.dry_run:
            print(f"\n정답 저장: {out_dir / 'ground_truth.json'}")
            return 0

        import anthropic

        from evals.grader import grade
        from evals.report import build_report
        from evals.runner import run_case

        prompt_path = PROMPTS_DIR / f"system_{args.prompt}.md"
        system_prompt = prompt_path.read_text(encoding="utf-8")
        meta = {
            "run_id": run_id,
            "dataset": _dataset_label(get_store()),
            "prompt_version": args.prompt,
            "prompt_hash": hashlib.sha256(system_prompt.encode()).hexdigest()[:8],
            "tools_hash": bridge.tools_hash(),
            "effort": args.effort,
            "repeats": args.repeats,
            "n_cases": len(cases),
            "models": args.models,
        }

        client = anthropic.AsyncAnthropic()
        sem = asyncio.Semaphore(args.concurrency)

        async def one(model: str, case, rep: int) -> dict:
            async with sem:
                rec = await run_case(
                    client, bridge, model=model, system_prompt=system_prompt,
                    case=case, repeat=rep, effort=args.effort,
                )
            g = grade(case, gts[case.id], rec.tool_calls, rec.final_text)
            row = rec.to_dict() | vars(g) | {"category": case.category, "expected": gts[case.id].value}
            mark = "O" if g.answer_ok else "X"
            print(f"[{mark}] {model:<18} {case.id:<6} #{rep} {rec.latency_sec:5.1f}s  {g.reason if not g.answer_ok else ''}")
            return row

        jobs = [one(m, c, r) for m in args.models for c in cases for r in range(1, args.repeats + 1)]
        rows = await asyncio.gather(*jobs)
        rows.sort(key=lambda r: (args.models.index(r["model"]), r["case_id"], r["repeat"]))

    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    report = build_report(rows, meta)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"\n리포트: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
