"""
job_postings JSON을 서버 시작 시 한 번 로드하고, 조회용 인덱스를 만든다.

로드 전략 판단 (2026-08-10 실측)
--------------------------------
- 파일 516개, 디스크 ~7.4MB
- 재수집 스냅샷 포함 시 ~1,155문서, 같은 id 최신 1건만 남기면 ~659건
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

from src.config.sources import ALL_SOURCES
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
_KNOWN_SOURCE_NAMES = tuple(s.source_name for s in ALL_SOURCES)

# 모델이 사이트 이름을 한글 · 띄어쓰기 변형으로 넣는 경우 (2026-09-02 실사용 로그: "사람인")
_SOURCE_ALIASES: dict[str, str] = {
    "사람인": "saramin",
    "잡코리아": "jobkorea",
    "원티드": "wanted",
    "점핏": "jumpit",
    "랠릿": "rallit",
    "고용24": "work24",
    "워크넷": "work24",
    "리모티브": "remotive",
    "더뮤즈": "themuse",
    "뮤즈": "themuse",
    "아르바이트나우": "arbeitnow",
    "애드주나": "adzuna",
}


def _source_key(text: str) -> str:
    """'The Muse', 'USA Jobs', 'work-24' 같은 표기 차이를 없앤 비교용 키."""
    return re.sub(r"[\s._\-]+", "", text).lower()


def _recrawl_sort_key(doc: dict[str, Any]) -> str:
    return str(
        doc.get("created_at")
        or doc.get("last_seen_at")
        or doc.get("posted_at")
        or ""
    )


def _posting_identity(doc: dict[str, Any]) -> tuple[Any, ...] | None:
    """같은 공고의 재수집 스냅샷을 묶는 키. id 우선, 없으면 (source_name, source_job_id)."""
    pid = doc.get("id")
    if pid:
        return ("id", pid)
    source_name = (doc.get("source_name") or "").strip()
    source_job_id = str(doc.get("source_job_id") or "").strip()
    if source_name and source_job_id:
        return ("sid", source_name, source_job_id)
    return None


def collapse_recrawl_snapshots(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    같은 공고가 crawl_date 다른 파일로 여러 번 저장된 경우 최신 1건만 남긴다.

    json_writer.load_all_documents_in_collection 은 id 중복을 제거하지 않는다.
    MCP는 raw_job_postings 가 아니라 job_postings 만 읽지만, 재수집 스냅샷은
    그 컬렉션에도 남을 수 있다.
    """
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []
    for doc in docs:
        key = _posting_identity(doc)
        if key is None:
            passthrough.append(doc)
            continue
        existing = by_key.get(key)
        if existing is None or _recrawl_sort_key(doc) >= _recrawl_sort_key(existing):
            by_key[key] = doc
    return passthrough + list(by_key.values())


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
        collapsed = collapse_recrawl_snapshots(docs)
        if len(collapsed) < len(docs):
            logger.info(
                "job_postings 재수집 스냅샷 제거: %d → %d (raw_job_postings 미사용)",
                len(docs),
                len(collapsed),
            )
        self.postings = collapsed
        self.by_function = defaultdict(list)
        self.by_category = defaultdict(list)

        for doc in self.postings:
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

    @property
    def known_sources(self) -> list[str]:
        return list(_KNOWN_SOURCE_NAMES)

    def resolve_source_name(
        self, name: str | None
    ) -> tuple[str | None, str | None]:
        """
        Returns
        -------
        (canonical_source_name, error_message)
        """
        if name is None or not str(name).strip():
            return None, None
        raw = str(name).strip()
        key = _source_key(raw)
        by_key = {_source_key(s): s for s in self.known_sources}
        by_key.update({_source_key(k): v for k, v in _SOURCE_ALIASES.items()})
        hit = by_key.get(key)
        if hit:
            return hit, None
        available = ", ".join(self.known_sources)
        # 실사용 로그에서 모델이 source_name 에 직무 · 직군명을 넣는 경우가 반복됐다
        # (예: "디자이너", "AI 개발자", "Healthcare"). 어느 파라미터로 옮겨야 하는지 알려 준다.
        if raw.lower() in {c.lower() for c in self.known_categories}:
            hint = f" {raw!r} looks like a job category — use job_category instead."
        elif self.resolve_job_function(raw)[0]:
            hint = f" {raw!r} looks like a job function — use job_function instead."
        else:
            hint = ""
        return None, (
            f"Unknown source_name {raw!r}. source_name is the job board the posting "
            f"was collected from, not a role. Available: {available}.{hint}"
        )

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
