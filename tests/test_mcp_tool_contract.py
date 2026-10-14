"""
MCP 도구 계약 테스트.

도구 이름 · 파라미터 · 응답 필드는 LLM 이 읽는 계약이다. 단위 테스트가 통과해도
이름이 바뀌면 모델의 호출이 깨지므로, 바뀌면 여기서 먼저 실패하게 둔다.
의도한 변경이면 EXPECTED 를 고치고, 평가(scripts/run_eval.py)를 다시 돌려 비교한다.
"""
from __future__ import annotations

import anyio
import pytest
from mcp import Client

from src.mcp_server.server import mcp

# 도구 이름 → (필수 파라미터, 전체 파라미터)
EXPECTED: dict[str, tuple[set[str], set[str]]] = {
    "search_job_postings": (
        set(),
        {"job_function", "job_category", "location", "employment_type",
         "work_arrangement", "source_name", "limit", "active_only"},
    ),
    "get_skill_trend": ({"job_function"}, {"job_function", "top_n", "active_only", "source_name"}),
    "get_posting_count_by_category": (set(), {"active_only", "source_name"}),
    "get_salary_summary": (set(), {"job_function", "location", "source_name"}),
    "get_company_hiring_activity": ({"company_name"}, {"company_name", "limit", "source_name"}),
}


@pytest.fixture(scope="module")
def tools() -> dict:
    async def _list():
        async with Client(mcp, raise_exceptions=True) as client:
            return (await client.list_tools()).tools

    return {t.name: t for t in anyio.run(_list)}


def test_tool_names(tools):
    assert set(tools) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_tool_parameters(tools, name):
    schema = tools[name].input_schema
    required, props = EXPECTED[name]
    assert set(schema.get("required", [])) == required
    assert set(schema["properties"]) == props


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_source_name_is_documented(tools, name):
    """모델이 source_name 에 직무명을 넣던 문제(#2) — 설명에 허용값이 있어야 한다."""
    desc = tools[name].description or ""
    assert "saramin" in desc and "job_function" in desc


def test_salary_description_names_overall_count_field(tools):
    desc = tools["get_salary_summary"].description or ""
    assert "salary_data_count" in desc and "group_sample_count" in desc


@pytest.mark.parametrize(
    "name, args, fields",
    [
        ("search_job_postings", {"limit": 1}, {"status", "count", "total_matched", "results"}),
        ("get_skill_trend", {"job_function": "Backend Engineer"}, {"status", "skills"}),
        ("get_posting_count_by_category", {}, {"status", "total_postings", "categories"}),
        ("get_salary_summary", {"job_function": "Backend Engineer"}, {"status", "matched_postings", "salary_data_count"}),
        ("get_company_hiring_activity", {"company_name": "zz-no-such-co"}, {"status"}),
    ],
)
def test_response_fields(name, args, fields):
    async def _call():
        async with Client(mcp, raise_exceptions=True) as client:
            return (await client.call_tool(name, args)).structured_content

    out = anyio.run(_call)
    assert fields <= set(out)
    assert out["status"] in {"ok", "empty", "unknown_param", "unknown_company", "no_salary_data"}


def test_unknown_param_has_no_total_matched():
    """잘못된 필터에 total_matched=0 을 주면 모델이 '0건'으로 답한다."""

    async def _call():
        async with Client(mcp, raise_exceptions=True) as client:
            args = {"job_function": "zz-not-a-role"}
            return (await client.call_tool("search_job_postings", args)).structured_content

    out = anyio.run(_call)
    assert out["status"] == "unknown_param" and "total_matched" not in out
