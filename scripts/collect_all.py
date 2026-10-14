#!/usr/bin/env python3
"""
전체 사이트 수집 — 수집 계획(src/config/collect_plan.json)대로 사이트를 하나씩 돌리고 요약을 남긴다.

- 사이트마다 별도 프로세스로 실행해, 한 사이트가 실패하거나 멈춰도 나머지는 계속 돈다.
- 실행 전후 job_postings 를 세어 사이트별로 몇 건이 늘었는지 기록한다.
- 로그에서 ERROR 줄을 세어, 종료 코드는 0 이어도 일부 요청이 실패한 경우(예: API 422)를 잡는다.
- 결과는 data/collect_runs/<run_id>/ 에 summary.json 과 사이트별 로그로 남는다.

종료 코드: 0 전부 성공 · 1 일부 실패 또는 경고 · 2 전부 실패

사용:
  PYTHONPATH=. python scripts/collect_all.py                    # 계획 전체
  PYTHONPATH=. python scripts/collect_all.py --only wanted saramin
  PYTHONPATH=. python scripts/collect_all.py --dry-run          # 실행할 명령만 출력
  PYTHONPATH=. python scripts/collect_all.py --data-dir /tmp/x  # 다른 위치에 수집 (시험용)
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.mcp_server.data_loader import JobPostingStore  # noqa: E402

PLAN_PATH = _ROOT / "src" / "config" / "collect_plan.json"
DEFAULT_TIMEOUT_SEC = 60 * 60


def load_plan(path: Path = PLAN_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expand_args(args: list[str], plan: dict[str, Any]) -> list[str]:
    """{functions} · {kr_queries} 자리표시를 계획의 목록으로 펼친다."""
    out: list[str] = []
    for a in args:
        if a.startswith("{") and a.endswith("}") and a[1:-1] in plan:
            out.extend(plan[a[1:-1]])
        else:
            out.append(a)
    return out


def build_command(site: dict[str, Any], plan: dict[str, Any], data_dir: Path | None) -> list[str]:
    cmd = [sys.executable, str(_ROOT / "scripts" / site["script"]), *expand_args(site["args"], plan)]
    if data_dir is not None:
        cmd += ["--save-dir", str(data_dir)]
    return cmd


def count_by_source(data_dir: Path) -> Counter:
    """MCP 서버와 같은 기준(재수집 중복 제거 후)으로 사이트별 공고 수를 센다."""
    store = JobPostingStore().load(data_dir)
    return Counter(d.get("source_name") or "?" for d in store.postings)


def count_errors(log_path: Path) -> tuple[int, list[str]]:
    lines = [ln for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines() if "[ERROR]" in ln]
    return len(lines), [ln[:240] for ln in lines[:5]]


def run_site(site: dict[str, Any], cmd: list[str], log_path: Path, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    env = os.environ | {"PYTHONPATH": str(_ROOT)}
    with log_path.open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(cmd, cwd=_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            exit_code: int | None = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code, timed_out = None, True
    n_errors, samples = count_errors(log_path)
    return {
        "source": site["source"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_sec": round(time.monotonic() - started, 1),
        "error_lines": n_errors,
        "error_samples": samples,
        "log": str(log_path.relative_to(_ROOT)) if log_path.is_relative_to(_ROOT) else str(log_path),
    }


def classify(result: dict[str, Any]) -> str:
    if result["timed_out"] or result["exit_code"] != 0:
        return "failed"
    if result["error_lines"] or result["added"] == 0:
        return "warning"
    return "ok"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="+", help="이 사이트만 (source 이름)")
    p.add_argument("--data-dir", type=Path, help="수집 저장 위치 (기본: data/)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, help="사이트당 제한 시간(초)")
    p.add_argument("--include-disabled", action="store_true", help="enabled=false 사이트도 실행")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    plan = load_plan()
    sites = [s for s in plan["sites"] if s.get("enabled", True) or args.include_disabled]
    if args.only:
        sites = [s for s in plan["sites"] if s["source"] in set(args.only)]
    data_dir = args.data_dir or (_ROOT / "data")

    if args.dry_run:
        for s in sites:
            print(shlex.join(build_command(s, plan, args.data_dir)))
        skipped = [s["source"] for s in plan["sites"] if s not in sites]
        if skipped:
            print(f"# 제외: {', '.join(skipped)}")
        return 0

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = _ROOT / "data" / "collect_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    before = count_by_source(data_dir)
    results: list[dict[str, Any]] = []
    for s in sites:
        print(f"[{datetime.now():%H:%M:%S}] {s['source']} 시작", flush=True)
        res = run_site(s, build_command(s, plan, args.data_dir), run_dir / f"{s['source']}.log", args.timeout)
        after = count_by_source(data_dir)
        res["added"] = after[s["source"]] - before[s["source"]]
        res["total"] = after[s["source"]]
        res["status"] = classify(res)
        before = after
        results.append(res)
        print(
            f"[{datetime.now():%H:%M:%S}] {s['source']} {res['status']} "
            f"+{res['added']}건 (총 {res['total']}) ERROR {res['error_lines']}줄 {res['duration_sec']}s",
            flush=True,
        )

    statuses = Counter(r["status"] for r in results)
    overall = "failed" if statuses["failed"] == len(results) else ("ok" if statuses["ok"] == len(results) else "partial")
    summary = {
        "run_id": run_id,
        "overall": overall,
        "data_dir": str(data_dir),
        "total_postings": sum(before.values()),
        "by_source": dict(before.most_common()),
        "sites": results,
        "skipped": [s["source"] for s in plan["sites"] if s not in sites],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n전체 {overall} · 공고 {summary['total_postings']}건 · 요약 {run_dir / 'summary.json'}")
    return {"ok": 0, "partial": 1, "failed": 2}[overall]


if __name__ == "__main__":
    raise SystemExit(main())
