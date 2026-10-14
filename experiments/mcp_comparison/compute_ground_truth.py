#!/usr/bin/env python3
"""
MCP 비교 실험 v2 — 정답지 계산 + Before/After 통합 템플릿 생성.

집계 기준은 실제 MCP tool 구현과 동일하다.
pandas 재계산은 tool 결과와 교차검증용이며, 불일치 시 실패한다.

사용 (프로젝트 루트):
  PYTHONPATH=. python experiments/mcp_comparison/compute_ground_truth.py
  PYTHONPATH=. python experiments/mcp_comparison/compute_ground_truth.py --force-templates
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.mcp_server.data_loader import JobPostingStore  # noqa: E402
from src.mcp_server.tools.category_stats import get_posting_count_by_category  # noqa: E402
from src.mcp_server.tools.company_activity import (  # noqa: E402
    _norm_company_key,
    get_company_hiring_activity,
)
from src.mcp_server.tools.salary_summary import (  # noqa: E402
    _has_salary_amount,
    get_salary_summary,
)
from src.mcp_server.tools.search import (  # noqa: E402
    _location_blob,
    _norm_enum_token,
    search_job_postings,
)
from src.mcp_server.tools.skill_trend import get_skill_trend  # noqa: E402
from src.taxonomy.job_categories import JOB_CATEGORIES  # noqa: E402

HERE = Path(__file__).resolve().parent
QUESTIONS_PATH = HERE / "questions.json"
GROUND_TRUTH_PATH = HERE / "ground_truth.json"
TEMPLATE_PATH = HERE / "before_after_template.json"

MIN_SAMPLE_SIZE = 20

TIME_INSTRUCTION = (
    "답변 맨 마지막 줄에 `응답시간: N초` 형식으로, 이 답을 생성하는 데 걸린 시간을 "
    "적어주세요. 메시지 하단 등 화면에 생성 시간이 보이면 그 숫자를 쓰고, 없으면 "
    "대략 초를 쓰되 `(추정)`을 붙이세요."
)
BEFORE_INSTRUCTION = (
    "별도 도구나 내부 데이터 없이, 일반적인 웹 검색만으로 답해주세요.\n"
    + TIME_INSTRUCTION
)
AFTER_INSTRUCTION = (
    "이 대화에 연결된 도구와 웹 검색을 모두 사용해서 답해주세요. "
    "도구 결과만으로 끝내지 말고, 웹에서 확인한 내용도 출처와 함께 적어주세요.\n"
    + TIME_INSTRUCTION
)
RETRY_AFTER_REFUSAL = (
    "정확한 실시간 수치가 없다면, 지금 웹 검색으로 확인 가능한 가장 최근 자료 "
    "기준으로 답해주세요. 출처마다 숫자가 다르면 그 점도 같이 알려주세요."
)


def _template_has_answers(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    for item in doc.get("items") or []:
        if str(item.get("before_answer") or "").strip():
            return True
        if str(item.get("after_answer") or "").strip():
            return True
        if str(item.get("answer") or "").strip():
            return True
    return False


def load_questions() -> dict[str, Any]:
    return json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))


def _skill_names(doc: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for skill in doc.get("skills") or []:
        if not isinstance(skill, dict):
            continue
        name = (skill.get("canonical_name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _salary_fields(doc: dict[str, Any]) -> tuple[str, str, str, str]:
    sal = doc.get("salary") or {}
    if not isinstance(sal, dict):
        return "", "", "", ""
    return (
        str(sal.get("min_amount") or ""),
        str(sal.get("max_amount") or ""),
        str(sal.get("currency_code") or ""),
        str(sal.get("pay_period") or ""),
    )


def docs_to_frame(docs: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for doc in docs:
        loc = doc.get("location") if isinstance(doc.get("location"), dict) else {}
        company = doc.get("company") if isinstance(doc.get("company"), dict) else {}
        min_a, max_a, cur, period = _salary_fields(doc)
        rows.append(
            {
                "job_function": (doc.get("job_function_name") or "").strip(),
                "job_category": (doc.get("job_category_name") or "").strip(),
                "employment_type": doc.get("employment_type_name") or "",
                "employment_type_norm": _norm_enum_token(
                    doc.get("employment_type_name") or ""
                ),
                "work_arrangement": doc.get("work_arrangement") or "",
                "location_blob": _location_blob(doc),
                "skills": _skill_names(doc),
                "salary_min": min_a,
                "salary_max": max_a,
                "salary_currency": cur,
                "salary_pay_period": period,
                "has_salary": _has_salary_amount(doc),
                "crawl_status": doc.get("crawl_status") or "ACTIVE",
                "company_key": _norm_company_key(str(company.get("name") or "")),
                "source_name": (doc.get("source_name") or ""),
            }
        )
    return pd.DataFrame(rows)


def active_mask(frame: pd.DataFrame) -> pd.Series:
    return frame["crawl_status"].fillna("ACTIVE") == "ACTIVE"


def pandas_search_count(
    frame: pd.DataFrame,
    *,
    job_function: str | None = None,
    job_category: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    work_arrangement: str | None = None,
    source_name: str | None = None,
) -> int:
    sub = frame[active_mask(frame)]
    if job_function:
        sub = sub[sub["job_function"] == job_function]
    if job_category:
        sub = sub[sub["job_category"] == job_category]
    if location:
        loc_q = location.strip().lower()
        sub = sub[sub["location_blob"].str.contains(loc_q, regex=False, na=False)]
    if employment_type:
        emp_q = employment_type.strip().lower()
        emp_q_norm = _norm_enum_token(emp_q)
        emp_doc = sub["employment_type_norm"]
        emp_raw = sub["employment_type"].str.lower()
        sub = sub[(emp_doc == emp_q_norm) | emp_raw.str.contains(emp_q, regex=False, na=False)]
    if work_arrangement:
        arr_q = work_arrangement.strip().lower()
        sub = sub[sub["work_arrangement"].str.lower().str.contains(arr_q, regex=False, na=False)]
    if source_name:
        sub = sub[sub["source_name"] == source_name]
    return int(len(sub))


def pandas_skill_top_n(
    frame: pd.DataFrame, job_function: str, top_n: int
) -> tuple[int, list[dict[str, Any]]]:
    sub = frame[active_mask(frame) & (frame["job_function"] == job_function)]
    counter: Counter[str] = Counter()
    for skills in sub["skills"]:
        for name in skills:
            counter[name] += 1
    ranked = [{"skill": s, "count": int(c)} for s, c in counter.most_common(top_n)]
    return int(len(sub)), ranked


def pandas_category_counts(frame: pd.DataFrame) -> dict[str, Any]:
    sub = frame[active_mask(frame)]
    counts = {c: 0 for c in JOB_CATEGORIES}
    uncategorized = 0
    for cat in sub["job_category"]:
        if cat in counts:
            counts[cat] += 1
        else:
            uncategorized += 1
    categories = [{"category": c, "count": counts[c]} for c in JOB_CATEGORIES]
    categories.sort(key=lambda x: (-x["count"], x["category"]))
    return {
        "total_postings": int(sum(counts.values()) + uncategorized),
        "uncategorized_count": int(uncategorized),
        "categories": categories,
    }


def _parse_amount(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def pandas_salary_summary(frame: pd.DataFrame, job_function: str) -> dict[str, Any]:
    sub = frame[active_mask(frame) & (frame["job_function"] == job_function)]
    with_sal = sub[sub["has_salary"]]
    groups: dict[tuple[str, str], list[tuple[Decimal | None, Decimal | None]]] = defaultdict(
        list
    )
    for _, row in with_sal.iterrows():
        currency = (row["salary_currency"] or "").strip() or "UNKNOWN"
        period = (row["salary_pay_period"] or "").strip() or "UNKNOWN"
        groups[(currency, period)].append(
            (_parse_amount(row["salary_min"]), _parse_amount(row["salary_max"]))
        )

    def _dec_to_json(value: Decimal) -> float | int:
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    summaries: list[dict[str, Any]] = []
    for (currency, period), ranges in sorted(
        groups.items(), key=lambda item: (-len(item[1]), item[0][0], item[0][1])
    ):
        mids: list[Decimal] = []
        group_mins_f: list[Decimal] = []
        group_maxs_f: list[Decimal] = []
        for mn, mx in ranges:
            if mn is not None and mx is not None:
                mids.append((mn + mx) / 2)
            elif mn is not None:
                mids.append(mn)
            elif mx is not None:
                mids.append(mx)
            if mn is not None or mx is not None:
                group_mins_f.append(mn if mn is not None else mx)  # type: ignore[arg-type]
                group_maxs_f.append(mx if mx is not None else mn)  # type: ignore[arg-type]
        if not mids or not group_mins_f or not group_maxs_f:
            continue
        avg = sum(mids) / len(mids)
        summaries.append(
            {
                "currency_code": currency,
                "pay_period": period,
                "group_sample_count": len(ranges),
                "min": _dec_to_json(min(group_mins_f)),
                "max": _dec_to_json(max(group_maxs_f)),
                "avg": _dec_to_json(avg),
            }
        )
    return {
        "matched_postings": int(len(sub)),
        "salary_data_count": int(len(with_sal)),
        "summaries": summaries,
    }


def pandas_company_count(frame: pd.DataFrame, company_name: str) -> int:
    key = _norm_company_key(company_name)
    sub = frame[active_mask(frame) & (frame["company_key"] == key)]
    return int(len(sub))


def _assert_equal(label: str, left: Any, right: Any) -> None:
    if left != right:
        raise AssertionError(f"pandas 교차검증 실패 ({label}): tool={left!r} pandas={right!r}")


def _assert_close_summaries(tool_s: list[dict], pandas_s: list[dict]) -> None:
    _assert_equal("salary groups len", len(tool_s), len(pandas_s))
    for a, b in zip(tool_s, pandas_s):
        _assert_equal("currency", a["currency_code"], b["currency_code"])
        _assert_equal("pay_period", a["pay_period"], b["pay_period"])
        _assert_equal("group_sample_count", a["group_sample_count"], b["group_sample_count"])
        _assert_equal("min", a["min"], b["min"])
        _assert_equal("max", a["max"], b["max"])
        if not math.isclose(float(a["avg"]), float(b["avg"]), rel_tol=1e-9, abs_tol=1e-6):
            raise AssertionError(f"avg mismatch {a['avg']} vs {b['avg']}")


def compute_one(
    q: dict[str, Any], store: JobPostingStore, frame: pd.DataFrame
) -> dict[str, Any]:
    qid = q["question_id"]
    tools = q["tools"]
    params = q["tool_params"]
    tool = tools[0]

    if tool == "search_job_postings":
        out = search_job_postings(store=store, **params)
        n = int(out["total_matched"])
        pd_n = pandas_search_count(
            frame,
            job_function=params.get("job_function"),
            job_category=params.get("job_category"),
            location=params.get("location"),
            employment_type=params.get("employment_type"),
            work_arrangement=params.get("work_arrangement"),
        )
        _assert_equal(qid, n, pd_n)
        expected = {"total_matched": n, "status": out["status"]}
        scoring = {
            "type": "exact_count",
            "field": "total_matched",
            "correct_if": f"우리 데이터셋 건수 == {n}",
            "common_error": (
                "search_job_postings의 count는 limit로 잘린 목록 길이. "
                "전체 건수는 total_matched. 웹의 시장 추정치는 오답."
            ),
        }
        if q.get("category") == "broad_control":
            scoring["control_note"] = (
                "직무 무관 대조군. 스냅샷 일치(440)가 채점 정답이지만, "
                "웹 잡보드 전수와 모집단이 달라 MCP가 있어도 시장 숫자와는 맞춰지지 않는다."
            )
    elif tool == "get_skill_trend":
        out = get_skill_trend(store=store, **params)
        pd_n, pd_skills = pandas_skill_top_n(
            frame, params["job_function"], params.get("top_n", 5)
        )
        _assert_equal(f"{qid}.posting_count", out["posting_count"], pd_n)
        _assert_equal(f"{qid}.skills", out["skills"], pd_skills)
        expected = {
            "job_function": out["job_function"],
            "posting_count": out["posting_count"],
            "skills": out["skills"],
            "status": out["status"],
        }
        scoring = {
            "type": "ranked_skills",
            "correct_if": "우리 데이터셋 top 5 스킬 이름과 count가 정답과 동일 (순서 포함)",
            "tie_note": "동점은 Counter.most_common (tool) 순서.",
        }
    elif tool == "get_posting_count_by_category":
        out = get_posting_count_by_category(store=store, **params)
        pd_out = pandas_category_counts(frame)
        _assert_equal(f"{qid}.total", out["total_postings"], pd_out["total_postings"])
        _assert_equal(
            f"{qid}.uncat", out["uncategorized_count"], pd_out["uncategorized_count"]
        )
        _assert_equal(f"{qid}.categories", out["categories"], pd_out["categories"])
        expected = {
            "total_postings": out["total_postings"],
            "uncategorized_count": out["uncategorized_count"],
            "categories": out["categories"],
            "status": out["status"],
        }
        scoring = {
            "type": "category_histogram",
            "correct_if": "15개 직군 count·0건 직군·uncategorized·total이 데이터셋과 일치",
        }
    elif tool == "get_salary_summary":
        out = get_salary_summary(store=store, **params)
        pd_out = pandas_salary_summary(frame, params["job_function"])
        _assert_equal(
            f"{qid}.matched", out["matched_postings"], pd_out["matched_postings"]
        )
        _assert_equal(
            f"{qid}.salary_n", out["salary_data_count"], pd_out["salary_data_count"]
        )
        _assert_close_summaries(out["summaries"], pd_out["summaries"])
        expected = {
            "matched_postings": out["matched_postings"],
            "salary_data_count": out["salary_data_count"],
            "job_function": out["job_function"],
            "summaries": out["summaries"],
            "status": out["status"],
        }
        scoring = {
            "type": "salary_grouped",
            "correct_if": (
                "salary_data_count·matched_postings와 통화/pay_period 그룹별 min/max/avg가 "
                "데이터셋과 일치"
            ),
            "common_error": "웹 연봉 조사 평균이나 가장 큰 그룹의 group_sample_count를 전체로 답하는 경우",
        }
    elif tool == "get_company_hiring_activity":
        out = get_company_hiring_activity(store=store, **params)
        pd_n = pandas_company_count(frame, params["company_name"])
        _assert_equal(qid, out["matched_postings"], pd_n)
        expected = {
            "company_name": out["company_name"],
            "matched_postings": out["matched_postings"],
            "status": out["status"],
        }
        scoring = {
            "type": "exact_count",
            "field": "matched_postings",
            "correct_if": f"우리 데이터셋 건수 == {out['matched_postings']}",
        }
    else:
        raise ValueError(f"unknown tool {tool} for {qid}")

    n_sample = int(q["sample_size"])
    reported_n = expected.get("total_matched")
    if reported_n is None:
        reported_n = expected.get("matched_postings")
    if reported_n is None:
        reported_n = expected.get("posting_count")
    if reported_n is None:
        reported_n = expected.get("total_postings")
    if reported_n != n_sample:
        raise AssertionError(
            f"{qid}: questions.json sample_size={n_sample} 이지만 계산값={reported_n}"
        )
    # broad_control은 직무 무관 대조군. 표본은 커도 웹 전수와 모집단이 다르다.
    if q.get("category") != "broad_control" and n_sample < MIN_SAMPLE_SIZE:
        raise AssertionError(f"{qid}: sample_size {n_sample} < {MIN_SAMPLE_SIZE}")

    return {
        "question_id": qid,
        "category": q["category"],
        "question": q["question"],
        "tools": tools,
        "tool_params": params,
        "why_web_search_differs": q.get("why_web_search_differs"),
        "computation": (
            f"src.mcp_server.tools 의 {tool}() 호출 결과를 정답으로 저장하고, "
            "동일 규칙의 pandas 집계로 교차검증함. "
            "채점은 시장 일반론이 아니라 이 expected와 일치하는지로 한다."
        ),
        "expected": expected,
        "scoring": scoring,
        "sample_size": n_sample,
    }


def main() -> None:
    spec = load_questions()
    questions: list[dict[str, Any]] = spec["questions"]
    store = JobPostingStore().load()
    frame = docs_to_frame(store.postings)
    total_active = int(active_mask(frame).sum())

    print(f"loaded postings={len(store.postings)} active={total_active}")
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
        print(f"  {q['question_id']} {q['category']:14} n={q['sample_size']}")

    ground = {
        "meta": {
            "experiment_version": 3,
            "source_questions": str(QUESTIONS_PATH.relative_to(_ROOT)),
            "data_dir": str(store.data_dir),
            "total_postings": len(store.postings),
            "active_postings": total_active,
            "n_questions": len(ground_items),
            "min_sample_size": MIN_SAMPLE_SIZE,
            "scoring_rule": (
                "객관적 시장 정답이 아니라 MCP tool이 이 스냅샷에서 계산한 수치와 "
                "일치하는지가 정답이다."
            ),
            "computation_rule": (
                "정답은 MCP tool 함수 호출 결과. pandas는 동일 규칙 교차검증. "
                "Full-time은 _norm_enum_token 동등 비교. "
                "스킬은 skills[].canonical_name, 공고당 1회."
            ),
            "smallest_sample": min(q["sample_size"] for q in questions),
            "smallest_question_ids": [
                q["question_id"]
                for q in questions
                if q["sample_size"] == min(x["sample_size"] for x in questions)
            ],
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
            "skip template: before_after_template.json already has answers. "
            "Pass --force-templates to overwrite."
        )
    else:
        template_doc = {
            "meta": {
                "experiment_version": 3,
                "condition_before": "web_search_on, mcp_off",
                "condition_after": "web_search_on, mcp_on",
                "instructions": (
                    "Before: prompt_to_paste_before 를 붙여넣으세요. "
                    "거절하면 같은 대화에 retry_after_refusal 한 번. "
                    "After: prompt_to_paste_after (연결된 도구 + 웹 검색 지시 + 응답시간 + 질문) 를 붙여넣으세요. "
                    "도구만 쓰거나 웹만 써도 고치지 말고 그대로 기록합니다. "
                    "답 마지막 줄의 N을 before_response_time_sec / after_response_time_sec 에 넣으세요. "
                    "수동 타이머는 쓰지 않습니다."
                ),
                "retry_after_refusal": RETRY_AFTER_REFUSAL,
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
    print(
        "sample_size range: "
        f"{min(q['sample_size'] for q in questions)}–{max(q['sample_size'] for q in questions)}"
    )


if __name__ == "__main__":
    main()
