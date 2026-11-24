"""
MCP 서버 데이터 로더·tool 유닛 테스트.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.mcp_server.data_loader import JobPostingStore, reset_store
from src.mcp_server.run import match_allowed_host, resolve_run_config
from src.mcp_server.tools.category_stats import get_posting_count_by_category
from src.mcp_server.tools.company_activity import get_company_hiring_activity
from src.mcp_server.tools.salary_summary import get_salary_summary
from src.mcp_server.tools.search import search_job_postings
from src.mcp_server.tools.skill_trend import get_skill_trend
from src.taxonomy.job_categories import JOB_CATEGORIES


class TestDataLoader:
    def test_indexes_by_function_and_category(self, sample_store: JobPostingStore):
        assert len(sample_store.postings) == 5
        assert len(sample_store.by_function["Backend Engineer"]) == 3
        assert len(sample_store.by_category["Data & Analytics"]) == 1

    def test_resolve_alias_seed(self, sample_store: JobPostingStore):
        name, err = sample_store.resolve_job_function("백엔드")
        assert err is None
        assert name == "Backend Engineer"

    def test_resolve_typo_autocorrect(self, sample_store: JobPostingStore):
        name, err = sample_store.resolve_job_function("Backned Engineer")
        assert err is None
        assert name == "Backend Engineer"

    def test_resolve_token_subset_devops(self, sample_store: JobPostingStore):
        name, err = sample_store.resolve_job_function("DevOps Engineer")
        assert err is None
        assert name == "DevOps / Platform Engineer"

    def test_resolve_unknown_with_suggestions(self, sample_store: JobPostingStore):
        name, err = sample_store.resolve_job_function("not-a-real-role-xyz")
        assert name is None
        assert err is not None
        assert "Unknown job_function" in err

    def test_resolve_case_insensitive(self, sample_store: JobPostingStore):
        name, err = sample_store.resolve_job_function("backend engineer")
        assert err is None
        assert name == "Backend Engineer"


class TestSearch:
    def test_filter_by_function_and_location(self, sample_store: JobPostingStore):
        out = search_job_postings(
            job_function="Backend Engineer",
            location="서울",
            store=sample_store,
        )
        assert out["status"] == "ok"
        assert out["count"] == 1
        assert out["results"][0]["title"] == "Backend Engineer A"
        assert "description" not in out["results"][0]

    def test_active_only_default(self, sample_store: JobPostingStore):
        out = search_job_postings(job_function="Backend Engineer", store=sample_store)
        titles = {r["title"] for r in out["results"]}
        assert "Expired Backend" not in titles
        assert out["count"] == 2

    def test_active_only_false_includes_expired(self, sample_store: JobPostingStore):
        out = search_job_postings(
            job_function="Backend Engineer",
            active_only=False,
            store=sample_store,
        )
        assert out["count"] == 3

    def test_unknown_function_returns_guidance(self, sample_store: JobPostingStore):
        out = search_job_postings(job_function="not-a-real-role-xyz", store=sample_store)
        assert out["status"] == "unknown_param"
        assert out["results"] == []
        assert "available_job_functions" in out

    def test_alias_korean_function_resolves(self, sample_store: JobPostingStore):
        out = search_job_postings(job_function="백엔드 개발자", store=sample_store)
        assert out["status"] == "ok"
        assert out["count"] >= 1

    def test_employment_type_underscore_matches_hyphen(self, sample_store: JobPostingStore):
        # fixture는 FULL_TIME, 실데이터는 Full-time — 정규화로 둘 다 통과해야 함
        out = search_job_postings(
            job_function="Backend Engineer",
            employment_type="full-time",
            store=sample_store,
        )
        assert out["status"] == "ok"
        assert out["count"] >= 1

    def test_valid_but_empty(self, sample_store: JobPostingStore):
        out = search_job_postings(
            job_function="Backend Engineer",
            location="제주",
            store=sample_store,
        )
        assert out["status"] == "empty"
        assert out["results"] == []

    def test_filter_by_source_name(self, sample_store: JobPostingStore):
        out = search_job_postings(
            job_function="Backend Engineer",
            source_name="jumpit",
            store=sample_store,
        )
        assert out["status"] == "ok"
        assert out["total_matched"] == 2
        assert {r["source_name"] for r in out["results"]} == {"jumpit"}

        wanted_only = search_job_postings(
            source_name="wanted",
            store=sample_store,
        )
        assert wanted_only["status"] == "ok"
        assert wanted_only["total_matched"] == 1
        assert wanted_only["results"][0]["title"] == "Data Analyst"
        assert wanted_only["results"][0]["source_name"] == "wanted"

    def test_source_name_case_insensitive(self, sample_store: JobPostingStore):
        out = search_job_postings(source_name="Jumpit", store=sample_store)
        assert out["status"] == "ok"
        assert {r["source_name"] for r in out["results"]} == {"jumpit"}

    def test_unknown_source_name(self, sample_store: JobPostingStore):
        out = search_job_postings(source_name="linkedin", store=sample_store)
        assert out["status"] == "unknown_param"
        assert out["results"] == []
        assert "available_source_names" in out
        assert "jobkorea" in out["available_source_names"]

    @pytest.mark.parametrize(
        "raw, expected",
        [("점핏", "jumpit"), ("원티드", "wanted"), ("사람인", "saramin"), ("The Muse", "themuse"),
         ("work-24", "work24"), (" JUMPIT ", "jumpit")],
    )
    def test_source_name_korean_and_spacing_aliases(
        self, sample_store: JobPostingStore, raw: str, expected: str
    ):
        assert sample_store.resolve_source_name(raw) == (expected, None)

    def test_korean_source_name_filters_like_canonical(self, sample_store: JobPostingStore):
        assert (
            search_job_postings(source_name="점핏", store=sample_store)["total_matched"]
            == search_job_postings(source_name="jumpit", store=sample_store)["total_matched"]
        )

    # 2026-09-02 실사용 로그에서 unknown_param 으로 끝난 호출 5건 (logs/mcp_tool_calls_20260902.jsonl)
    @pytest.mark.parametrize("raw", ["디자이너", "AI 개발자", "data", "Healthcare"])
    def test_role_in_source_name_explains_which_param(self, sample_store: JobPostingStore, raw: str):
        out = get_posting_count_by_category(source_name=raw, store=sample_store)
        assert out["status"] == "unknown_param"
        assert "not a role" in out["message"]

    def test_category_in_source_name_points_to_job_category(self, sample_store: JobPostingStore):
        out = get_posting_count_by_category(source_name="Healthcare", store=sample_store)
        assert "use job_category" in out["message"]

    def test_salary_with_korean_source_name_resolves(self, sample_store: JobPostingStore):
        out = get_salary_summary(job_function="Data Analyst", source_name="사람인", store=sample_store)
        assert out["status"] != "unknown_param"

    def test_source_name_omitted_keeps_all_sources(
        self, sample_store: JobPostingStore
    ):
        out = search_job_postings(store=sample_store)
        sources = {r["source_name"] for r in out["results"]}
        assert sources == {"jumpit", "wanted"}
        assert out["total_matched"] == 4  # ACTIVE only, mixed sources


class TestRecrawlDedup:
    def test_same_id_keeps_newer_snapshot(self, tmp_path: Path):
        reset_store()
        base = {
            "id": "same-job",
            "title": "Backend Engineer A",
            "company": {"name": "Acme", "raw_name": "Acme"},
            "job_function_name": "Backend Engineer",
            "job_category_name": "Engineering & Technology",
            "location": {
                "country_name": "대한민국",
                "city_name": "서울",
                "region_name": "서울",
                "raw_text": "서울",
            },
            "employment_type_name": "FULL_TIME",
            "work_arrangement": "ONSITE",
            "skills": [],
            "salary": {},
            "original_url": "https://www.jobkorea.co.kr/Recruit/GI_Read/1",
            "source_name": "jobkorea",
            "source_job_id": "1",
            "crawl_status": "ACTIVE",
        }
        older = {
            **base,
            "posted_at": "2026-07-01",
            "created_at": "2026-07-29T00:00:00+00:00",
        }
        newer = {
            **base,
            "title": "Backend Engineer A (recrawl)",
            "posted_at": "2026-07-24",
            "created_at": "2026-08-04T00:00:00+00:00",
        }
        dest = tmp_path / "job_postings" / "Backend Engineer" / "jobkorea"
        dest.mkdir(parents=True)
        (dest / "2026-07-29_1.json").write_text(
            json.dumps(older, ensure_ascii=False), encoding="utf-8"
        )
        (dest / "2026-08-04_1.json").write_text(
            json.dumps(newer, ensure_ascii=False), encoding="utf-8"
        )
        # raw 컬렉션에 같은 공고가 있어도 MCP 스토어는 job_postings 만 읽는다
        raw_dest = tmp_path / "raw_job_postings" / "jobkorea"
        raw_dest.mkdir(parents=True)
        (raw_dest / "extra.json").write_text(
            json.dumps({**older, "id": "raw-only"}, ensure_ascii=False),
            encoding="utf-8",
        )

        store = JobPostingStore().load(tmp_path)
        assert len(store.postings) == 1
        assert store.postings[0]["title"] == "Backend Engineer A (recrawl)"

        out = search_job_postings(
            job_function="Backend Engineer",
            location="서울",
            source_name="jobkorea",
            store=store,
        )
        assert out["status"] == "ok"
        assert out["total_matched"] == 1
        assert out["results"][0]["posted_at"] == "2026-07-24"
        assert {r["original_url"] for r in out["results"]} == {
            "https://www.jobkorea.co.kr/Recruit/GI_Read/1"
        }


class TestSkillTrend:
    def test_counts_canonical_skills(self, sample_store: JobPostingStore):
        out = get_skill_trend("Backend Engineer", top_n=5, store=sample_store)
        assert out["status"] == "ok"
        skills = {s["skill"]: s["count"] for s in out["skills"]}
        assert skills["Python"] == 2
        assert skills["Docker"] == 1
        assert "Go" not in skills  # EXPIRED 공고 제외

    def test_source_name_filters_skill_pool(self, sample_store: JobPostingStore):
        out = get_skill_trend(
            "Data Analyst", source_name="wanted", store=sample_store
        )
        assert out["status"] == "ok"
        assert out["posting_count"] == 1
        assert out["skills"][0]["skill"] == "SQL"

        empty = get_skill_trend(
            "Data Analyst", source_name="jumpit", store=sample_store
        )
        assert empty["status"] == "empty"

    def test_unknown_function(self, sample_store: JobPostingStore):
        out = get_skill_trend("not-a-real-role", store=sample_store)
        assert out["status"] == "unknown_param"
        assert out["skills"] == []


class TestCategoryStats:
    def test_includes_zero_categories(self, sample_store: JobPostingStore):
        out = get_posting_count_by_category(store=sample_store)
        assert out["status"] == "ok"
        assert len(out["categories"]) == len(JOB_CATEGORIES)
        by_name = {c["category"]: c["count"] for c in out["categories"]}
        assert by_name["Engineering & Technology"] == 3  # ACTIVE only
        assert by_name["Data & Analytics"] == 1
        assert by_name["Education & Training"] == 0
        assert by_name["Legal & Compliance"] == 0

    def test_source_name_filters_counts(self, sample_store: JobPostingStore):
        out = get_posting_count_by_category(
            source_name="wanted", store=sample_store
        )
        by_name = {c["category"]: c["count"] for c in out["categories"]}
        assert by_name["Data & Analytics"] == 1
        assert by_name["Engineering & Technology"] == 0
        assert out["total_postings"] == 1


class TestSalarySummary:
    def test_with_salary_data(self, sample_store: JobPostingStore):
        out = get_salary_summary(
            job_function="Backend Engineer",
            location="서울",
            store=sample_store,
        )
        assert out["status"] == "ok"
        assert out["matched_postings"] == 1
        assert out["salary_data_count"] == 1
        assert "postings_with_salary_data" not in out
        assert len(out["summaries"]) == 1
        s = out["summaries"][0]
        assert s["currency_code"] == "KRW"
        assert s["pay_period"] == "ANNUAL"
        assert s["group_sample_count"] == 1
        assert "postings_with_salary_data" not in s
        assert s["min"] == 60000000
        assert s["max"] == 80000000
        assert s["avg"] == 70000000
        assert "salary_data_count=" in (out["message"] or "")

    def test_no_salary_data(self, sample_store: JobPostingStore):
        out = get_salary_summary(
            job_function="Backend Engineer",
            location="부산",
            store=sample_store,
        )
        assert out["status"] == "no_salary_data"
        assert out["matched_postings"] == 1
        assert out["salary_data_count"] == 0
        assert out["summaries"] == []

    def test_does_not_mix_currencies(self, sample_store: JobPostingStore):
        out = get_salary_summary(store=sample_store)
        assert out["status"] == "ok"
        currencies = {s["currency_code"] for s in out["summaries"]}
        assert currencies == {"KRW", "USD"}
        # 그룹 sample 합 = 전체 salary_data_count (필드명이 달라 LLM 혼동 방지)
        assert sum(s["group_sample_count"] for s in out["summaries"]) == out[
            "salary_data_count"
        ]


class TestCompanyHiringActivity:
    def test_existing_company(self, sample_store: JobPostingStore):
        out = get_company_hiring_activity("acme", limit=10, store=sample_store)
        assert out["status"] == "ok"
        assert out["company_name"] == "Acme"
        assert out["matched_postings"] == 3
        fns = {x["job_function"]: x["count"] for x in out["job_function_counts"]}
        assert fns["Backend Engineer"] == 2
        assert fns["Frontend Engineer"] == 1
        assert len(out["postings"]) == 3

    def test_unknown_company_suggests(self, sample_store: JobPostingStore):
        out = get_company_hiring_activity("Acm", store=sample_store)
        assert out["status"] == "unknown_company"
        assert out["matched_postings"] == 0
        assert "Acme" in out["suggestions"]
        assert out["postings"] == []

    def test_suggest_rejects_loose_similarity(self):
        """spacexx→Paychex(ratio≈0.71) 오탐 방지: cutoff 0.75."""
        from src.mcp_server.tools.company_activity import _suggest_companies

        index = {
            "spacex": "SpaceX",
            "paychex": "Paychex",
            "카카오뱅크": "카카오뱅크",
            "네이버": "네이버",
        }
        assert _suggest_companies("spacexx", index) == ["SpaceX"]
        assert "Paychex" not in _suggest_companies("spacexx", index)

        # 한국어 오타 회귀: 실제 회사명에 가까운 변형은 잡고, 느슨한 변형은 제외
        assert "카카오뱅크" in _suggest_companies("카카오뱅크으", index)
        assert "네이버" in _suggest_companies("네이버르", index)
        # 한글 1자만 다른 약한 오타(ratio≈0.67)는 cutoff 아래로 제외
        assert _suggest_companies("네이바", index) == []

    def test_spacexx_does_not_suggest_paychex(self, sample_store: JobPostingStore):
        """실데이터 경로: SpaceX·Paychex가 같이 있을 때 spacexx 오탐 없음."""
        docs = list(sample_store.postings) + [
            {
                "id": "sx1",
                "title": "SE",
                "company": {"name": "SpaceX", "raw_name": "SpaceX"},
                "job_function_name": "Backend Engineer",
                "job_category_name": "Engineering & Technology",
                "location": {"city_name": "Hawthorne", "raw_text": "Hawthorne"},
                "employment_type_name": "FULL_TIME",
                "work_arrangement": "ONSITE",
                "skills": [],
                "salary": {},
                "crawl_status": "ACTIVE",
                "posted_at": "2026-08-01",
            },
            {
                "id": "px1",
                "title": "Payroll Eng",
                "company": {"name": "Paychex", "raw_name": "Paychex"},
                "job_function_name": "Backend Engineer",
                "job_category_name": "Engineering & Technology",
                "location": {"city_name": "Rochester", "raw_text": "Rochester"},
                "employment_type_name": "FULL_TIME",
                "work_arrangement": "REMOTE",
                "skills": [],
                "salary": {},
                "crawl_status": "ACTIVE",
                "posted_at": "2026-08-01",
            },
        ]
        # company tool은 store.postings만 사용
        store = JobPostingStore(postings=docs)
        out = get_company_hiring_activity("spacexx", store=store)
        assert out["status"] == "unknown_company"
        assert out["suggestions"] == ["SpaceX"]
        assert "Paychex" not in out["suggestions"]

class TestMatchAllowedHost:
    def test_dns_wildcard_matches_subdomain(self):
        assert match_allowed_host("abc123.ngrok-free.dev", "*.ngrok-free.dev")
        assert match_allowed_host("xyz.ngrok-free.dev", "*.ngrok-free.dev")

    def test_dns_wildcard_rejects_apex_and_other(self):
        assert not match_allowed_host("ngrok-free.dev", "*.ngrok-free.dev")
        assert not match_allowed_host("evil.com", "*.ngrok-free.dev")
        assert not match_allowed_host(
            "ngrok-free.dev.attacker.com", "*.ngrok-free.dev"
        )

    def test_dns_wildcard_with_port(self):
        assert match_allowed_host("abc.ngrok-free.dev:443", "*.ngrok-free.dev:*")
        assert match_allowed_host("abc.ngrok-free.dev", "*.ngrok-free.dev:*")

    def test_exact_and_port_wildcard(self):
        assert match_allowed_host("localhost", "localhost")
        assert match_allowed_host("localhost:8000", "localhost:*")
        assert not match_allowed_host("other:8000", "localhost:*")


class TestRunConfig:
    def test_default_stdio(self):
        cfg = resolve_run_config([])
        assert cfg == {"transport": "stdio"}

    def test_http_defaults_localhost(self):
        cfg = resolve_run_config(["--transport", "streamable-http", "--port", "8765"])
        assert cfg["transport"] == "streamable-http"
        assert cfg["host"] == "127.0.0.1"
        assert cfg["port"] == 8765
        assert cfg["streamable_http_path"] == "/mcp"

    def test_rejects_wildcard_bind(self):
        with pytest.raises(SystemExit):
            resolve_run_config(
                ["--transport", "streamable-http", "--host", "0.0.0.0"]
            )

    def test_allowed_hosts_dns_wildcard_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MCP_ALLOWED_HOSTS", "*.ngrok-free.dev")
        cfg = resolve_run_config(["--transport", "streamable-http"])
        assert cfg["allowed_hosts"] is not None
        assert "*.ngrok-free.dev" in cfg["allowed_hosts"]
        assert "*.ngrok-free.dev:*" in cfg["allowed_hosts"]
        # 바뀐 서브도메인도 매칭되는지 (런타임 로직과 동일 함수)
        assert any(
            match_allowed_host("new-subdomain.ngrok-free.dev", p)
            for p in cfg["allowed_hosts"]
        )
