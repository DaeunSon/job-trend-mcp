#!/usr/bin/env python3
"""
튜닝 전후 동일 질의 비교표 생성.

사용:
  PYTHONPATH=. python scripts/compare_mcp_tuning.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.mcp_server.data_loader import get_store, reset_store
from src.mcp_server.tools.salary_summary import get_salary_summary
from src.mcp_server.tools.search import search_job_postings
from src.mcp_server.tools.skill_trend import get_skill_trend


# 모니터링에서 확인된 문제 질의 + 기대 개선
COMPARE_CASES = [
    {
        "id": "typo_backned",
        "tool": "search_job_postings",
        "params": {"job_function": "Backned Engineer", "limit": 5},
        "issue": "typo_nonstandard: Backned → unknown_param",
        "baseline": {"status": "unknown_param", "count": 0},
    },
    {
        "id": "ko_backend",
        "tool": "search_job_postings",
        "params": {"job_function": "백엔드 엔지니어", "limit": 5},
        "issue": "typo_nonstandard: 한글 alias 미연결",
        "baseline": {"status": "unknown_param", "count": 0},
    },
    {
        "id": "devops_alias",
        "tool": "search_job_postings",
        "params": {"job_function": "DevOps Engineer", "location": "Remote", "limit": 5},
        "issue": "popular: DevOps Engineer ≠ taxonomy명",
        "baseline": {"status": "unknown_param", "count": 0},
    },
    {
        "id": "typo_scientist",
        "tool": "get_skill_trend",
        "params": {"job_function": "Data Scinetist"},
        "issue": "typo_nonstandard: Data Scinetist",
        "baseline": {"status": "unknown_param", "count": 0},
    },
    {
        "id": "typo_pm",
        "tool": "get_salary_summary",
        "params": {"job_function": "Product Manger"},
        "issue": "typo_nonstandard: Product Manger",
        "baseline": {"status": "unknown_param", "count": 0},
    },
    {
        "id": "emp_full_time",
        "tool": "search_job_postings",
        "params": {
            "job_function": "Backend Engineer",
            "employment_type": "FULL_TIME",
            "limit": 5,
        },
        "issue": "salary_company: FULL_TIME vs Full-time 미스매치",
        "baseline": {"status": "empty", "count": 0},
    },
]


def _run(tool: str, params: dict):
    if tool == "search_job_postings":
        return search_job_postings(**params)
    if tool == "get_skill_trend":
        return get_skill_trend(**params)
    if tool == "get_salary_summary":
        return get_salary_summary(**params)
    raise ValueError(tool)


def _count(out: dict) -> int:
    if isinstance(out.get("count"), int):
        return out["count"]
    if isinstance(out.get("skills"), list):
        return len(out["skills"])
    if isinstance(out.get("salary_data_count"), int):
        return out["salary_data_count"]
    if isinstance(out.get("matched_postings"), int):
        return out["matched_postings"]
    return 0


def main() -> None:
    reset_store()
    get_store(reload=True)

    rows = []
    print("| id | 문제(모니터링) | 전 status/count | 후 status/count | 변화 |")
    print("|---|---|---|---|---|")
    for case in COMPARE_CASES:
        out = _run(case["tool"], case["params"])
        after = {"status": out.get("status"), "count": _count(out)}
        before = case["baseline"]
        changed = before != after
        marker = "개선" if (
            before.get("status") in ("unknown_param", "empty")
            and after.get("status") == "ok"
        ) else ("동일" if not changed else "변경")
        print(
            f"| {case['id']} | {case['issue']} | "
            f"{before['status']}/{before['count']} | "
            f"{after['status']}/{after['count']} | {marker} |"
        )
        rows.append({
            "id": case["id"],
            "issue": case["issue"],
            "params": case["params"],
            "before": before,
            "after": after,
            "message": out.get("message"),
        })

    out_path = _ROOT / "logs" / "mcp_tuning_compare.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON: {out_path}")


if __name__ == "__main__":
    main()
