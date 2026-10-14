#!/usr/bin/env python3
"""
수집 품질 게이트 — 이번 수집 결과를 직전 수집과 비교해, 사이트가 조용히 깨졌는지 판정한다.

사이트 구조가 바뀌면 파서는 예외 없이 빈 값을 저장할 수 있다. 그래서 종료 코드만 보지 않고
사이트별 공고 수와 필드 결측률이 직전보다 크게 나빠졌는지를 본다.

판정 (사이트별):
  fail — 공고 수가 직전 대비 DROP_RATIO 넘게 줄었거나, 어떤 필드 결측률이 MISSING_PP 넘게 늘었다
  warn — 수집 로그에 ERROR 줄이 있다 (예: 일부 카테고리 API 422)
  ok   — 그 외

결과는 수집 실행 폴더(data/collect_runs/<run_id>/quality.json)에 저장한다.
직전 실행이 없으면 기준선만 만들고 통과시킨다.

종료 코드: 0 통과(ok/warn) · 1 실패(fail 하나 이상)

사용:
  PYTHONPATH=. python scripts/quality_gate.py                 # 가장 최근 수집 실행 기준
  PYTHONPATH=. python scripts/quality_gate.py --run 20261014-130926
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.data_quality_report import FIELDS  # noqa: E402
from src.mcp_server.data_loader import JobPostingStore  # noqa: E402

RUNS_DIR = _ROOT / "data" / "collect_runs"
DROP_RATIO = 0.5   # 공고 수가 절반 넘게 줄면 실패
MISSING_PP = 20.0  # 결측률이 20%p 넘게 늘면 실패


def measure(postings: list[dict]) -> dict[str, dict[str, Any]]:
    """사이트별 공고 수와 필드별 결측률(%)."""
    by_src: dict[str, list[dict]] = defaultdict(list)
    for d in postings:
        by_src[d.get("source_name") or "?"].append(d)
    out = {}
    for src, docs in by_src.items():
        out[src] = {
            "count": len(docs),
            "missing_pct": {
                name: round(100 * sum(1 for d in docs if not fn(d)) / len(docs), 1)
                for name, fn in FIELDS.items()
            },
        }
    return out


def compare(current: dict, previous: dict | None, error_lines: dict[str, int]) -> dict[str, dict[str, Any]]:
    verdicts: dict[str, dict[str, Any]] = {}
    for src, cur in current.items():
        reasons: list[str] = []
        status = "ok"
        prev = (previous or {}).get(src)
        if prev:
            if prev["count"] and cur["count"] < prev["count"] * (1 - DROP_RATIO):
                status = "fail"
                reasons.append(f"공고 수 {prev['count']} → {cur['count']}")
            for field, pct in cur["missing_pct"].items():
                before = prev["missing_pct"].get(field)
                if before is not None and pct - before > MISSING_PP:
                    status = "fail"
                    reasons.append(f"{field} 결측 {before}% → {pct}%")
        if error_lines.get(src) and status == "ok":
            status = "warn"
            reasons.append(f"수집 로그 ERROR {error_lines[src]}줄")
        verdicts[src] = {"status": status, "reasons": reasons}
    for src in (previous or {}):
        if src not in current:
            verdicts[src] = {"status": "fail", "reasons": ["이번 수집에 공고가 없음"]}
    return verdicts


def _runs() -> list[Path]:
    return sorted(p for p in RUNS_DIR.glob("*") if (p / "summary.json").exists())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="수집 실행 id (기본: 가장 최근)")
    args = ap.parse_args()

    runs = _runs()
    if not runs:
        print("수집 실행 기록이 없습니다. 먼저 scripts/collect_all.py 를 실행하세요.", file=sys.stderr)
        return 1
    run_dir = RUNS_DIR / args.run if args.run else runs[-1]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    store = JobPostingStore().load(summary.get("data_dir"))
    current = measure(store.postings)

    # 같은 데이터 위치를 쓴 직전 실행 중 품질 기록이 있는 것
    previous = None
    for p in reversed(runs):
        if p == run_dir or not (p / "quality.json").exists():
            continue
        prev_q = json.loads((p / "quality.json").read_text(encoding="utf-8"))
        if prev_q.get("data_dir") == summary.get("data_dir") and p.name < run_dir.name:
            previous = prev_q
            break

    errors = {s["source"]: s.get("error_lines", 0) for s in summary.get("sites", [])}
    verdicts = compare(current, previous and previous["metrics"], errors)
    failed = [s for s, v in verdicts.items() if v["status"] == "fail"]

    report = {
        "run_id": run_dir.name,
        "data_dir": summary.get("data_dir"),
        "baseline_run": previous["run_id"] if previous else None,
        "passed": not failed,
        "metrics": current,
        "verdicts": verdicts,
    }
    (run_dir / "quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"기준선: {report['baseline_run'] or '없음 (이번 실행이 기준선)'}")
    for src, v in sorted(verdicts.items()):
        n = current.get(src, {}).get("count", 0)
        print(f"  {v['status']:<4} {src:<10} {n:>5}건  {'; '.join(v['reasons'])}")
    print("통과" if not failed else f"실패: {', '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
