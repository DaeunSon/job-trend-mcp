#!/usr/bin/env python3
"""
스킬 매칭률 측정 — 비스킬 태그 필터(skill_noise_filter) 적용 전후.

매칭률 = 표준 스킬(taxonomy 91개)로 해석된 스킬 태그 수 / 추출된 스킬 태그 수 (태그 단위)

- 적용 후: 지금 파서 그대로 raw_job_postings 를 다시 파싱한다.
- 적용 전: is_skill_noise 를 끄고(빈 문자열만 거름) 같은 raw 를 다시 파싱한다.

raw 를 다시 파싱만 하고 저장하지 않는다. 측정 중에는 alias 후보 등록(파일 쓰기)도 막는다.

사용:
  PYTHONPATH=. python scripts/measure_skill_match.py
  PYTHONPATH=. python scripts/measure_skill_match.py --out docs/skill_match_rate.md
"""
from __future__ import annotations

import argparse
import importlib
import logging
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterator

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.normalization import alias_resolver, skill_noise_filter  # noqa: E402
from src.storage.json_writer import load_all_documents_in_collection  # noqa: E402
from src.taxonomy.skills import SKILLS  # noqa: E402

CANONICAL = {s["canonical_name"] for s in SKILLS}

# source_name → raw 한 건을 job_postings dict 로 바꾸는 함수
PARSERS: dict[str, str] = {
    "adzuna": "src.crawlers.adzuna.parser",
    "arbeitnow": "src.crawlers.arbeitnow.parser",
    "jobkorea": "src.crawlers.jobkorea.parser",
    "jumpit": "src.crawlers.jumpit.parser",
    "rallit": "src.crawlers.rallit.parser",
    "remotive": "src.crawlers.remotive.parser",
    "saramin": "src.crawlers.saramin.parser",
    "themuse": "src.crawlers.themuse.parser",
    "wanted": "src.crawlers.wanted.parser",
}


@contextmanager
def measurement_mode(noise_filter: bool) -> Iterator[None]:
    """alias 파일 쓰기를 막고, 필요하면 노이즈 필터를 끈다. 끝나면 원래대로 돌린다."""
    saved = {
        "register": alias_resolver._register_candidate,
        "load": alias_resolver._load_aliases,
        "is_noise": skill_noise_filter.is_skill_noise,
    }
    cached = saved["load"]()
    alias_resolver._register_candidate = lambda *a, **k: None
    alias_resolver._load_aliases = lambda: cached
    if not noise_filter:
        skill_noise_filter.is_skill_noise = lambda text: not (text or "").strip()
    try:
        yield
    finally:
        alias_resolver._register_candidate = saved["register"]
        alias_resolver._load_aliases = saved["load"]
        skill_noise_filter.is_skill_noise = saved["is_noise"]


def measure(raws: list[dict[str, Any]], noise_filter: bool) -> dict[str, Counter]:
    """사이트별 (태그 수, 매칭 수, 공고 수) 집계."""
    parse_fns: dict[str, Callable] = {
        src: importlib.import_module(mod).parse_raw_posting for src, mod in PARSERS.items()
    }
    out: dict[str, Counter] = defaultdict(Counter)
    with measurement_mode(noise_filter):
        for raw in raws:
            src = raw.get("source_name")
            fn = parse_fns.get(src)
            if fn is None:
                continue
            try:
                job = fn(raw)
            except Exception:
                out[src]["parse_error"] += 1
                continue
            if not job:
                continue
            tags = job.get("skills") or []
            out[src]["postings"] += 1
            out[src]["tags"] += len(tags)
            out[src]["matched"] += sum(1 for t in tags if t.get("canonical_name") in CANONICAL)
    return out


def _rate(c: Counter) -> str:
    return f"{100 * c['matched'] / c['tags']:.1f}%" if c["tags"] else "-"


def build_report(before: dict[str, Counter], after: dict[str, Counter], n_raw: int) -> str:
    tot_b, tot_a = sum(before.values(), Counter()), sum(after.values(), Counter())
    lines = [
        "# 스킬 매칭률 — 비스킬 태그 필터 전후\n",
        f"- 측정일 {date.today()} · raw 공고 {n_raw}건을 다시 파싱 (저장 안 함)",
        "- 매칭률 = 표준 스킬 91개로 해석된 태그 / 추출된 태그 (태그 단위)",
        "- 필터 전: `is_skill_noise` 를 끄고 같은 raw 를 파싱. 필터 후: 지금 파서 그대로",
        "- 사람인 · 원티드 · 점핏 · USAJobs · 고용24 등 필터를 쓰지 않는 사이트는 전후가 같다",
        "",
        "| 사이트 | 태그 수 (전 → 후) | 매칭률 (전 → 후) |",
        "|---|---|---|",
        f"| **전체** | {tot_b['tags']} → {tot_a['tags']} | **{_rate(tot_b)} → {_rate(tot_a)}** |",
    ]
    for src in sorted(after, key=lambda s: -after[s]["tags"]):
        b, a = before.get(src, Counter()), after[src]
        lines.append(f"| {src} | {b['tags']} → {a['tags']} | {_rate(b)} → {_rate(a)} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--data-dir", type=Path, help="raw_job_postings 가 있는 data 폴더 (기본: data/)")
    args = ap.parse_args()
    logging.disable(logging.WARNING)

    raws = load_all_documents_in_collection(
        "raw_job_postings", base_dir=str(args.data_dir) if args.data_dir else None
    )
    before = measure(raws, noise_filter=False)
    after = measure(raws, noise_filter=True)
    md = build_report(before, after, len(raws))
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"저장: {args.out}")
    print(md)


if __name__ == "__main__":
    main()
