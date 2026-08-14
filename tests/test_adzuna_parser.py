"""adzuna/parser.py 유닛 테스트."""
from __future__ import annotations

import json

from src.crawlers.adzuna.parser import parse_raw_posting


def _raw(job: dict, **extra) -> dict:
    doc = {
        "id": "raw-1",
        "source_name": "adzuna",
        "source_job_id": str(job.get("id", "1")),
        "original_url": job.get("redirect_url") or "https://www.adzuna.co.uk/jobs/details/1",
        "raw_html": "",
        "raw_text": json.dumps(job, ensure_ascii=False),
        "collected_at": "2026-08-03T00:00:00+00:00",
        "parse_status": "PENDING",
    }
    doc.update(extra)
    return doc


class TestParseRawPosting:
    def test_basic(self):
        job = {
            "id": "129698749",
            "title": "Javascript Developer",
            "description": "JavaScript Developer with React and Node.js experience",
            "redirect_url": "http://adzuna.co.uk/jobs/land/ad/129698749",
            "created": "2026-08-01T18:07:39Z",
            "salary_min": 50000,
            "salary_max": 55000,
            "salary_raw": "£50000 - £55000/annum",
            "salary_currency": "GBP",
            "salary_period": "ANNUAL",
            "company": {"display_name": "Corporate Project Solutions"},
            "location": {"display_name": "Marlow, Buckinghamshire", "area": ["UK", "South East England"]},
            "category": {"label": "IT Jobs", "tag": "it-jobs"},
            "contract_type": "permanent",
            "contract_time": "full_time",
        }
        result = parse_raw_posting(_raw(job))
        assert result is not None
        assert result["title"] == "Javascript Developer"
        assert result["source_name"] == "adzuna"
        assert result["company"]["raw_name"] == "Corporate Project Solutions"
        assert result["job_category_name"] == "Engineering & Technology"
        assert result["salary"]["min_amount"] == "50000"
        assert result["salary"]["currency_code"] == "GBP"
        assert result["salary"]["pay_period"] == "ANNUAL"
        assert result["location"]["country_name"] == "영국"

    def test_missing_title_returns_none(self):
        assert parse_raw_posting(_raw({"id": "1", "title": ""})) is None

    def test_daily_contract_hybrid_python_job(self):
        job = {
            "id": "5720620383",
            "title": "Python Developer",
            "description": (
                "Role: – Sr Python Developer\n"
                "Duration:6 Months Contract\n"
                "Location: London, UK ?(Hybrid 3 days office)\n"
                "Must-Have Skills\n"
                "Strong experience in Core Python development\n"
                "Strong SQL skills\n"
                "Python libraries (Pandas, NumPy)\n"
                "RESTful APIs/services (Flask / FastAPI / Django)\n"
                "Unix / Linux environments\n"
            ),
            "redirect_url": "https://www.adzuna.co.uk/jobs/details/5720620383",
            "company": {"display_name": "N Consulting Ltd"},
            "location": {"display_name": "London, London", "area": ["London", "London"]},
            "category": {"label": "IT Jobs", "tag": ""},
            "salary_min": 300.0,
            "salary_max": 350.0,
            "salary_raw": "300 - 350 GBP Per day",
            "contract_type": "contract",
            "contract_time": "",
            "employment_types": ["CONTRACTOR", "FULL_TIME"],
        }
        result = parse_raw_posting(_raw(job))
        assert result is not None
        assert result["company"]["raw_name"] == "N Consulting Ltd"
        assert result["employment_type_name"] == "Contract"
        assert result["work_arrangement"] == "HYBRID"
        assert result["location"]["city_name"] == "London"
        assert result["location"]["country_name"] == "영국"
        assert result["salary"]["min_amount"] == "300.0"
        assert result["salary"]["max_amount"] == "350.0"
        assert result["salary"]["currency_code"] == "GBP"
        assert result["salary"]["pay_period"] == "DAILY"
        assert result["salary"]["raw_text"] == "300 - 350 GBP Per day"
        skills = {s["canonical_name"] for s in result["skills"]}
        assert "Python" in skills
        assert "SQL" in skills
        assert "FastAPI" in skills or "Django" in skills
        assert result["job_category_name"] == "Engineering & Technology"
        assert result["job_function_name"]  # title 기반 직무 매핑
