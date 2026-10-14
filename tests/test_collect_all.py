"""scripts/collect_all.py — 수집 계획 해석과 사이트 상태 판정 (실제 수집 없음)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "collect_all.py"
_spec = importlib.util.spec_from_file_location("collect_all", _PATH)
collect_all = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect_all)


def test_plan_scripts_exist():
    plan = collect_all.load_plan()
    for site in plan["sites"]:
        assert (_PATH.parent / site["script"]).exists(), site["script"]


def test_plan_sources_are_known():
    from src.config.sources import ALL_SOURCES

    known = {s.source_name for s in ALL_SOURCES}
    assert {s["source"] for s in collect_all.load_plan()["sites"]} <= known


def test_expand_placeholders():
    plan = {"functions": ["A", "B"]}
    assert collect_all.expand_args(["--function", "{functions}", "--max-jobs", "5"], plan) == [
        "--function", "A", "B", "--max-jobs", "5",
    ]


def test_unknown_placeholder_kept():
    assert collect_all.expand_args(["{nope}"], {}) == ["{nope}"]


def test_build_command_adds_save_dir(tmp_path):
    site = {"source": "x", "script": "run_x.py", "args": ["--a"]}
    cmd = collect_all.build_command(site, {}, tmp_path)
    assert cmd[0] == sys.executable
    assert cmd[-2:] == ["--save-dir", str(tmp_path)]


def _res(**kw):
    base = {"timed_out": False, "exit_code": 0, "error_lines": 0, "added": 10}
    return base | kw


def test_classify():
    assert collect_all.classify(_res()) == "ok"
    assert collect_all.classify(_res(error_lines=3)) == "warning"   # 예: 일부 API 422
    assert collect_all.classify(_res(added=0)) == "warning"
    assert collect_all.classify(_res(exit_code=1)) == "failed"
    assert collect_all.classify(_res(exit_code=None, timed_out=True)) == "failed"


def test_jobkorea_disabled_by_default():
    plan = collect_all.load_plan()
    jk = next(s for s in plan["sites"] if s["source"] == "jobkorea")
    assert jk.get("enabled") is False


def test_network_failure_is_retryable():
    assert collect_all.classify(_res(error_lines=3, network_error_lines=3, added=0)) == "network"
    # 일부라도 받았으면 경고로 둔다
    assert collect_all.classify(_res(error_lines=3, network_error_lines=3, added=50)) == "warning"


def test_count_errors_separates_network(tmp_path):
    log = tmp_path / "x.log"
    log.write_text(
        "a [ERROR] Max retries exceeded (Caused by NameResolutionError(...))\n"
        "b [ERROR] 422 Client Error\n"
        "c [INFO] ok\n",
        encoding="utf-8",
    )
    total, network, samples = collect_all.count_errors(log)
    assert (total, network, len(samples)) == (2, 1, 2)
