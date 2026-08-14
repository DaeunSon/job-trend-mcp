"""
컬렉션 문서(dict)를 로컬 JSON 파일로 저장하는 공통 유틸.

저장 경로 규칙 (직무 기준):
  data/{collection_name}/{job_function_name}/{source_name}/{crawl_date}_{source_job_id}.json

판단 근거
---------
- 스킬 보강의 목적은 "이 직무, 전체 사이트에서 어떤 스킬 표현이 자주 나오는지"를
  보는 것이므로, 직무를 최상위로 두면
  `data/raw_job_postings/{job_function}/**/*.json` 한 번으로 여러 사이트를
  가로질러 조회할 수 있다.
- `run_*_batch(job_functions: list[str])` 가 이미 직무 단위로 순회하므로,
  그 반복문의 job_function 값을 경로에 그대로 쓰면 된다 (추가 계산 불필요).
- 날짜는 폴더 depth에서 빼고 파일명 접두사로만 남긴다.
  특정 날짜만 볼 때는 파일명 패턴 `{crawl_date}_*.json` 으로 검색하면 충분하다.

job_function_name 에 `/` 가 있으면 (예: "DevOps / Platform Engineer")
폴더명으로 쓸 때 `sanitize_job_function_dirname()` 으로 `.` 으로 치환한다.
저장·조회 모두 이 함수를 써야 경로가 어긋나지 않는다.

레거시 경로 (`{crawl_date}/{filename}.json`) 의 기존 데이터는 마이그레이션하지
않는다. 조회(rglob)는 양쪽 레이아웃을 모두 찾는다.

DB가 확정되면 이 모듈의 함수 시그니처는 유지한 채 내부 구현만 교체한다.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_BASE_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# YYYY-MM-DD_source_job_id.json
_NEW_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)\.json$")


# ---------------------------------------------------------------------------
# Public API — DB 교체 시 이 함수들의 시그니처만 유지하면 된다
# ---------------------------------------------------------------------------

def sanitize_job_function_dirname(job_function_name: str) -> str:
    """
    job_function_name 을 폴더명으로 안전하게 만든다.

    `/` 는 경로 구분자로 해석되므로 `.` 으로 치환한다.
    예: "Data Labeling / Annotation Specialist"
      → "Data Labeling . Annotation Specialist"
    """
    return (job_function_name or "").replace("/", ".")


def build_document_path(
    collection_name: str,
    job_function_name: str,
    source_name: str,
    crawl_date: str,
    source_job_id: str,
    base_dir: str | None = None,
) -> Path:
    """
    새 저장 경로를 조립한다 (디렉토리 생성 없음).

    data/{collection}/{job_function}/{source}/{crawl_date}_{source_job_id}.json
    """
    root = _resolve_collection_dir(collection_name, base_dir)
    jf_dir = sanitize_job_function_dirname(job_function_name)
    safe_source = _sanitize_filename(source_name)
    safe_job_id = _sanitize_filename(str(source_job_id))
    filename = f"{crawl_date}_{safe_job_id}.json"
    return root / jf_dir / safe_source / filename


def save_document(
    document: dict[str, Any],
    collection_name: str,
    filename: str = "",
    crawl_date: str = "",
    base_dir: str | None = None,
    job_function_name: str | None = None,
) -> Path:
    """
    단일 문서를 JSON 파일로 저장한다.

    Parameters
    ----------
    document:           저장할 딕셔너리 (컬렉션 문서 하나)
    collection_name:    'raw_job_postings' | 'job_postings' 등
    filename:           레거시 호환용. job_function_name 이 없을 때 폴백
    crawl_date:         날짜 라벨 (예: '2026-07-24'). 비어 있으면 문서에서 추론
    base_dir:           기본값 = <project_root>/data
    job_function_name:  경로 최상위 직무명. None이면 문서 필드 → filename 순 폴백

    Returns
    -------
    저장된 파일의 Path 객체
    """
    return save_documents(
        documents=[document],
        collection_name=collection_name,
        filename=filename,
        crawl_date=crawl_date,
        base_dir=base_dir,
        job_function_name=job_function_name,
    )


def save_documents(
    documents: list[dict[str, Any]],
    collection_name: str,
    filename: str = "",
    crawl_date: str = "",
    base_dir: str | None = None,
    upsert: bool = False,
    upsert_keys: tuple[str, ...] = ("id",),
    job_function_name: str | None = None,
) -> Path:
    """
    문서마다 개별 JSON 파일로 저장한다.

    경로: {collection}/{job_function}/{source_name}/{crawl_date}_{source_job_id}.json

    job_function 결정 순서:
      1) job_function_name 인자
      2) 문서의 job_function_name 필드
      3) filename 인자 (레거시 호출 호환 폴백)

    upsert=True 이면 upsert_keys 로 매칭되는 기존 파일을 새 문서로 교체한다.
    """
    if not documents:
        root = _resolve_collection_dir(collection_name, base_dir)
        return root

    last_path: Path | None = None
    n_saved = 0

    for doc in documents:
        jf = _resolve_job_function_name(doc, job_function_name, filename)
        # 명시적으로 전달된 직무명은 문서에도 남겨 저장·조회 경로가 일치하도록 한다
        if job_function_name and str(job_function_name).strip() and not doc.get("job_function_name"):
            doc = {**doc, "job_function_name": str(job_function_name).strip()}
        source_name = str(doc.get("source_name") or "unknown")
        source_job_id = str(doc.get("source_job_id") or doc.get("id") or "unknown")
        date_label = crawl_date or _infer_crawl_date(doc)

        dest = build_document_path(
            collection_name=collection_name,
            job_function_name=jf,
            source_name=source_name,
            crawl_date=date_label,
            source_job_id=source_job_id,
            base_dir=base_dir,
        )

        if dest.exists():
            try:
                existing_list = _read_json_list(dest)
            except Exception as exc:
                logger.warning("기존 파일 읽기 실패, 덮어씁니다 (%s): %s", dest, exc)
                existing_list = []

            if upsert:
                incoming_key = _doc_key(doc, upsert_keys)
                replaced = False
                merged: list[dict[str, Any]] = []
                for existing in existing_list:
                    if _doc_key(existing, upsert_keys) == incoming_key:
                        merged.append(doc)
                        replaced = True
                    else:
                        merged.append(existing)
                if not replaced:
                    merged.append(doc)
                to_write: Any = merged[0] if len(merged) == 1 else merged
            else:
                # 동일 경로에 이미 있으면 스킵 (크롤러의 saved_ids 와 이중 방어)
                last_path = dest
                continue
        else:
            to_write = doc

        _write_json(dest, to_write)
        n_saved += 1
        last_path = dest

    logger.info(
        "저장 완료 — 컬렉션: %s, 처리: %d건 → %s",
        collection_name, n_saved, last_path,
    )
    return last_path or _resolve_collection_dir(collection_name, base_dir)


def load_documents(
    collection_name: str,
    filename: str,
    crawl_date: str,
    base_dir: str | None = None,
    job_function_name: str | None = None,
    source_name: str | None = None,
    source_job_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    저장된 JSON 파일을 읽어 문서 목록을 반환한다.
    파일이 없으면 빈 리스트를 반환한다.

    새 경로: job_function_name + source_name + source_job_id 가 있으면 그쪽을 우선한다.
    레거시 경로: {collection}/{crawl_date}/{filename}.json 도 지원한다.
    """
    if job_function_name and source_name and source_job_id:
        dest = build_document_path(
            collection_name=collection_name,
            job_function_name=job_function_name,
            source_name=source_name,
            crawl_date=crawl_date,
            source_job_id=source_job_id,
            base_dir=base_dir,
        )
        if dest.exists():
            return _read_json_list(dest)

    # 레거시: data/{collection}/{crawl_date}/{filename}.json
    legacy = _resolve_legacy_path(collection_name, crawl_date, filename, base_dir)
    if legacy.exists():
        return _read_json_list(legacy)

    # 새 레이아웃에서 crawl_date + filename(stem) 패턴으로 탐색
    # filename 이 "{crawl_date}_{source_job_id}" 형태일 수 있음
    stem = filename
    match = _NEW_FILENAME_RE.match(f"{stem}.json") if stem else None
    date_prefix = crawl_date or (match.group(1) if match else "")
    job_id_part = match.group(2) if match else stem

    if date_prefix and job_id_part:
        root = _resolve_collection_dir(collection_name, base_dir)
        if root.exists():
            pattern = f"{date_prefix}_{_sanitize_filename(job_id_part)}.json"
            for path in root.rglob(pattern):
                return _read_json_list(path)

    return []


def load_all_documents_in_collection(
    collection_name: str,
    base_dir: str | None = None,
) -> list[dict[str, Any]]:
    """
    컬렉션 디렉토리 아래 모든 JSON 파일의 문서를 합쳐서 반환한다.
    중복 제거(id 기준)는 수행하지 않는다.
    """
    root = _resolve_collection_dir(collection_name, base_dir)
    if not root.exists():
        return []

    all_docs: list[dict[str, Any]] = []
    for json_file in sorted(root.rglob("*.json")):
        try:
            all_docs.extend(_read_json_list(json_file))
        except Exception as exc:
            logger.warning("파일 읽기 실패 (%s): %s", json_file, exc)

    return all_docs


def get_saved_ids(
    collection_name: str,
    base_dir: str | None = None,
) -> set[tuple[str, str]]:
    """
    저장된 모든 문서의 (source_name, source_job_id) 세트를 반환한다.
    크롤러가 중복 수집을 건너뛸 때 사용한다.
    """
    docs = load_all_documents_in_collection(collection_name, base_dir)
    result: set[tuple[str, str]] = set()
    for doc in docs:
        sn = doc.get("source_name")
        sid = doc.get("source_job_id")
        if sn and sid:
            result.add((sn, sid))
    return result


def iter_collection_json_files(
    collection_name: str,
    base_dir: str | None = None,
    *,
    crawl_date: str | None = None,
    name_contains: str | None = None,
) -> Iterator[tuple[Path, str]]:
    """
    컬렉션 아래 JSON 파일을 (path, crawl_date_label) 로 yield 한다.

    새 레이아웃·레거시 레이아웃을 모두 지원한다.
    crawl_date 가 주어지면 해당 날짜 파일만 반환한다.
    name_contains 가 주어지면 파일명에 그 문자열이 포함된 것만 반환한다.
    """
    root = _resolve_collection_dir(collection_name, base_dir)
    if not root.exists():
        return

    for json_file in sorted(root.rglob("*.json")):
        if name_contains and name_contains.lower() not in json_file.name.lower():
            # 레거시 파일명 필터 (indeed, jumpit_ 등). 새 레이아웃은 상위 source 폴더로 판별
            parent_name = json_file.parent.name.lower()
            if name_contains.lower() not in parent_name:
                # 레거시: 파일명에 소스명이 들어 있는 경우도 허용하려면 위에서 이미 걸림
                # 새 경로: .../{job_function}/{source}/{date}_{id}.json → parent = source
                continue

        date_label = _crawl_date_from_path(json_file, root)
        if crawl_date and date_label != crawl_date:
            continue
        yield json_file, date_label


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _doc_key(doc: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(doc.get(key) for key in keys)


def _resolve_job_function_name(
    doc: dict[str, Any],
    job_function_name: str | None,
    filename: str,
) -> str:
    if job_function_name and str(job_function_name).strip():
        return str(job_function_name).strip()
    doc_jf = doc.get("job_function_name")
    if doc_jf and str(doc_jf).strip():
        return str(doc_jf).strip()
    if filename and str(filename).strip():
        return str(filename).strip()
    return "_unknown"


def _infer_crawl_date(doc: dict[str, Any]) -> str:
    for key in ("collected_at", "first_collected_at", "created_at", "posted_at"):
        val = doc.get(key)
        if isinstance(val, str) and len(val) >= 10:
            return val[:10]
    from datetime import date
    return date.today().isoformat()


def _resolve_collection_dir(
    collection_name: str,
    base_dir: str | None,
) -> Path:
    root = Path(base_dir) if base_dir else _BASE_DATA_DIR
    return root / collection_name


def _resolve_legacy_path(
    collection_name: str,
    crawl_date: str,
    filename: str,
    base_dir: str | None,
) -> Path:
    dest_dir = _resolve_collection_dir(collection_name, base_dir) / crawl_date
    safe_name = _sanitize_filename(filename)
    return dest_dir / f"{safe_name}.json"


def _crawl_date_from_path(json_file: Path, collection_root: Path) -> str:
    """파일 경로에서 crawl_date 라벨을 추출한다 (신·구 레이아웃 공통)."""
    match = _NEW_FILENAME_RE.match(json_file.name)
    if match:
        return match.group(1)

    # 레거시: {collection}/{crawl_date}/{file}.json
    try:
        rel = json_file.relative_to(collection_root)
        if len(rel.parts) >= 2:
            maybe_date = rel.parts[0]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", maybe_date):
                return maybe_date
    except ValueError:
        pass
    return ""


def _sanitize_filename(name: str) -> str:
    """파일명으로 사용할 수 없는 문자를 제거한다."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
    result = []
    for ch in name:
        if ch in keep or ord(ch) > 127:
            result.append(ch)
        else:
            result.append("_")
    return "".join(result)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise ValueError(f"JSON 파일 형식이 list/dict가 아닙니다: {path}")
