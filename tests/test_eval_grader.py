"""evals 채점 로직 테스트 — API 호출 없이 가짜 도구 호출 기록으로 채점한다."""
from __future__ import annotations

import pytest

from evals.cases import Case, GroundTruth, extract_value
from evals.grader import grade, parse_answer
from evals.report import build_report
from evals.runner import estimate_cost


def _count_case(**expect_extra) -> Case:
    expect = {
        "type": "count",
        "tool": "search_job_postings",
        "args": {"job_function": "Backend Engineer", "source_name": "wanted"},
    } | expect_extra
    return Case(id="s01", category="site_specific", question="?", expect=expect)


def _search_call(total: int, count: int = 1, **args) -> dict:
    return {
        "name": "search_job_postings",
        "args": args,
        "result": {"status": "ok", "count": count, "total_matched": total, "results": []},
    }


class TestParseAnswer:
    def test_count_takes_last_answer_line(self):
        text = "정답: 3\n중간 설명\n정답: 1,204"
        assert parse_answer(text, "count") == 1204

    def test_count_with_markdown(self):
        assert parse_answer("**정답: 42건**", "count") == 42

    def test_full_width_colon(self):
        assert parse_answer("정답：17", "count") == 17

    def test_missing_line(self):
        assert parse_answer("총 42건입니다.", "count") is None

    def test_skills_list_strips_counts(self):
        got = parse_answer("정답: Java (89), AWS (66), Spring", "top_skills")
        assert got == ["Java", "AWS", "Spring"]

    def test_abstain(self):
        assert parse_answer("정답: 없음", "abstain") == "없음"
        assert parse_answer("정답: 없음", "count") == "없음"


class TestGrade:
    def test_correct(self):
        gt = GroundTruth("s01", 9, "ok", trap_value=66)
        g = grade(_count_case(), gt, [_search_call(9, source_name="wanted")], "정답: 9")
        assert (g.tool_ok, g.call_ok, g.answer_ok, g.trap_hit) == (True, True, True, False)

    def test_trap_value_is_flagged(self):
        gt = GroundTruth("s01", 9, "ok", trap_value=66)
        g = grade(_count_case(), gt, [_search_call(66)], "정답: 66")
        assert not g.answer_ok and g.trap_hit and not g.call_ok
        assert "함정" in g.reason

    def test_wrong_tool(self):
        gt = GroundTruth("s01", 9, "ok")
        calls = [{"name": "get_posting_count_by_category", "args": {}, "result": {"status": "ok"}}]
        g = grade(_count_case(), gt, calls, "정답: 9")
        assert not g.tool_ok
        assert g.answer_ok  # 값이 우연히 맞아도 tool_ok 로 구분된다

    def test_count_field_confusion(self):
        """목록 길이(count)를 전체 건수로 답한 경우."""
        gt = GroundTruth("q06", 189, "ok")
        g = grade(_count_case(), gt, [_search_call(189, count=3)], "정답: 3")
        assert g.call_ok and not g.answer_ok
        assert "답을 3" in g.reason

    def test_no_tool_call(self):
        gt = GroundTruth("s01", 9, "ok")
        g = grade(_count_case(), gt, [], "정답: 10")
        assert not g.tool_ok and "미호출" in g.reason

    def test_top_skills_order_insensitive(self):
        case = Case("k01", "skills", "?", {"type": "top_skills", "tool": "get_skill_trend", "k": 3})
        gt = GroundTruth("k01", ["Java", "AWS", "Spring"], "ok")
        call = {
            "name": "get_skill_trend",
            "args": {},
            "result": {"status": "ok", "skills": [{"skill": s, "count": 1} for s in ["Java", "AWS", "Spring", "Docker"]]},
        }
        g = grade(case, gt, [call], "정답: aws, Java, spring")
        assert g.call_ok and g.answer_ok

    def test_abstain(self):
        case = Case("n01", "abstain", "?", {"type": "abstain", "tool": "get_company_hiring_activity"})
        gt = GroundTruth("n01", "없음", "unknown_company")
        call = {"name": "get_company_hiring_activity", "args": {}, "result": {"status": "unknown_company"}}
        assert grade(case, gt, [call], "정답: 없음").answer_ok
        assert not grade(case, gt, [call], "정답: 3").answer_ok


def test_extract_category_count():
    exp = {"type": "category_count", "tool": "get_posting_count_by_category", "category": "Data & Analytics"}
    result = {"status": "ok", "categories": [{"category": "Data & Analytics", "count": 12}]}
    assert extract_value(exp, result) == 12


def test_extract_non_ok_status_is_none():
    exp = {"type": "count", "tool": "search_job_postings"}
    assert extract_value(exp, {"status": "unknown_param"}) is None


def test_estimate_cost():
    assert estimate_cost("claude-opus-5-5", 1_000_000, 0) == pytest.approx(4.0)
    assert estimate_cost("claude-haiku-5-5", 0, 1_000_000) == pytest.approx(0.5)
    assert estimate_cost("unknown-model", 10, 10) == 0.0


def test_report_renders():
    row = {
        "model": "claude-haiku-5-5", "case_id": "s01", "repeat": 1, "category": "site_specific",
        "tool_ok": True, "call_ok": True, "answer_ok": False, "trap_hit": True,
        "error": None, "reason": "함정 값 66", "latency_sec": 2.0,
        "input_tokens": 1000, "output_tokens": 100, "cost_usd": 0.0002,
    }
    meta = {"run_id": "t", "repeats": 1, "n_cases": 1}
    md = build_report([row], meta)
    assert "claude-haiku-5-5" in md and "함정 값 66" in md
