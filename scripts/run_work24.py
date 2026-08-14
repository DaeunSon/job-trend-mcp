"""
고용24 크롤링/파싱 배치 실행 진입점.

실행 예:
  # 검색어 하나 수집
  python scripts/run_work24.py -q "백엔드 개발자"

  # 검색어 여러 개
  python scripts/run_work24.py -q "백엔드 개발자" "데이터 엔지니어"

  # 전체 taxonomy 검색어 배치 수집
  python scripts/run_work24.py

  # 수집만 (파싱 건너뜀)
  python scripts/run_work24.py --no-parse

  # 파싱만 (수집 건너뜀)
  python scripts/run_work24.py --parse-only

  # 이미 파싱된 raw 데이터를 수정된 파서로 재파싱
  python scripts/run_work24.py --parse-only --reparse

  # 특정 날짜 raw 재파싱
  python scripts/run_work24.py --parse-only --reparse --date 2026-07-29

  # 최대 페이지 지정 (기본 50)
  python scripts/run_work24.py -q "백엔드 개발자" --max-pages 5

  # DEBUG 로그
  python scripts/run_work24.py -q "백엔드 개발자" -v
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawlers.work24.crawler import crawl_work24, run_work24_batch
from src.crawlers.work24.extractor import run_work24_parse
from src.crawlers.work24.search_queries import get_all_queries


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="고용24 채용공고 크롤링/파싱 배치 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--query", "-q",
        nargs="*",
        default=None,
        help="검색어 목록 (생략 시 search_queries.py 전체 사용)",
    )
    p.add_argument(
        "--date", "-d",
        default=None,
        dest="crawl_date",
        help="저장 경로 날짜 라벨 (기본값: 오늘, 형식: YYYY-MM-DD)",
    )
    p.add_argument(
        "--save-dir",
        default=None,
        help="raw_job_postings 저장 루트 경로 (기본값: ./data)",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="검색어당 최대 페이지 수 (기본값: 50)",
    )
    p.add_argument(
        "--no-parse",
        action="store_true",
        help="수집만 수행하고 파싱은 건너뜀",
    )
    p.add_argument(
        "--parse-only",
        action="store_true",
        help="파싱만 수행하고 수집은 건너뜀",
    )
    p.add_argument(
        "--reparse",
        action="store_true",
        help="parse_status=PARSED 인 것도 재파싱",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="DEBUG 로그 출력",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)

    queries: list[str] | None = args.query

    # ── 수집 단계 ────────────────────────────────────────────────────────────
    if not args.parse_only:
        if queries:
            # 지정된 검색어 하나씩 수집
            for q in queries:
                try:
                    crawl_work24(
                        query=q,
                        crawl_date=args.crawl_date,
                        save_path=args.save_dir,
                        max_pages=args.max_pages,
                    )
                except Exception as exc:
                    logging.error("수집 실패 (query=%r): %s", q, exc, exc_info=True)
        else:
            # 전체 taxonomy 배치 수집
            run_work24_batch(
                job_functions=None,
                crawl_date=args.crawl_date,
                save_dir=args.save_dir,
                max_pages=args.max_pages,
            )

    # ── 파싱 단계 ────────────────────────────────────────────────────────────
    if not args.no_parse:
        run_work24_parse(
            crawl_date=args.crawl_date,
            base_dir=args.save_dir,
            reparse=args.reparse,
        )


if __name__ == "__main__":
    main()
