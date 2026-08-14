#!/usr/bin/env python3
"""
실사용 패턴을 흉내 낸 MCP tool 질의 시뮬레이션.

카테고리별 5~10개, 총 40~60건을 실행하고 JSONL 모니터링 로그를 남긴다.
분석 리포트도 같은 실행에서 stdout으로 출력한다.

사용:
  PYTHONPATH=. python scripts/simulate_mcp_queries.py
  PYTHONPATH=. python scripts/simulate_mcp_queries.py --log logs/sim_baseline.jsonl
  PYTHONPATH=. python scripts/simulate_mcp_queries.py --analyze-only logs/sim_baseline.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 시뮬레이션 중 stderr 요약은 끄고 JSONL만 남김 (리포트가 깨끗하도록)
os.environ.setdefault("MCP_MONITOR_QUIET", "1")

from src.mcp_server.data_loader import get_store, reset_store  # noqa: E402
from src.mcp_server.monitoring import monitored_call, set_log_path  # noqa: E402
from src.mcp_server.tools.category_stats import get_posting_count_by_category  # noqa: E402
from src.mcp_server.tools.company_activity import get_company_hiring_activity  # noqa: E402
from src.mcp_server.tools.salary_summary import get_salary_summary  # noqa: E402
from src.mcp_server.tools.search import search_job_postings  # noqa: E402
from src.mcp_server.tools.skill_trend import get_skill_trend  # noqa: E402


Query = tuple[str, str, Callable[..., Any], dict[str, Any]]


def build_queries() -> list[Query]:
    """(sim_category, tool_name, fn, kwargs) 목록."""
    q: list[Query] = []

    # 1) 정상적인 인기 케이스
    popular = [
        ("search_job_postings", search_job_postings, {"job_function": "Backend Engineer", "location": "서울", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_function": "Frontend Engineer", "location": "서울", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_function": "Data Scientist", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_function": "DevOps Engineer", "location": "Remote", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_category": "Engineering & Technology", "limit": 5}),
        ("get_skill_trend", get_skill_trend, {"job_function": "Backend Engineer", "top_n": 10}),
        ("get_skill_trend", get_skill_trend, {"job_function": "Data Scientist", "top_n": 10}),
        ("get_posting_count_by_category", get_posting_count_by_category, {}),
        ("get_salary_summary", get_salary_summary, {"job_function": "Backend Engineer", "location": "서울"}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "SpaceX", "limit": 5}),
    ]
    for tool, fn, kwargs in popular:
        q.append(("popular", tool, fn, kwargs))

    # 2) 희귀 케이스 (taxonomy 갭·커버리지 낮은 직무)
    rare = [
        ("search_job_postings", search_job_postings, {"job_function": "Data Labeling / Annotation Specialist", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_function": "Teacher / Instructor", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_function": "Nurse", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_function": "Curriculum Developer", "location": "서울", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_function": "Supply Chain Analyst", "limit": 5}),
        ("get_skill_trend", get_skill_trend, {"job_function": "Nurse"}),
        ("get_skill_trend", get_skill_trend, {"job_function": "Teacher / Instructor"}),
        ("get_salary_summary", get_salary_summary, {"job_function": "Data Labeling / Annotation Specialist"}),
        ("get_salary_summary", get_salary_summary, {"job_function": "Nurse", "location": "서울"}),
        ("search_job_postings", search_job_postings, {"job_category": "Healthcare", "limit": 5}),
    ]
    for tool, fn, kwargs in rare:
        q.append(("rare", tool, fn, kwargs))

    # 3) 오타/비표준 입력
    typo = [
        ("search_job_postings", search_job_postings, {"job_function": "Backned Engineer", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_function": "backend engineer", "limit": 5}),  # 대소문자
        ("search_job_postings", search_job_postings, {"job_function": "백엔드 엔지니어", "limit": 5}),
        ("search_job_postings", search_job_postings, {"location": "서울특별시", "job_function": "Backend Engineer", "limit": 5}),
        ("search_job_postings", search_job_postings, {"location": "Atlantis", "limit": 5}),
        ("search_job_postings", search_job_postings, {"job_category": "Engineering", "limit": 5}),
        ("get_skill_trend", get_skill_trend, {"job_function": "Data Scinetist"}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "NoSuchCompanyXYZ"}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "spacexx"}),
        ("get_salary_summary", get_salary_summary, {"job_function": "Product Manger"}),
    ]
    for tool, fn, kwargs in typo:
        q.append(("typo_nonstandard", tool, fn, kwargs))

    # 4) 경계값
    edge = [
        ("search_job_postings", search_job_postings, {"job_function": "Backend Engineer", "limit": 0}),
        ("search_job_postings", search_job_postings, {"job_function": "Backend Engineer", "limit": 9999}),
        ("search_job_postings", search_job_postings, {"job_function": "", "limit": 5}),
        ("search_job_postings", search_job_postings, {"location": "", "limit": 3}),
        ("search_job_postings", search_job_postings, {"job_function": "Backend Engineer", "location": "   ", "limit": 3}),
        ("get_skill_trend", get_skill_trend, {"job_function": "Backend Engineer", "top_n": 0}),
        ("get_skill_trend", get_skill_trend, {"job_function": "Backend Engineer", "top_n": 100}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "", "limit": 5}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "SpaceX", "limit": 0}),
        ("get_posting_count_by_category", get_posting_count_by_category, {"active_only": False}),
    ]
    for tool, fn, kwargs in edge:
        q.append(("edge", tool, fn, kwargs))

    # 5) 급여/회사 tool 혼합
    salary_company = [
        ("get_salary_summary", get_salary_summary, {"job_function": "Backend Engineer"}),
        ("get_salary_summary", get_salary_summary, {"location": "서울"}),
        ("get_salary_summary", get_salary_summary, {"job_function": "Recruiter"}),
        ("get_salary_summary", get_salary_summary, {"job_function": "Frontend Engineer", "location": "부산"}),
        ("get_salary_summary", get_salary_summary, {}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "Acme"}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "Google"}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "네이버"}),
        ("get_company_hiring_activity", get_company_hiring_activity, {"company_name": "Samsung"}),
        ("search_job_postings", search_job_postings, {"job_function": "Backend Engineer", "employment_type": "FULL_TIME", "limit": 5}),
    ]
    for tool, fn, kwargs in salary_company:
        q.append(("salary_company", tool, fn, kwargs))

    return q


def run_simulation(log_path: Path) -> list[dict[str, Any]]:
    set_log_path(log_path)
    if log_path.exists():
        log_path.unlink()

    reset_store()
    store = get_store(reload=True)
    print(f"Loaded {len(store.postings)} postings → log {log_path}", flush=True)

    events: list[dict[str, Any]] = []
    queries = build_queries()
    for i, (category, tool_name, fn, kwargs) in enumerate(queries, 1):
        try:
            monitored_call(tool_name, fn, category=category, **kwargs)
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}/{len(queries)}] EXCEPTION {tool_name}: {exc}", flush=True)
        # 방금 쓴 마지막 줄 읽기
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                events.append(json.loads(lines[-1]))
        print(f"[{i}/{len(queries)}] {category}/{tool_name}", flush=True)

    return events


def load_events(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def analyze(events: list[dict[str, Any]]) -> str:
    total = len(events)
    if total == 0:
        return "이벤트 없음."

    zero = [e for e in events if e.get("is_zero")]
    errors = [e for e in events if e.get("error")]
    unknown = [e for e in events if e.get("is_unknown_param")]
    empty = [e for e in events if e.get("is_empty")]
    ok = [e for e in events if e.get("status") == "ok"]

    by_cat_zero: dict[str, int] = Counter()
    by_cat_total: dict[str, int] = Counter()
    by_tool_dur: dict[str, list[float]] = defaultdict(list)
    by_status: Counter[str] = Counter()
    by_tool_zero: dict[str, int] = Counter()
    by_tool_total: dict[str, int] = Counter()

    for e in events:
        cat = e.get("sim_category") or "(none)"
        tool = e.get("tool") or "?"
        by_cat_total[cat] += 1
        by_tool_total[tool] += 1
        by_status[str(e.get("status"))] += 1
        by_tool_dur[tool].append(float(e.get("duration_ms") or 0))
        if e.get("is_zero"):
            by_cat_zero[cat] += 1
            by_tool_zero[tool] += 1

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("MCP Tool 모니터링 분석 리포트")
    lines.append("=" * 60)
    lines.append(f"총 호출: {total}")
    lines.append(f"status=ok: {len(ok)} ({100 * len(ok) / total:.1f}%)")
    lines.append(f"0건(is_zero): {len(zero)} ({100 * len(zero) / total:.1f}%)")
    lines.append(f"unknown_param/unknown_company: {len(unknown)} ({100 * len(unknown) / total:.1f}%)")
    lines.append(f"empty/no_salary_data: {len(empty)} ({100 * len(empty) / total:.1f}%)")
    lines.append(f"에러(예외): {len(errors)}")
    lines.append("")
    lines.append("--- status 분포 ---")
    for status, n in by_status.most_common():
        lines.append(f"  {status}: {n}")

    lines.append("")
    lines.append("--- 카테고리별 0건 비율 ---")
    for cat in sorted(by_cat_total.keys()):
        z = by_cat_zero[cat]
        t = by_cat_total[cat]
        lines.append(f"  {cat}: {z}/{t} ({100 * z / t:.1f}%)")

    lines.append("")
    lines.append("--- tool별 0건 비율 ---")
    for tool in sorted(by_tool_total.keys()):
        z = by_tool_zero[tool]
        t = by_tool_total[tool]
        lines.append(f"  {tool}: {z}/{t} ({100 * z / t:.1f}%)")

    lines.append("")
    lines.append("--- tool별 응답 시간 (ms) ---")
    for tool, durs in sorted(by_tool_dur.items()):
        avg = sum(durs) / len(durs)
        mx = max(durs)
        lines.append(f"  {tool}: n={len(durs)} avg={avg:.2f} max={mx:.2f}")

    lines.append("")
    lines.append("--- 에러 케이스 ---")
    if not errors:
        lines.append("  (없음)")
    else:
        for e in errors:
            lines.append(
                f"  [{e.get('sim_category')}] {e.get('tool')} "
                f"params={e.get('params')} err={e.get('error')}"
            )

    lines.append("")
    lines.append("--- 0건 케이스 상세 (패턴 파악) ---")
    for e in zero:
        lines.append(
            f"  [{e.get('sim_category')}] {e.get('tool')} "
            f"status={e.get('status')} params={json.dumps(e.get('params'), ensure_ascii=False)}"
        )

    # 개선 포인트 휴리스틱
    lines.append("")
    lines.append("--- 우선 개선 후보 (데이터 근거) ---")
    suggestions: list[tuple[int, str]] = []

    # typo: unknown_param 많으면 fuzzy/alias 개선
    typo_unknown = [
        e for e in events
        if e.get("sim_category") == "typo_nonstandard" and e.get("is_unknown_param")
    ]
    if typo_unknown:
        suggestions.append((
            1,
            f"오타/비표준 {len(typo_unknown)}건이 unknown_param/unknown_company. "
            "직무명 close-match 제안(회사 tool과 유사)이 임팩트 큼.",
        ))

    # rare empty
    rare_empty = [
        e for e in events
        if e.get("sim_category") == "rare" and e.get("status") in ("empty", "no_salary_data")
    ]
    if rare_empty:
        suggestions.append((
            2,
            f"희귀 직무 empty/no_salary_data {len(rare_empty)}건 — "
            "매칭 로직보다 데이터 부재 가능성 높음(수집 보강은 오늘 범위 밖).",
        ))

    # limit=0 still returns results? check edge
    limit_zero = [
        e for e in events
        if e.get("sim_category") == "edge"
        and isinstance(e.get("params"), dict)
        and e["params"].get("limit") == 0
        and (e.get("result_count") or 0) > 0
    ]
    if limit_zero:
        suggestions.append((
            1,
            f"limit=0 인데 {len(limit_zero)}건이 결과 반환 "
            f"(현재 max(1,min(limit,100)) 클램프). 경계값 의미와 불일치.",
        ))

    # location 서울특별시 empty while 서울 ok
    seoul_special = [
        e for e in events
        if isinstance(e.get("params"), dict)
        and e["params"].get("location") == "서울특별시"
        and e.get("is_zero")
    ]
    seoul_ok = [
        e for e in events
        if isinstance(e.get("params"), dict)
        and e["params"].get("location") == "서울"
        and e.get("status") == "ok"
    ]
    if seoul_special and seoul_ok:
        suggestions.append((
            1,
            "location='서울특별시'는 0건인데 '서울'은 성공 — "
            "지역 alias/정규화 부재가 확인됨.",
        ))

    # Korean job function
    ko_fn = [
        e for e in events
        if isinstance(e.get("params"), dict)
        and e["params"].get("job_function") == "백엔드 엔지니어"
        and e.get("is_unknown_param")
    ]
    if ko_fn:
        suggestions.append((
            1,
            "한글 직무명 '백엔드 엔지니어' → unknown_param. "
            "taxonomy alias가 MCP resolve 경로에 연결되지 않았을 수 있음.",
        ))

    # salary sparse
    no_sal = [e for e in events if e.get("status") == "no_salary_data"]
    if no_sal:
        suggestions.append((
            3,
            f"no_salary_data {len(no_sal)}건 — 데이터 희소 문제(안내 status는 이미 존재).",
        ))

    if not suggestions:
        suggestions.append((2, "뚜렷한 로직 버그보다 데이터 커버리지/입력 안내 이슈 위주."))

    suggestions.sort(key=lambda x: x[0])
    for i, (prio, text) in enumerate(suggestions[:5], 1):
        lines.append(f"  {i}. [우선순위 {prio}] {text}")

    lines.append("")
    lines.append("권장: 우선순위 1인 항목 중 오늘 고칠 수 있는 1~2개만 튜닝.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP tool 실사용 시뮬레이션")
    parser.add_argument(
        "--log",
        default=str(_ROOT / "logs" / "mcp_sim_baseline.jsonl"),
        help="JSONL 로그 경로",
    )
    parser.add_argument(
        "--analyze-only",
        metavar="PATH",
        help="실행 없이 기존 로그만 분석",
    )
    args = parser.parse_args()

    if args.analyze_only:
        events = load_events(Path(args.analyze_only))
        print(analyze(events))
        return

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    events = run_simulation(log_path)
    print()
    print(analyze(events))
    print(f"\n로그 저장: {log_path} ({len(events)} events)")


if __name__ == "__main__":
    main()
