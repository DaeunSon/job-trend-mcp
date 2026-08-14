"""
사람인 크롤링/파싱 배치 실행 진입점.

실행 예:
  # 검색어 하나 수집
  python scripts/run_saramin.py -q "백엔드 개발자"

  # 검색어 여러 개
  python scripts/run_saramin.py -q "백엔드 개발자" "데이터 엔지니어"

  # 전체 taxonomy 검색어 배치 수집
  python scripts/run_saramin.py

  # 수집만 (파싱 건너뜀)
  python scripts/run_saramin.py --no-parse

  # 파싱만 (수집 건너뜀)
  python scripts/run_saramin.py --parse-only

  # 이미 파싱된 raw 데이터를 수정된 파서로 재파싱
  python scripts/run_saramin.py --parse-only --reparse

  # 특정 날짜 raw 재파싱
  python scripts/run_saramin.py --parse-only --reparse --date 2026-07-29

  # 날짜 지정
  python scripts/run_saramin.py --date 2026-07-27

  # 최대 페이지 지정 (기본 50)
  python scripts/run_saramin.py -q "백엔드 개발자" --max-pages 5

  # DEBUG 로그
  python scripts/run_saramin.py -q "백엔드 개발자" -v
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawlers.saramin.crawler import crawl_saramin, run_saramin_batch
from src.crawlers.saramin.parser import run_saramin_parse
from src.crawlers.saramin.search_queries import get_all_queries


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="사람인 채용공고 크롤링/파싱 배치 실행",
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
        help="데이터 저장 디렉토리 (기본값: 프로젝트 루트/data)",
    )
    p.add_argument(
        "--parse-only",
        action="store_true",
        help="수집 건너뜀, 저장된 raw 데이터 파싱만 실행",
    )
    p.add_argument(
        "--no-parse",
        action="store_true",
        help="수집 후 파싱 단계 건너뜀",
    )
    p.add_argument(
        "--reparse",
        action="store_true",
        help="이미 PARSED된 raw도 포함해 job_postings를 다시 생성 (parse-only와 함께 사용)",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=50,
        metavar="N",
        help="검색어당 최대 순회 페이지 수 (기본값: 50)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG 레벨 로그")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    queries = args.query if args.query else get_all_queries()

    if not args.parse_only:
        logger.info("수집 시작 — 검색어 %d개 | max_pages=%d", len(queries), args.max_pages)
        if len(queries) == 1:
            crawl_saramin(
                query=queries[0],
                crawl_date=args.crawl_date,
                save_path=args.save_dir,
                max_pages=args.max_pages,
            )
        else:
            run_saramin_batch(
                job_functions=queries,
                crawl_date=args.crawl_date,
                save_dir=args.save_dir or "./data/raw_job_postings",
            )

    if not args.no_parse:
        logger.info("파싱 시작%s", " (재파싱)" if args.reparse else "")
        run_saramin_parse(
            crawl_date=args.crawl_date,
            base_dir=args.save_dir,
            reparse=args.reparse,
        )

    logger.info("완료")


if __name__ == "__main__":
    main()
