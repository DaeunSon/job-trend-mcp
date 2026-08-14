"""
USAJobs 채용공고 크롤링·파싱 배치 실행 진입점.

수집 방식 (2026-07-31 확인)
---------------------------
- GET /Search/Results 로 세션 쿠키 시드 → 동일 Session 으로
  POST /Search/ExecuteSearch (내부 JSON API, API 키 불필요)
- 각 공고 GET /job/{DocumentID} 상세 HTML 도 함께 수집
  (본문·max 급여·근무형태 보강, raw_html 저장)
- User-Agent: src.config.sources.USAJOBS_USER_AGENT 고정값

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기본 실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python scripts/run_usajobs.py

  python scripts/run_usajobs.py --function "Software Engineer"
  python scripts/run_usajobs.py --function "Software Engineer" "Data Scientist"

  python scripts/run_usajobs.py --crawl-date 2026-07-30

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
수집량 제한
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python scripts/run_usajobs.py --function "Software Engineer" --max-pages 1
  python scripts/run_usajobs.py --function "Software Engineer" --max-jobs 20

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파싱 제어
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python scripts/run_usajobs.py --parse-only
  python scripts/run_usajobs.py --parse-only --reparse --crawl-date 2026-07-30
  python scripts/run_usajobs.py --no-parse

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기타
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python scripts/run_usajobs.py -v --function "Software Engineer" --max-pages 1
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawlers.usajobs.crawler import _MAX_PAGES, crawl_usajobs, run_usajobs_batch
from src.crawlers.usajobs.extractor import run_usajobs_parse
from src.crawlers.usajobs.search_queries import get_all_function_names

RESULTS_PER_PAGE = 50


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="USAJobs 채용공고 크롤링·파싱 배치 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--function",
        nargs="*",
        default=None,
        metavar="FUNCTION",
        help="수집할 taxonomy 직무명 목록. 생략 시 search_queries.py 전체.",
    )
    parser.add_argument(
        "--crawl-date",
        default=None,
        help="저장 경로에 사용할 날짜 라벨 (기본값: 오늘, 형식: YYYY-MM-DD)",
    )
    parser.add_argument(
        "--save-dir",
        default=None,
        help="데이터 저장 기준 디렉토리 (기본값: ./data)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help=(
            f"키워드별 최대 수집 페이지 수 (페이지당 {RESULTS_PER_PAGE}건). "
            f"생략 시 기본값 {_MAX_PAGES}."
        ),
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        metavar="N",
        help="직무별 최대 수집 건수 상한.",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="크롤링을 건너뛰고 파싱만 실행",
    )
    parser.add_argument(
        "--no-parse",
        action="store_true",
        help="크롤링 후 파싱 건너뜀",
    )
    parser.add_argument(
        "--reparse",
        action="store_true",
        help="이미 PARSED된 raw도 포함해 job_postings를 다시 생성",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="DEBUG 레벨 로그 출력",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    job_functions = args.function if args.function else get_all_function_names()
    max_pages = args.max_pages if args.max_pages is not None else _MAX_PAGES
    max_jobs = args.max_jobs
    save_dir = args.save_dir

    logger.info(
        "USAJobs 배치 시작 — 직무: %d개, crawl_date=%s, max_pages=%d%s",
        len(job_functions),
        args.crawl_date or "오늘",
        max_pages,
        f", max_jobs={max_jobs}" if max_jobs else "",
    )

    if not args.parse_only:
        run_usajobs_batch(
            job_functions=job_functions,
            crawl_date=args.crawl_date,
            save_dir=(
                f"{save_dir}/raw_job_postings" if save_dir else "./data/raw_job_postings"
            ),
            max_pages=max_pages,
            max_jobs=max_jobs,
        )

    if not args.no_parse:
        logger.info("파싱 단계 시작%s", " (재파싱)" if args.reparse else "")
        run_usajobs_parse(
            crawl_date=args.crawl_date,
            base_dir=save_dir,
            reparse=args.reparse,
        )

    logger.info("모든 단계 완료")


if __name__ == "__main__":
    main()
