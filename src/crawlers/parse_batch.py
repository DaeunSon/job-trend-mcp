"""
raw_job_postings → job_postings 배치 파싱 공통 유틸.

각 사이트 parser 의 _process_raw_file / run_*_parse 에서 재사용한다.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from src.storage.json_writer import (
    _read_json_list,
    _resolve_job_function_name,
    _write_json,
    load_documents,
    save_documents,
)

logger = logging.getLogger(__name__)

_PARSED_COLLECTION = "job_postings"


def select_parse_targets(
    raws: list[dict[str, Any]],
    *,
    source_name: str | None = None,
    reparse: bool = False,
) -> list[dict[str, Any]]:
    """파싱 대상 raw 문서 목록을 반환한다."""
    if reparse:
        if source_name:
            return [r for r in raws if r.get("source_name") == source_name]
        return list(raws)

    if source_name:
        return [
            r for r in raws
            if r.get("parse_status") == "PENDING"
            and r.get("source_name") == source_name
        ]
    return [r for r in raws if r.get("parse_status") == "PENDING"]


def preserve_parsed_metadata(
    result: dict[str, Any],
    raw: dict[str, Any],
    existing_by_id: dict[str, dict[str, Any]],
) -> None:
    """재파싱 시 기존 job_posting id·타임스탬프를 유지한다."""
    existing_id = raw.get("parsed_job_posting_id")
    if not existing_id:
        return

    result["id"] = existing_id
    existing = existing_by_id.get(existing_id)
    if not existing:
        return

    for field in ("created_at", "first_collected_at"):
        if existing.get(field):
            result[field] = existing[field]


def process_raw_file(
    json_file: Path,
    date_label: str,
    base_dir: str | None,
    parse_fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    *,
    source_name: str | None = None,
    reparse: bool = False,
    log_prefix: str = "",
) -> tuple[int, int]:
    """
    raw JSON 파일 하나를 파싱하고 결과를 저장한다.

    Returns
    -------
    (성공 건수, 실패 건수)
    """
    prefix = f"{log_prefix} " if log_prefix else ""
    try:
        raws = _read_json_list(json_file)
    except Exception as exc:
        logger.error("%s파일 읽기 실패 (%s): %s", prefix, json_file, exc)
        return 0, 0

    targets = select_parse_targets(raws, source_name=source_name, reparse=reparse)
    if not targets:
        return 0, 0

    logger.info(
        "%s파싱 대상 %d건 (%s)%s",
        prefix,
        len(targets),
        json_file.name,
        " — 재파싱" if reparse else "",
    )

    parsed_docs: list[dict[str, Any]] = []
    n_ok = 0
    n_fail = 0

    for raw in targets:
        result = parse_fn(raw)
        if result is not None:
            if reparse:
                existing_parsed = _load_existing_parsed(result, date_label, base_dir)
                existing_by_id = {
                    doc["id"]: doc for doc in existing_parsed if doc.get("id")
                }
                preserve_parsed_metadata(result, raw, existing_by_id)
            # raw 에 검색 시 직무가 있으면 파싱 결과보다 경로 일관성을 위해 유지 가능
            # (파서가 정규화한 job_function_name 이 최종 경로 기준)
            raw["parse_status"] = "PARSED"
            raw["parsed_job_posting_id"] = result["id"]
            parsed_docs.append(result)
            n_ok += 1
        else:
            raw["parse_status"] = "FAILED"
            n_fail += 1

    try:
        _write_json(json_file, raws[0] if len(raws) == 1 else raws)
    except Exception as exc:
        logger.error("%sraw 파일 업데이트 실패 (%s): %s", prefix, json_file, exc)

    if parsed_docs:
        save_documents(
            documents=parsed_docs,
            collection_name=_PARSED_COLLECTION,
            crawl_date=date_label,
            base_dir=base_dir,
            upsert=reparse,
            upsert_keys=("id",),
        )

    return n_ok, n_fail


def _load_existing_parsed(
    result: dict[str, Any],
    date_label: str,
    base_dir: str | None,
) -> list[dict[str, Any]]:
    """재파싱 시 동일 공고의 기존 job_postings 문서를 로드한다."""
    # save_documents 와 동일하게 빈 job_function 은 _unknown 으로 해석
    jf = _resolve_job_function_name(result, None, "")
    sn = result.get("source_name")
    sid = result.get("source_job_id")
    if not (sn and sid):
        return []
    return load_documents(
        collection_name=_PARSED_COLLECTION,
        filename=f"{date_label}_{sid}",
        crawl_date=date_label,
        base_dir=base_dir,
        job_function_name=jf,
        source_name=str(sn),
        source_job_id=str(sid),
    )
