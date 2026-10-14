#!/usr/bin/env python3
"""
수집 데이터 품질 리포트 — 사이트별 공고 수와 표준 필드 결측률.

MCP 서버와 같은 로더(get_store)를 써서, 도구가 실제로 보는 공고(재수집 중복 제거 후) 기준으로 센다.

사용:
  PYTHONPATH=. python scripts/data_quality_report.py              # 표준출력
  PYTHONPATH=. python scripts/data_quality_report.py --out docs/data_quality.md
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.mcp_server.data_loader import get_store  # noqa: E402


def _has_salary(d: dict) -> bool:
    s = d.get("salary") or {}
    return bool(s.get("min_amount") or s.get("max_amount"))


# 필드 이름 → 값이 채워졌는지 판단
FIELDS = {
    "직무": lambda d: bool(d.get("job_function_name")),
    "직군": lambda d: bool(d.get("job_category_name")),
    "고용형태": lambda d: bool(d.get("employment_type_name")),
    "근무형태": lambda d: bool(d.get("work_arrangement")),
    "스킬": lambda d: bool(d.get("skills")),
    "숫자 급여": _has_salary,
    "지역": lambda d: bool(
        (d.get("location") or {}).get("city_name")
        or (d.get("location") or {}).get("region_name")
        or (d.get("location") or {}).get("country_name")
    ),
    "게시일": lambda d: bool(d.get("posted_at")),
}


def build(postings: list[dict]) -> str:
    by_src: dict[str, list[dict]] = defaultdict(list)
    for d in postings:
        by_src[d.get("source_name") or "?"].append(d)
    total = len(postings)
    dates = sorted(str(d.get("created_at") or "")[:10] for d in postings if d.get("created_at"))

    lines = [
        "# 수집 데이터 품질\n",
        f"- 공고 {total}건 (재수집 중복 제거 후, MCP 도구가 보는 기준)",
        f"- 수집일 {dates[0]} ~ {dates[-1]}" if dates else "- 수집일 정보 없음",
        "",
        "## 사이트별 공고 수\n",
        "| 사이트 | 건수 | 비중 |",
        "|---|---|---|",
    ]
    for src, docs in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"| {src} | {len(docs)} | {100 * len(docs) / total:.0f}% |")

    lines += ["", "## 필드별 결측률 (비어 있는 비율)\n"]
    header = "| 사이트 | " + " | ".join(FIELDS) + " |"
    lines += [header, "|---|" + "---|" * len(FIELDS)]

    def row(name: str, docs: list[dict]) -> str:
        cells = []
        for fn in FIELDS.values():
            missing = sum(1 for d in docs if not fn(d))
            cells.append(f"{100 * missing / len(docs):.0f}%")
        return f"| {name} | " + " | ".join(cells) + " |"

    lines.append(row("**전체**", postings))
    for src, docs in sorted(by_src.items(), key=lambda kv: -len(kv[1])):
        lines.append(row(src, docs))

    fn_counts = Counter(d.get("job_function_name") or "(미분류)" for d in postings)
    lines += ["", "## 직무 분포 (상위 15)\n", "| 직무 | 건수 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in fn_counts.most_common(15)]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    store = get_store()
    if not store.postings:
        print("job_postings 가 비어 있습니다.", file=sys.stderr)
        raise SystemExit(1)
    md = build(store.postings)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"저장: {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
