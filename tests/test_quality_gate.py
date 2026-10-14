"""scripts/quality_gate.py — 직전 수집 대비 판정."""
from __future__ import annotations

from scripts.quality_gate import compare, measure


def _m(count, **missing):
    return {"count": count, "missing_pct": {"스킬": 10.0, "직무": 5.0} | missing}


def test_first_run_has_no_baseline():
    v = compare({"wanted": _m(100)}, None, {})
    assert v["wanted"]["status"] == "ok"


def test_count_drop_fails():
    v = compare({"wanted": _m(40)}, {"wanted": _m(100)}, {})
    assert v["wanted"]["status"] == "fail" and "100 → 40" in v["wanted"]["reasons"][0]


def test_missing_rate_jump_fails():
    """파서가 깨져 스킬을 못 뽑는 경우 — 건수는 그대로인데 결측이 급증한다."""
    v = compare({"saramin": _m(100, 스킬=80.0)}, {"saramin": _m(100)}, {})
    assert v["saramin"]["status"] == "fail" and "스킬" in v["saramin"]["reasons"][0]


def test_error_lines_warn_only():
    v = compare({"wanted": _m(100)}, {"wanted": _m(100)}, {"wanted": 4})
    assert v["wanted"]["status"] == "warn"


def test_site_disappeared_fails():
    v = compare({}, {"rallit": _m(50)}, {})
    assert v["rallit"]["status"] == "fail"


def test_measure_missing_pct():
    docs = [
        {"source_name": "a", "skills": [{"canonical_name": "Python"}], "job_function_name": "X"},
        {"source_name": "a", "skills": [], "job_function_name": ""},
    ]
    m = measure(docs)
    assert m["a"]["count"] == 2
    assert m["a"]["missing_pct"]["스킬"] == 50.0
    assert m["a"]["missing_pct"]["직무"] == 50.0
