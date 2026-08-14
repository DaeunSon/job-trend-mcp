"""
job_postings JSON을 서버 시작 시 한 번 로드하고, 조회용 인덱스를 만든다.

로드 전략 판단 (2026-08-10 실측)
--------------------------------
- 파일 516개, 문서 ~1,155건, 디스크 ~7.4MB
- load_all_documents_in_collection 기준 약 0.1초
- 규모가 작아 매 요청마다 폴더를 여는 이득이 없고, tool이 교차 집계
  (직군별 통계·스킬 트렌드)를 하므로 **전체 로드 후 조회**가 맞다.
- 데이터가 커지면 job_function 폴더 단위 lazy load + 캐시로 전환하면 된다.
"""
from __future__ import annotations

import difflib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.storage.json_writer import load_all_documents_in_collection
from src.taxonomy.job_categories import JOB_CATEGORIES
from src.taxonomy.job_functions import get_function_names, is_valid_function

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# 오타 자동 보정 하한 (Backned→Backend 0.94, Data Scinetist→Data Scientist 0.93).
# DevOps Engineer→DevOps / Platform 은 0.73대라 토큰 매칭으로 별도 처리.
_CLOSE_MATCH_AUTO_CUTOFF = 0.90
_CLOSE_MATCH_SUGGEST_CUTOFF = 0.60
_STOP_TOKENS = frozenset({"and", "or", "the", "a", "an", "of", "for", "/", "-"})


def _function_tokens(text: str) -> set[str]:
    parts = re.split(r"[^a-z0-9가-힣]+", text.lower())
    return {p for p in parts if p and p not in _STOP_TOKENS}


def _suggest_job_functions(query: str, *, limit: int = 5) -> list[str]:
    """토큰 포함 + difflib 기반 유사 직무 제안 (자동 resolve 아님)."""
    names = get_function_names()
    lower_map = {f.lower(): f for f in names}
    q_tokens = _function_tokens(query)
    scored: dict[str, float] = {}

    if q_tokens:
        for name in names:
            n_tokens = _function_tokens(name)
            if not n_tokens:
                continue
            if q_tokens <= n_tokens:
                # 쿼리 토큰이 모두 포함되면 강하게 가산 (DevOps Engineer → DevOps / Platform)
                scored[name] = max(scored.get(name, 0.0), 0.95)
            overlap = len(q_tokens & n_tokens) / len(q_tokens)
            if overlap >= 0.5:
                scored[name] = max(scored.get(name, 0.0), 0.7 + 0.2 * overlap)

    for key in difflib.get_close_matches(
        query.lower(),
        list(lower_map.keys()),
        n=limit,
        cutoff=_CLOSE_MATCH_SUGGEST_CUTOFF,
    ):
        name = lower_map[key]
        ratio = difflib.SequenceMatcher(None, query.lower(), key).ratio()
        scored[name] = max(scored.get(name, 0.0), ratio)

    ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, _ in ranked[:limit]]


def _resolve_via_alias_seed(raw: str) -> str | None:
    """taxonomy seed만 조회 (파일에 MANUAL 후보를 쓰지 않는 read-only 경로)."""
    from src.normalization.alias_resolver import _lookup_seed

    hit = _lookup_seed("JOB_FUNCTION", raw)
    if hit and is_valid_function(hit):
        return hit
    return None


def _resolve_via_high_confidence_close(raw: str) -> str | None:
    """명백한 오타만 자동 보정 (cutoff 0.90+)."""
    names = get_function_names()
    lower_map = {f.lower(): f for f in names}
    matches = difflib.get_close_matches(
        raw.lower(),
        list(lower_map.keys()),
        n=1,
        cutoff=_CLOSE_MATCH_AUTO_CUTOFF,
    )
    if matches:
        return lower_map[matches[0]]
    return None


def _resolve_via_token_subset(raw: str) -> str | None:
    """쿼리 토큰이 유일하게 포함되는 taxonomy 직무로 해석 (DevOps Engineer 등)."""
    q_tokens = _function_tokens(raw)
    if len(q_tokens) < 2:
        return None
    hits = [
        name
        for name in get_function_names()
        if q_tokens <= _function_tokens(name)
    ]
    if len(hits) == 1:
        return hits[0]
    return None


@dataclass
class JobPostingStore:
    """메모리에 올린 채용공고와 단순 인덱스."""

    postings: list[dict[str, Any]] = field(default_factory=list)
    by_function: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    by_category: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    data_dir: Path = field(default_factory=lambda: _DEFAULT_DATA_DIR)

    def load(self, base_dir: str | Path | None = None) -> "JobPostingStore":
        root = Path(base_dir) if base_dir is not None else self.data_dir
        self.data_dir = root
        docs = load_all_documents_in_collection(
            "job_postings",
            base_dir=str(root),
        )
        self.postings = docs
        self.by_function = defaultdict(list)
        self.by_category = defaultdict(list)

        for doc in docs:
            jf = (doc.get("job_function_name") or "").strip()
            jc = (doc.get("job_category_name") or "").strip()
            if jf:
                self.by_function[jf].append(doc)
            if jc:
                self.by_category[jc].append(doc)

        logger.info(
            "job_postings 로드 완료: %d건 (function=%d, category=%d) from %s",
            len(self.postings),
            len(self.by_function),
            len(self.by_category),
            root / "job_postings",
        )
        return self

    @property
    def known_functions(self) -> list[str]:
        return get_function_names()

    @property
    def known_categories(self) -> list[str]:
        return list(JOB_CATEGORIES)

    def resolve_job_function(self, name: str | None) -> tuple[str | None, str | None]:
        """
        Returns
        -------
        (canonical_name, error_message)
        error_message가 있으면 taxonomy에 없는 값.

        해석 순서 (모니터링 typo/비표준 카테고리 대응):
        1) taxonomy 정확·대소문자 무시
        2) job_taxonomy_seed alias (한글·약칭, read-only)
        3) 토큰 부분일치가 유일하면 채택 (예: DevOps Engineer)
        4) difflib >= 0.90 오타 자동 보정
        5) 실패 시 유사 후보를 메시지에 포함
        """
        if name is None or not str(name).strip():
            return None, None
        raw = str(name).strip()
        if is_valid_function(raw):
            return raw, None
        # 대소문자만 다른 경우
        lower_map = {f.lower(): f for f in get_function_names()}
        hit = lower_map.get(raw.lower())
        if hit:
            return hit, None

        alias_hit = _resolve_via_alias_seed(raw)
        if alias_hit:
            return alias_hit, None

        token_hit = _resolve_via_token_subset(raw)
        if token_hit:
            return token_hit, None

        close_hit = _resolve_via_high_confidence_close(raw)
        if close_hit:
            return close_hit, None

        suggestions = _suggest_job_functions(raw)
        available = ", ".join(get_function_names()[:12])
        hint = (
            f" Did you mean: {', '.join(suggestions)}?"
            if suggestions
            else ""
        )
        return None, (
            f"Unknown job_function {raw!r}.{hint} "
            f"Use a taxonomy value, e.g. {available}, … "
            f"(total {len(get_function_names())} functions)."
        )


_STORE: JobPostingStore | None = None


def get_store(base_dir: str | Path | None = None, *, reload: bool = False) -> JobPostingStore:
    """프로세스 전역 스토어. 테스트에서는 base_dir/reload로 교체 가능."""
    global _STORE
    if _STORE is None or reload or base_dir is not None:
        store = JobPostingStore()
        store.load(base_dir)
        if base_dir is None and not reload:
            _STORE = store
            return _STORE
        if base_dir is None and reload:
            _STORE = store
        return store
    return _STORE


def reset_store() -> None:
    """테스트용 — 전역 캐시 초기화."""
    global _STORE
    _STORE = None
