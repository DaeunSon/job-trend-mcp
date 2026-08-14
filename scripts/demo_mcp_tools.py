#!/usr/bin/env python3
"""MCP tool들을 실제 data/job_postings 로 한 번 호출해 시연용 출력을 만든다."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp import Client

from src.mcp_server.server import mcp


def _print(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def main() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        tools = await client.list_tools()
        print("TOOLS:", [t.name for t in tools.tools])

        r1 = await client.call_tool(
            "search_job_postings",
            {"job_function": "Backend Engineer", "location": "서울", "limit": 3},
        )
        _print("search_job_postings", r1.structured_content)

        r2 = await client.call_tool(
            "get_skill_trend",
            {"job_function": "Backend Engineer", "top_n": 10},
        )
        _print("get_skill_trend", r2.structured_content)

        r3 = await client.call_tool("get_posting_count_by_category", {})
        _print("get_posting_count_by_category", r3.structured_content)

        r4 = await client.call_tool(
            "get_salary_summary",
            {"job_function": "Backend Engineer", "location": "서울"},
        )
        _print("get_salary_summary (with data)", r4.structured_content)

        r5 = await client.call_tool(
            "get_salary_summary",
            {"job_function": "Recruiter"},
        )
        _print("get_salary_summary (no_salary_data)", r5.structured_content)

        r6 = await client.call_tool(
            "get_company_hiring_activity",
            {"company_name": "SpaceX", "limit": 5},
        )
        _print("get_company_hiring_activity (exists)", r6.structured_content)

        r7 = await client.call_tool(
            "get_company_hiring_activity",
            {"company_name": "spacexx"},
        )
        _print("get_company_hiring_activity (unknown)", r7.structured_content)


if __name__ == "__main__":
    asyncio.run(main())
