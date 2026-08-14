"""고용24 raw → job_postings 파싱 파이프라인."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.crawlers.parse_batch import process_raw_file
from src.crawlers.work24.detail_parser import extract_detail_fields
from src.crawlers.work24.field_parsers import (
    _parse_career,
    _resolve_education_raw,
)
from src.models.schemas import SalaryInfo
from src.normalization.job_taxonomy import extract_work24_taxonomy_raw
from src.normalization.posting_normalizer import RawExtractedFields, build_job_posting
from src.storage.json_writer import _BASE_DATA_DIR, iter_collection_json_files

logger = logging.getLogger(__name__)

_RAW_COLLECTION = "raw_job_postings"
_PARSED_COLLECTION = "job_postings"
_SOURCE_NAME = "work24"

def parse_raw_posting(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    단일 raw_job_postings 문서를 job_postings 구조로 파싱한다.

    Returns
    -------
    job_postings dict, 또는 파싱 실패 시 None
    """
    source_job_id = raw.get("source_job_id", "")
    source_name = raw.get("source_name", "")
    raw_html = raw.get("raw_html", "")
    raw_text_str = raw.get("raw_text", "")

    if not raw_html:
        logger.warning("[work24] raw_html 없음: %s/%s", source_name, source_job_id)
        return None

    # raw_text 는 JSON 메타데이터 또는 플레인 텍스트
    raw_meta: dict[str, Any] = {}
    if raw_text_str:
        try:
            parsed = json.loads(raw_text_str)
            if isinstance(parsed, dict):
                raw_meta = parsed
        except json.JSONDecodeError:
            pass

    card_meta: dict[str, str] = raw_meta.get("card_meta", {})
    search_query: str = raw_meta.get("search_query", "")

    try:
        fields = extract_detail_fields(raw_html, card_meta)
    except Exception as exc:
        logger.error(
            "[work24] extract_detail_fields 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None

    if not fields.get("title"):
        logger.warning(
            "[work24] 제목 추출 실패 (%s/%s) — 파싱 건너뜀",
            source_name, source_job_id,
        )
        return None

    try:
        # --- work_arrangement 처리 ---
        # 재택근무 가능 구조화 필드가 있으면 REMOTE 우선 적용
        work_arrangement_override: str | None = None
        if fields.get("has_remote_work") is True:
            work_arrangement_override = "REMOTE"

        # --- 경력 파싱 ---
        career_min, career_max = _parse_career(fields.get("career_raw", ""))

        # --- 교육 수준 (원문 전체 보존 — "대졸(4년)~석사" 등 범위 포함) ---
        education_level = _resolve_education_raw(
            fields.get("education_raw", ""),
            fields.get("description", ""),
        )

        # --- job_function / job_category ---
        job_function_raw, job_category_raw = extract_work24_taxonomy_raw(
            title=fields["title"],
            description=fields.get("description", ""),
            occupation_raw=fields.get("occupation_raw", ""),
            search_query=search_query,
        )

        extracted = RawExtractedFields(
            title=fields["title"],
            company_raw=fields["company"],
            description=fields["description"],
            location_raw=fields["location_raw"],
            employment_type_raw=fields["employment_type_raw"],
            career_raw_text=fields.get("career_raw", ""),
            career_min_years=career_min,
            career_max_years=career_max,
            work_arrangement_text=fields["description"],
            work_arrangement_override=work_arrangement_override,
            education_level=education_level,
            job_function_raw=job_function_raw,
            job_category_raw=job_category_raw,
            skills=[],  # 고용24 상세 HTML에서 기술스택 구조화 어려움 — description 에 포함됨
            salary=SalaryInfo(
                raw_text=fields.get("salary_raw") or None,
                min_amount=fields.get("salary_min"),
                max_amount=fields.get("salary_max"),
                currency_code=fields.get("salary_currency"),
                pay_period=fields.get("salary_period"),
            ),
            posted_at=fields.get("posted_at") or None,
            expires_at=fields.get("expires_at"),
            company_industry=fields.get("company_type_raw") or None,
        )
        return build_job_posting(extracted, raw)

    except Exception as exc:
        logger.error(
            "[work24] build_job_posting 실패 (%s/%s): %s",
            source_name, source_job_id, exc, exc_info=True,
        )
        return None


def run_work24_parse(
    crawl_date: str | None = None,
    base_dir: str | None = None,
    reparse: bool = False,
) -> None:
    """
    저장된 raw_job_postings 문서를 일괄 파싱한다.

    Parameters
    ----------
    crawl_date : 특정 날짜 폴더만 처리. None 이면 전체.
    base_dir   : data 루트 경로. None 이면 프로젝트 기본값.
    reparse    : True 이면 parse_status='PARSED' 인 것도 재파싱.
    """
    _data_root = Path(base_dir) if base_dir else _BASE_DATA_DIR
    raw_root = _data_root / _RAW_COLLECTION

    if not raw_root.exists():
        logger.warning("[work24] raw_job_postings 디렉토리 없음: %s", raw_root)
        return

    total_parsed = 0
    total_failed = 0

    for json_file, date_label in iter_collection_json_files(
        _RAW_COLLECTION,
        base_dir,
        crawl_date=crawl_date,
        name_contains="work24",
    ):
        n_ok, n_fail = _process_raw_file(
            json_file=json_file,
            date_label=date_label,
            base_dir=base_dir,
            reparse=reparse,
        )
        total_parsed += n_ok
        total_failed += n_fail

    logger.info(
        "[work24] 파싱 배치 완료 — 성공: %d건, 실패: %d건%s",
        total_parsed,
        total_failed,
        " (재파싱)" if reparse else "",
    )


# ---------------------------------------------------------------------------
# 내부: 파일 단위 처리
# ---------------------------------------------------------------------------


def _process_raw_file(
    json_file: Path,
    date_label: str,
    base_dir: str | None,
    reparse: bool = False,
) -> tuple[int, int]:
    return process_raw_file(
        json_file=json_file,
        date_label=date_label,
        base_dir=base_dir,
        parse_fn=parse_raw_posting,
        source_name=_SOURCE_NAME if reparse else None,
        reparse=reparse,
        log_prefix="[work24]",
    )

