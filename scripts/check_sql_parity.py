"""스냅샷 전체로 MCP tool 의 메모리 경로와 SQL 경로 응답을 비교한다.

  DATABASE_URL=postgresql://.../jobtrend \\
      python scripts/check_sql_parity.py --archive data/data-archive/data_snapshot_20260803.tar.gz

메모리 쪽은 스냅샷을 풀어 renormalize_doc 한 문서를 임시 폴더에 JSON 으로 써서
JobPostingStore().load() 로 읽는다. SQL 쪽은 DATABASE_URL 의 DB(backfill 로 적재한 것)를 조회한다.
같으면 `parity OK: <n> queries`, 다르면 다른 질문 목록을 출력하고 종료 코드 1.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.connection import reset_pool  # noqa: E402
from src.db.renormalize import renormalize_doc  # noqa: E402
from src.mcp_server.data_loader import JobPostingStore  # noqa: E402
from src.mcp_server.tools.category_stats import get_posting_count_by_category  # noqa: E402
from src.mcp_server.tools.company_activity import (  # noqa: E402
    _company_index,
    _norm_company_key,
    get_company_hiring_activity,
)
from src.mcp_server.tools.search import _company_name, search_job_postings  # noqa: E402
from src.mcp_server.tools.salary_summary import get_salary_summary  # noqa: E402
from src.mcp_server.tools.skill_trend import get_skill_trend  # noqa: E402

_COUNT_FIELDS = (
    "count", "total_matched", "posting_count", "total_postings", "uncategorized_count",
    "matched_postings", "salary_data_count",
)
# 목록 키 → (이름 필드, 건수 필드)
_NAMED_COUNTS = {
    "categories": ("category", "count"),
    "job_function_counts": ("job_function", "count"),
    "location_counts": ("location", "count"),
}


def iter_records(root: Path):
    for path in sorted((root / "data" / "job_postings").rglob("*.json")):
        if path.name.startswith("._"):  # macOS AppleDouble 메타 파일
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for rec in data if isinstance(data, list) else [data]:
            if isinstance(rec, dict):
                yield rec


def load_memory_store(archive: Path, workdir: Path) -> JobPostingStore:
    extracted = workdir / "extracted"
    with tarfile.open(archive) as tar:
        tar.extractall(extracted, filter="data")
    docs = [renormalize_doc(r) for r in iter_records(extracted)]
    dest = workdir / "store" / "job_postings"
    dest.mkdir(parents=True)
    (dest / "snapshot.json").write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")
    return JobPostingStore().load(workdir / "store")


def _skills_equal(mem: list[dict], sql: list[dict]) -> bool:
    """상위 N 경계의 동률 때문에 이름만 다른 경우는 건수가 같으면 같다고 본다."""
    if sorted(s["count"] for s in mem) != sorted(s["count"] for s in sql):
        return False
    m = {s["skill"]: s["count"] for s in mem}
    q = {s["skill"]: s["count"] for s in sql}
    if m == q:
        return True
    boundary = min(m.values())
    differing = set(m.items()) ^ set(q.items())
    return all(count == boundary for _, count in differing)


def diff(mem: dict[str, Any], sql: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if mem.get("status") != sql.get("status"):
        problems.append(f"status {mem.get('status')} != {sql.get('status')}")
    for field in _COUNT_FIELDS:
        if mem.get(field) != sql.get(field):
            problems.append(f"{field} {mem.get(field)} != {sql.get(field)}")
    if "skills" in mem and not _skills_equal(mem["skills"], sql.get("skills", [])):
        problems.append("skills differ")
    for key, (name, cnt) in _NAMED_COUNTS.items():
        if key in mem:
            m = {x[name]: x[cnt] for x in mem[key]}
            q = {x[name]: x[cnt] for x in sql.get(key, [])}
            if m != q:
                problems.append(f"{key} differ")
    if "summaries" in mem and mem["summaries"] != sql.get("summaries"):
        problems.append("summaries differ")
    return problems


def build_questions(store: JobPostingStore) -> list[tuple[Callable[..., dict], dict[str, Any]]]:
    questions: list[tuple[Callable[..., dict], dict[str, Any]]] = []
    for fn in store.known_functions:
        questions.append((search_job_postings, {"job_function": fn, "limit": 100}))
        questions.append((get_skill_trend, {"job_function": fn, "top_n": 50}))
        questions.append((get_salary_summary, {"job_function": fn}))
    for src in store.known_sources:
        questions.append((get_posting_count_by_category, {"source_name": src}))
        questions.append((search_job_postings, {"source_name": src, "limit": 100}))

    active = [d for d in store.postings if (d.get("crawl_status") or "ACTIVE") == "ACTIVE"]
    index = _company_index(active)
    per_company = Counter(
        _norm_company_key(str(_company_name(d))) for d in active if str(_company_name(d) or "").strip()
    )
    for key, _ in sorted(per_company.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
        questions.append((get_company_hiring_activity, {"company_name": index[key]}))

    questions.append((search_job_postings, {"limit": 100}))
    questions.append((get_posting_count_by_category, {}))
    questions.append((get_salary_summary, {}))
    return questions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", required=True, type=Path)
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        store = load_memory_store(args.archive, Path(tmp))
    questions = build_questions(store)
    print(f"memory postings={len(store.postings)} questions={len(questions)}")

    failures: list[str] = []
    for fn, kwargs in questions:
        problems = diff(fn(**kwargs, store=store), fn(**kwargs))
        if problems:
            failures.append(f"{fn.__name__}({kwargs}): {'; '.join(problems)}")

    if failures:
        print(f"parity FAILED: {len(failures)}/{len(questions)} queries differ")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"parity OK: {len(questions)} queries")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        reset_pool()
    raise SystemExit(code)
