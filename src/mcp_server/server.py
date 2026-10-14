"""
Job Trend MCP 서버 (mcp Python SDK v2).

실행:
  # 로컬 stdio (기본)
  python -m src.mcp_server.server
  mcp dev src/mcp_server/server.py

  # Streamable HTTP (로컬 바인딩 127.0.0.1)
  python -m src.mcp_server.server --transport streamable-http --port 8000
  MCP_TRANSPORT=streamable-http MCP_PORT=8000 python -m src.mcp_server.server
"""
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from src.mcp_server.data_loader import get_store
from src.mcp_server.monitoring import monitor_tool
from src.mcp_server.tools import category_stats as category_stats_mod
from src.mcp_server.tools import company_activity as company_activity_mod
from src.mcp_server.tools import salary_summary as salary_summary_mod
from src.mcp_server.tools import search as search_mod
from src.mcp_server.tools import skill_trend as skill_trend_mod

mcp = MCPServer(
    "job-trend-mcp",
    instructions=(
        "Query normalized job postings collected from multiple job boards. "
        "Use search_job_postings for listings, get_skill_trend for skill "
        "frequency by job function, get_posting_count_by_category for "
        "category volume, get_salary_summary for salary stats by filters, "
        "and get_company_hiring_activity for a company's open roles. "
        "Prefer taxonomy job_function names (e.g. 'Backend Engineer')."
    ),
)

# 서버 import 시점에 데이터 1회 로드 (stdio 호스트가 모듈을 import할 때)
get_store()


@mcp.tool(
    name="search_job_postings",
    title="Search job postings",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
@monitor_tool("search_job_postings")
def search_job_postings(
    job_function: str | None = None,
    job_category: str | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    work_arrangement: str | None = None,
    source_name: str | None = None,
    limit: int = 20,
    active_only: bool = True,
) -> dict[str, Any]:
    """조건에 맞는 채용공고를 검색한다. 조건을 안 주면 최근 공고를 반환한다.

    source_name 은 수집 사이트 필터다: saramin(사람인), jobkorea(잡코리아), wanted(원티드), jumpit(점핏), rallit(랠릿), work24(고용24), remotive, themuse, arbeitnow, usajobs, adzuna. 직무·직군 이름은 job_function / job_category 에 넣는다.
    """
    return search_mod.search_job_postings(
        job_function=job_function,
        job_category=job_category,
        location=location,
        employment_type=employment_type,
        work_arrangement=work_arrangement,
        source_name=source_name,
        limit=limit,
        active_only=active_only,
    )


@mcp.tool(
    name="get_skill_trend",
    title="Skill trend by job function",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
@monitor_tool("get_skill_trend")
def get_skill_trend(
    job_function: str,
    top_n: int = 15,
    active_only: bool = True,
    source_name: str | None = None,
) -> dict[str, Any]:
    """특정 직무에서 가장 많이 요구되는 기술스택 상위 N개를 빈도순으로 반환한다.

    source_name 은 수집 사이트 필터다: saramin(사람인), jobkorea(잡코리아), wanted(원티드), jumpit(점핏), rallit(랠릿), work24(고용24), remotive, themuse, arbeitnow, usajobs, adzuna. 직무·직군 이름은 job_function / job_category 에 넣는다.
    """
    return skill_trend_mod.get_skill_trend(
        job_function=job_function,
        top_n=top_n,
        active_only=active_only,
        source_name=source_name,
    )


@mcp.tool(
    name="get_posting_count_by_category",
    title="Posting count by category",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
@monitor_tool("get_posting_count_by_category")
def get_posting_count_by_category(
    active_only: bool = True,
    source_name: str | None = None,
) -> dict[str, Any]:
    """직군(job_category)별 채용공고 수를 집계해 반환한다.

    source_name 은 수집 사이트 필터다: saramin(사람인), jobkorea(잡코리아), wanted(원티드), jumpit(점핏), rallit(랠릿), work24(고용24), remotive, themuse, arbeitnow, usajobs, adzuna. 직무·직군 이름은 job_function / job_category 에 넣는다.
    """
    return category_stats_mod.get_posting_count_by_category(
        active_only=active_only,
        source_name=source_name,
    )


@mcp.tool(
    name="get_salary_summary",
    title="Salary summary",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
@monitor_tool("get_salary_summary")
def get_salary_summary(
    job_function: str | None = None,
    location: str | None = None,
    source_name: str | None = None,
) -> dict[str, Any]:
    """직무·지역 조건에 맞는 채용공고의 급여 통계를 반환한다.

    전체 급여 표본 수는 salary_data_count 이다.
    summaries[*].group_sample_count 는 통화·pay_period 그룹별 건수이므로
    전체 건수와 혼동하지 말 것.

    source_name 은 수집 사이트 필터다: saramin(사람인), jobkorea(잡코리아), wanted(원티드), jumpit(점핏), rallit(랠릿), work24(고용24), remotive, themuse, arbeitnow, usajobs, adzuna. 직무·직군 이름은 job_function / job_category 에 넣는다.
    """
    return salary_summary_mod.get_salary_summary(
        job_function=job_function,
        location=location,
        source_name=source_name,
    )


@mcp.tool(
    name="get_company_hiring_activity",
    title="Company hiring activity",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
@monitor_tool("get_company_hiring_activity")
def get_company_hiring_activity(
    company_name: str,
    limit: int = 20,
    source_name: str | None = None,
) -> dict[str, Any]:
    """특정 회사의 채용 현황(진행 중인 공고 목록과 직무 분포)을 반환한다.

    source_name 은 수집 사이트 필터다: saramin(사람인), jobkorea(잡코리아), wanted(원티드), jumpit(점핏), rallit(랠릿), work24(고용24), remotive, themuse, arbeitnow, usajobs, adzuna. 직무·직군 이름은 job_function / job_category 에 넣는다.
    """
    return company_activity_mod.get_company_hiring_activity(
        company_name=company_name,
        limit=limit,
        source_name=source_name,
    )


if __name__ == "__main__":
    from src.mcp_server.run import main

    main()
