"""
원티드 채용공고 크롤링·파싱 배치 실행 진입점.

※ 원티드 API에는 날짜 필터가 없습니다. job_sort=job.latest_order(최신순) 정렬을
  사용하므로 --max-pages / --max-jobs 로 수집량을 제한하세요.
  앞쪽 페이지일수록 최근 공고입니다 (페이지당 20건).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기본 실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 전체 직무 크롤링 + 파싱 (기본값: 직무당 최대 2,000건)
  python scripts/run_wanted.py

  # 특정 직무만 (한글/영문 모두 가능)
  python scripts/run_wanted.py --function "백엔드 개발자"
  python scripts/run_wanted.py --function "Backend Engineer" "Frontend Engineer"

  # 날짜 라벨 지정 (저장 경로용, 기본값: 오늘)
  python scripts/run_wanted.py --crawl-date 2026-07-27

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
수집량 제한 (날짜 제약 대체)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 페이지 수 제한: 직무당 최근 N × 20건
  python scripts/run_wanted.py --function "백엔드 개발자" --max-pages 5   # 최대 100건
  python scripts/run_wanted.py --max-pages 10                             # 전체 직무, 직무당 200건

  # 건수 제한: 직무당 최대 N건
  python scripts/run_wanted.py --function "백엔드 개발자" --max-jobs 50

  # 두 조건 병행 (먼저 도달한 쪽에서 중단)
  python scripts/run_wanted.py --function "백엔드 개발자" --max-pages 3 --max-jobs 50

  대략적인 기준:
    --max-pages 1  → 직무당  20건  (빠른 테스트)
    --max-pages 5  → 직무당 100건  (일별 증분 수집 권장)
    --max-pages 10 → 직무당 200건  (주간 수집)
    생략(기본)     → 직무당 2,000건 (전체 수집)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파싱 제어
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 크롤링 건너뛰고 파싱만
  python scripts/run_wanted.py --parse-only

  # 이미 파싱된 raw 데이터 재파싱
  python scripts/run_wanted.py --parse-only --reparse --crawl-date 2026-07-28

  # 크롤링만 (파싱 건너뜀)
  python scripts/run_wanted.py --no-parse

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기타
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # DEBUG 로그 출력
  python scripts/run_wanted.py -v --function "백엔드 개발자" --max-pages 1
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawlers.wanted.client import run_wanted_batch, _MAX_PAGES
from src.crawlers.wanted.parser import run_wanted_parse
from src.crawlers.wanted.search_queries import get_all_function_names


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="원티드 채용공고 크롤링·파싱 배치 실행",
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
            "직무별 최대 수집 페이지 수 (페이지당 20건, 최신순). "
            "원티드 API에 날짜 필터가 없으므로 이 값으로 수집량을 제한한다. "
            "예) --max-pages 5 → 직무당 최대 100건. "
            "생략 시 기본값 100페이지(최대 2,000건)."
        ),
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        metavar="N",
        help=(
            "직무별 최대 수집 건수 상한. "
            "--max-pages와 함께 쓰면 먼저 도달한 조건에서 중단. "
            "예) --max-jobs 50 → 직무당 최대 50건."
        ),
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
        help="이미 PARSED된 raw도 포함해 job_postings를 다시 생성 (parse-only와 함께 사용)",
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
    max_jobs  = args.max_jobs

    logger.info(
        "원티드 배치 시작 — 직무: %d개, crawl_date=%s, max_pages=%d%s",
        len(job_functions),
        args.crawl_date or "오늘",
        max_pages,
        f", max_jobs={max_jobs}" if max_jobs else "",
    )

    save_dir = args.save_dir

    if not args.parse_only:
        run_wanted_batch(
            job_functions=job_functions,
            crawl_date=args.crawl_date,
            save_dir=f"{save_dir}/raw_job_postings" if save_dir else "./data/raw_job_postings",
            max_pages=max_pages,
            max_jobs=max_jobs,
        )

    if not args.no_parse:
        logger.info("파싱 단계 시작%s", " (재파싱)" if args.reparse else "")
        run_wanted_parse(
            crawl_date=args.crawl_date,
            base_dir=save_dir,
            reparse=args.reparse,
        )

    logger.info("모든 단계 완료")


if __name__ == "__main__":
    main()
