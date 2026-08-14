"""
Adzuna raw_job_postings → job_postings 파싱.

raw_text 에 저장된 개별 공고 JSON(HTML 크롤 추출물)을 파싱한다.
필드: title / company / location / description / salary_* / contract_* / employment_types
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.crawlers.parse_batch import process_raw_file
from src.models.schemas import SalaryInfo
from src.normalization.job_taxonomy import extract_title_function_raw
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.storage.json_writer import _BASE_DATA_DIR, iter_collection_json_files
from src.taxonomy.skills import find_skills_in_text

logger = logging.getLogger(__name__)

_RAW_COLLECTION = "raw_job_postings"
_SOURCE_NAME = "adzuna"

_COUNTRY_MAP = {
    "uk": "영국",
    "gb": "영국",
    "united kingdom": "영국",
    "england": "영국",
    "scotland": "영국",
    "wales": "영국",
    "us": "미국",
    "usa": "미국",
    "united states": "미국",
    "au": "호주",
    "australia": "호주",
    "ca": "캐나다",
    "canada": "캐나다",
    "de": "독일",
    "germany": "독일",
}


def parse_raw_posting(raw: dict[str, Any]) -> dict[str, Any] | None:
    source_job_id = raw.get("source_job_id", "")
    source_name = raw.get("source_name", "")
    raw_text = raw.get("raw_text", "")

    if not raw_text:
        logger.warning("[adzuna] raw_text 없음: %s/%s", source_name, source_job_id)
        return None

    try:
        job = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("[adzuna] JSON 파싱 실패 (%s/%s): %s", source_name, source_job_id, exc)
        return None

    if not isinstance(job, dict):
        return None

    try:
        title = (job.get("title") or "").strip()
        if not title:
            return None

        company = ((job.get("company") or {}).get("display_name") or "").strip()
        location = ((job.get("location") or {}).get("display_name") or "").strip()
        description = (job.get("description") or "").strip()
        category_label = ((job.get("category") or {}).get("label") or "").strip()
        if category_label.upper() == "IT":
            category_label = "IT Jobs"

        contract_type = (job.get("contract_type") or "").strip()
        contract_time = (job.get("contract_time") or "").strip()
        employment_types = job.get("employment_types") or []
        if not isinstance(employment_types, list):
            employment_types = []

        employment_raw = _build_employment_raw(
            contract_type, contract_time, employment_types, description,
        )

        function_raw = extract_title_function_raw(title, description)
        skills = find_skills_in_text(f"{title}\n{description}")
        salary = _extract_salary(job, description)
        posted_at = _extract_posted_at(job)

        city, region, country = _parse_location(job, location, description, raw)

        work_text = f"{location}\n{description}"
        work_override = _detect_hybrid_override(work_text)

        extracted = RawExtractedFields(
            title=title,
            company_raw=company,
            description=description,
            location_raw=location,
            employment_type_raw=employment_raw,
            job_category_raw=category_label,
            job_function_raw=function_raw,
            skills=skills,
            salary=salary,
            posted_at=posted_at,
            work_arrangement_text=work_text,
            work_arrangement_override=work_override,
            use_korean_location_parser=False,
            location_country=country,
            location_city=city,
            location_region=region,
        )
        return build_job_posting(extracted, raw)
    except Exception as exc:
        logger.error(
            "[adzuna] 파싱 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_adzuna_parse(
    crawl_date: str | None = None,
    base_dir: str | None = None,
    reparse: bool = False,
) -> None:
    _data_root = Path(base_dir) if base_dir else _BASE_DATA_DIR
    raw_root = _data_root / _RAW_COLLECTION
    if not raw_root.exists():
        logger.warning("[adzuna] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="adzuna",
    ):
        parsed, failed = process_raw_file(
            json_file=json_file,
            date_label=date_label,
            base_dir=str(_data_root) if base_dir else None,
            parse_fn=parse_raw_posting,
            source_name=_SOURCE_NAME if reparse else None,
            reparse=reparse,
            log_prefix="[adzuna]",
        )
        total_parsed += parsed
        total_failed += failed

    logger.info(
        "[adzuna] 파싱 배치 완료 — 성공: %d건, 실패: %d건",
        total_parsed, total_failed,
    )


def _build_employment_raw(
    contract_type: str,
    contract_time: str,
    employment_types: list[str],
    description: str,
) -> str:
    parts: list[str] = []
    parts.extend(str(x) for x in employment_types if x)
    if contract_type:
        parts.append(contract_type)
    if contract_time:
        parts.append(contract_time)
    # 본문: "Duration:6 Months Contract"
    if re.search(r"\bcontract\b", description, re.I):
        parts.append("contract")
    if re.search(r"\bpermanent\b", description, re.I):
        parts.append("permanent")
    if re.search(r"\bfull[\s_-]?time\b", description, re.I):
        parts.append("full_time")
    # Contract 우선 — CONTRACTOR+FULL_TIME 동시일 때 Contract 가 먼저 오도록
    joined = " ".join(parts)
    if re.search(r"contract", joined, re.I):
        return "CONTRACTOR " + joined
    return joined


def _detect_hybrid_override(text: str) -> str | None:
    low = (text or "").lower()
    if re.search(r"\bhybrid\b", low):
        return "HYBRID"
    if re.search(r"\bremote\b", low) and re.search(r"\b(office|onsite|on-site)\b", low):
        return "HYBRID"
    if re.search(r"\b(fully\s+)?remote\b|\bwfh\b|work from home", low):
        return "REMOTE"
    return None


def _extract_salary(job: dict[str, Any], description: str = "") -> SalaryInfo:
    smin = job.get("salary_min")
    smax = job.get("salary_max")
    raw_text = (job.get("salary_raw") or "").strip() or None
    currency = (job.get("salary_currency") or None)
    period = (job.get("salary_period") or None)

    # salary_raw 보강 파싱
    if raw_text:
        parsed = _parse_salary_raw(raw_text)
        if smin is None:
            smin = parsed.get("min")
        if smax is None:
            smax = parsed.get("max")
        currency = currency or parsed.get("currency")
        period = period or parsed.get("period")

    # 본문에 £300 - £350 / day 형태가 있을 때
    if smin is None and description:
        m = re.search(
            r"[£$€]\s*([\d,]+(?:\.\d+)?)\s*[-–—to]+\s*[£$€]?\s*([\d,]+(?:\.\d+)?)",
            description,
        )
        if m:
            smin = float(m.group(1).replace(",", ""))
            smax = float(m.group(2).replace(",", ""))
            raw_text = raw_text or m.group(0)
            if "£" in m.group(0):
                currency = currency or "GBP"

    if smin is None and smax is None:
        return SalaryInfo()

    # 기본 기간: raw 에 day 없으면 연봉으로 두지 말고 raw 힌트 없으면 None
    if period is None and raw_text:
        low = raw_text.lower()
        if "day" in low:
            period = "DAILY"
        elif "hour" in low:
            period = "HOURLY"
        elif "month" in low:
            period = "MONTHLY"
        elif "year" in low or "annum" in low:
            period = "ANNUAL"

    return SalaryInfo(
        raw_text=raw_text,
        min_amount=str(smin) if smin is not None else None,
        max_amount=str(smax) if smax is not None else None,
        currency_code=currency,
        pay_period=period,
    )


def _parse_salary_raw(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    cleaned = text.replace(",", "")
    m = re.search(
        r"[£$€]?\s*([\d.]+)\s*[-–—to]+\s*[£$€]?\s*([\d.]+)",
        cleaned,
        re.I,
    )
    if m:
        out["min"] = float(m.group(1))
        out["max"] = float(m.group(2))
    else:
        m = re.search(r"[£$€]\s*([\d.]+)", cleaned)
        if m:
            out["min"] = float(m.group(1))

    upper = text.upper()
    if "GBP" in upper or "£" in text:
        out["currency"] = "GBP"
    elif "USD" in upper or "$" in text:
        out["currency"] = "USD"
    elif "EUR" in upper or "€" in text:
        out["currency"] = "EUR"
    elif "AUD" in upper:
        out["currency"] = "AUD"

    low = text.lower()
    if "day" in low:
        out["period"] = "DAILY"
    elif "hour" in low:
        out["period"] = "HOURLY"
    elif "month" in low:
        out["period"] = "MONTHLY"
    elif "year" in low or "annum" in low:
        out["period"] = "ANNUAL"
    return out


def _parse_location(
    job: dict[str, Any],
    location: str,
    description: str,
    raw: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    city = None
    region = None
    country = None

    if location:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        if parts:
            city = parts[0]
            if len(parts) > 1 and parts[1].lower() != parts[0].lower():
                region = parts[1]

    # 본문: Location: London, UK ?(Hybrid ...)
    m = re.search(
        r"Location:\s*([^,\n]+),\s*([A-Za-z][A-Za-z .]+?)(?:\s*[\?(]|$)",
        description,
        re.I,
    )
    if m:
        city = city or m.group(1).strip()
        country_raw = m.group(2).strip()
        country = _normalize_country(country_raw)

    area = (job.get("location") or {}).get("area") or []
    for item in area:
        mapped = _normalize_country(str(item))
        if mapped:
            country = country or mapped
            break

    # URL / source 도메인 힌트
    if not country:
        url = (raw.get("original_url") or job.get("redirect_url") or "").lower()
        if ".co.uk" in url or "/gb/" in url:
            country = "영국"
        elif ".com.au" in url:
            country = "호주"
        elif "adzuna.com/" in url and ".co.uk" not in url:
            country = "미국"

    # area 값이 도시명만 있는 경우 country 로 쓰지 않음 (London 등)
    return city, region, country


def _normalize_country(text: str) -> str | None:
    key = (text or "").strip().lower()
    if not key:
        return None
    if key in _COUNTRY_MAP:
        return _COUNTRY_MAP[key]
    # 이미 한글 국가명
    if text in {"영국", "미국", "호주", "캐나다", "독일", "대한민국"}:
        return text
    return None


def _extract_posted_at(job: dict[str, Any]) -> str | None:
    created = job.get("created")
    if not created:
        return date.today().isoformat()
    try:
        dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        return dt.date().isoformat()
    except Exception:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(created))
        return m.group(1) if m else date.today().isoformat()
