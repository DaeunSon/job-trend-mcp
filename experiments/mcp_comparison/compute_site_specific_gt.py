#!/usr/bin/env python3
"""
사이트 지정형 비교 실험 — 정답지 + 템플릿.

search_job_postings 의 source_name 필터로 사이트 GT를 계산하고,
필터 없이 호출한 값을 mcp_unfiltered 로 함께 둔다.
기존 compute_ground_truth.py / before_after_template.json 은 건드리지 않는다.

사용 (프로젝트 루트):
  PYTHONPATH=. python experiments/mcp_comparison/compute_site_specific_gt.py
  PYTHONPATH=. python experiments/mcp_comparison/compute_site_specific_gt.py --force-templates
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.mcp_server.data_loader import JobPostingStore  # noqa: E402
from src.mcp_server.tools.search import search_job_postings  # noqa: E402

HERE = Path(__file__).resolve().parent
QUESTIONS_PATH = HERE / "site_specific_questions.json"
GROUND_TRUTH_PATH = HERE / "site_specific_ground_truth.json"
TEMPLATE_PATH = HERE / "site_specific_template.json"

import importlib.util  # noqa: E402

_gt_spec = importlib.util.spec_from_file_location(
    "mcp_cmp_gt", HERE / "compute_ground_truth.py"
)
assert _gt_spec and _gt_spec.loader
_gt = importlib.util.module_from_spec(_gt_spec)
_gt_spec.loader.exec_module(_gt)

AFTER_INSTRUCTION = _gt.AFTER_INSTRUCTION
BEFORE_INSTRUCTION = _gt.BEFORE_INSTRUCTION
MIN_SAMPLE_SIZE = _gt.MIN_SAMPLE_SIZE
RETRY_AFTER_REFUSAL = _gt.RETRY_AFTER_REFUSAL
TIME_INSTRUCTION = _gt.TIME_INSTRUCTION
_template_has_answers = _gt._template_has_answers
active_mask = _gt.active_mask
docs_to_frame = _gt.docs_to_frame
pandas_search_count = _gt.pandas_search_count


def _assert_equal(label: str, left: Any, right: Any) -> None:
    if left != right:
        raise AssertionError(f"교차검증 실패 ({label}): {left!r} vs {right!r}")


def compute_one(
    q: dict[str, Any], store: JobPostingStore, frame
) -> dict[str, Any]:
    qid = q["question_id"]
    params = dict(q["tool_params"])
    source_name = q["source_name"]

    mcp_out = search_job_postings(store=store, **params)
    mcp_n = int(mcp_out.get("total_matched") or mcp_out.get("count") or 0)
    pd_unfiltered = pandas_search_count(
        frame,
        job_function=params.get("job_function"),
        job_category=params.get("job_category"),
        location=params.get("location"),
        employment_type=params.get("employment_type"),
        work_arrangement=params.get("work_arrangement"),
    )
    _assert_equal(f"{qid}.mcp_unfiltered", mcp_n, pd_unfiltered)

    filtered_out = search_job_postings(
        store=store, source_name=source_name, **params
    )
    filtered_n = int(
        filtered_out.get("total_matched") or filtered_out.get("count") or 0
    )
    pd_filtered = pandas_search_count(
        frame,
        job_function=params.get("job_function"),
        job_category=params.get("job_category"),
        location=params.get("location"),
        employment_type=params.get("employment_type"),
        work_arrangement=params.get("work_arrangement"),
        source_name=source_name,
    )
    _assert_equal(f"{qid}.source_filtered tool vs pandas", filtered_n, pd_filtered)

    n_src = int(q["sample_size_source_filtered"])
    n_mcp = int(q["sample_size_mcp_unfiltered"])
    _assert_equal(f"{qid}.source_filtered vs questions.json", pd_filtered, n_src)
    _assert_equal(f"{qid}.mcp_unfiltered vs questions.json", mcp_n, n_mcp)
    if n_src < 1:
        raise AssertionError(f"{qid}: source_filtered is 0")
    if n_mcp < MIN_SAMPLE_SIZE:
        raise AssertionError(f"{qid}: mcp_unfiltered {n_mcp} < {MIN_SAMPLE_SIZE}")

    return {
        "question_id": qid,
        "category": q["category"],
        "site_display_name": q["site_display_name"],
        "source_name": source_name,
        "question": q["question"],
        "tools": q["tools"],
        "tool_params": params,
        "computation": (
            "source_filtered는 search_job_postings(source_name=...) + pandas 교차검증. "
            "mcp_unfiltered는 source_name 없이 같은 직무×조건 호출."
        ),
        "expected": {
            "source_filtered_count": pd_filtered,
            "mcp_unfiltered_total_matched": mcp_n,
            "mcp_filtered_status": filtered_out["status"],
            "mcp_unfiltered_status": mcp_out["status"],
        },
        "scoring": {
            "type": "site_vs_mcp_gap",
            "site_truth": (
                f"search_job_postings(source_name={source_name!r}) "
                f"total_matched == {pd_filtered}"
            ),
            "after_if_tools_used": (
                f"source_name 을 쓰면 {pd_filtered}, "
                f"안 쓰면 통합 total_matched == {mcp_n}"
            ),
            "before_typical": "지정 사이트의 웹 검색 근사치·캐시 스니펫 (우리 크롤 N과 불일치 가능)",
            "common_error": (
                "search의 count(limit 자른 목록 길이)를 전체로 답하는 경우. "
                "사이트 지정 질문인데 MCP가 준 통합 건수를 사람인/잡코리아 숫자라고 말하는 경우."
            ),
        },
        "sample_size_source_filtered": n_src,
        "sample_size_mcp_unfiltered": n_mcp,
        "notes": q.get("notes"),
    }


def main() -> None:
    spec = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    questions: list[dict[str, Any]] = spec["questions"]
    store = JobPostingStore().load()
    frame = docs_to_frame(store.postings)
    frame["source_name"] = [
        (d.get("source_name") or "") for d in store.postings
    ]
    total_active = int(active_mask(frame).sum())

    print(f"loaded postings={len(store.postings)} active={total_active}")
    print("mcp source filter: yes (search_job_postings source_name)")
    print(f"questions={len(questions)}")

    ground_items: list[dict[str, Any]] = []
    template_items: list[dict[str, Any]] = []

    for q in questions:
        item = compute_one(q, store, frame)
        ground_items.append(item)
        template_items.append(
            {
                "question_id": q["question_id"],
                "question": q["question"],
                "category": q["category"],
                "site_display_name": q["site_display_name"],
                "source_name": q["source_name"],
                "before_instruction": BEFORE_INSTRUCTION,
                "prompt_to_paste_before": f"{BEFORE_INSTRUCTION}\n\n{q['question']}",
                "before_answer": "",
                "before_response_time_sec": None,
                "after_instruction": AFTER_INSTRUCTION,
                "prompt_to_paste_after": f"{AFTER_INSTRUCTION}\n\n{q['question']}",
                "after_answer": "",
                "after_response_time_sec": None,
                "matches_ground_truth": None,
            }
        )
        print(
            f"  {q['question_id']} {q['source_name']:10} "
            f"site={q['sample_size_source_filtered']} mcp={q['sample_size_mcp_unfiltered']}"
        )

    ground = {
        "meta": {
            "experiment_version": 3,
            "kind": "site_specific",
            "source_questions": str(QUESTIONS_PATH.relative_to(_ROOT)),
            "data_dir": str(store.data_dir),
            "total_postings": len(store.postings),
            "active_postings": total_active,
            "n_questions": len(ground_items),
            "mcp_source_filter": True,
            "scoring_rule": (
                "사이트 GT는 search_job_postings(source_name=...) 의 total_matched. "
                "source_name 없이 호출하면 mcp_unfiltered_total_matched. "
                "둘의 차이가 '사이트 지정 vs 통합 스냅샷' 대비이다."
            ),
        },
        "items": ground_items,
    }
    GROUND_TRUTH_PATH.write_text(
        json.dumps(ground, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    skip_templates = (
        "--force-templates" not in sys.argv and _template_has_answers(TEMPLATE_PATH)
    )
    if skip_templates:
        print(
            "skip template: site_specific_template.json already has answers. "
            "Pass --force-templates to overwrite."
        )
    else:
        template_doc = {
            "meta": {
                "experiment_version": 3,
                "kind": "site_specific",
                "condition_before": "web_search_on, mcp_off",
                "condition_after": "web_search_on, mcp_on",
                "mcp_source_filter": True,
                "instructions": (
                    "기존 18문항과 별도. Before: prompt_to_paste_before. "
                    "거절하면 retry_after_refusal 한 번. "
                    "After: prompt_to_paste_after (연결된 도구 + 웹 검색 지시 + 응답시간 + 질문, 사이트명 포함). "
                    "도구만 쓰거나 웹만 써도 고치지 말고 그대로 기록. "
                    "답 마지막 줄 N을 *_response_time_sec 에 넣음. 수동 타이머 없음."
                ),
                "retry_after_refusal": RETRY_AFTER_REFUSAL,
                "time_instruction": TIME_INSTRUCTION,
            },
            "items": template_items,
        }
        TEMPLATE_PATH.write_text(
            json.dumps(template_doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print("\nwrote:")
    print(f"  {GROUND_TRUTH_PATH.relative_to(_ROOT)}")
    if skip_templates:
        print("  (template unchanged)")
    else:
        print(f"  {TEMPLATE_PATH.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
