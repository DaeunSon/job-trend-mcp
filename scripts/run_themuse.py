"""
The Muse 채용공고 수집·파싱 배치 실행 진입점.

이용약관 준수 사항
------------------
- 미등록 기준 시간당 500건, 등록 시 시간당 3,600건
- X-Ratelimit-Remaining 헤더로 잔여 한도 자동 확인 (≤50건 시 자동 대기)
- 상업적 재배포 및 제3자 채용 플랫폼(Google Jobs, LinkedIn Jobs 등) 재게시 금지
- API 키 없이 사용 가능 (완전 공개 API — 미등록 기준)
- 이용약관: https://www.themuse.com/developers/api/v2/terms

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기본 실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 기본 배치 카테고리 전체 수집 + 파싱 (카테고리당 최대 5페이지 = 100건)
  python scripts/run_themuse.py

  # 특정 카테고리만
  python scripts/run_themuse.py --category "Software Engineering" "Data and Analytics"

  # 날짜 라벨 지정 (저장 경로용, 기본값: 오늘)
  python scripts/run_themuse.py --crawl-date 2026-07-30

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
수집량 제한
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 페이지 수 제한: 카테고리당 최대 N × 20건
  python scripts/run_themuse.py --max-pages 1   # 카테고리당 20건 (빠른 테스트)
  python scripts/run_themuse.py --max-pages 10  # 카테고리당 200건

  대략적인 기준:
    --max-pages 1  → 카테고리당  20건  (빠른 테스트)
    --max-pages 5  → 카테고리당 100건  (기본값, 일별 증분 권장)
    --max-pages 10 → 카테고리당 200건  (주간 수집)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파싱 제어
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 수집 건너뛰고 파싱만 (기존 raw 파일 재파싱)
  python scripts/run_themuse.py --parse-only

  # 이미 파싱된 raw 데이터 재파싱
  python scripts/run_themuse.py --parse-only --reparse --crawl-date 2026-07-29

  # 수집만 (파싱 건너뜀)
  python scripts/run_themuse.py --no-parse

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API 키 사용 (등록 시 시간당 3,600건으로 상향)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python scripts/run_themuse.py --api-key YOUR_KEY

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용 가능한 The Muse 카테고리 목록
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  "Software Engineering", "Data and Analytics", "Science and Engineering",
  "Product Management", "Project Management", "Advertising and Marketing",
  "Account Management", "Accounting and Finance", "Human Resources and Recruitment",
  "Sales", "Legal Services", "Management", "Business Operations"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기타
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # DEBUG 로그 출력
  python scripts/run_themuse.py -v --category "Software Engineering" --max-pages 1
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawlers.themuse.client import RESULTS_PER_PAGE, fetch_themuse, run_themuse_batch
from src.crawlers.themuse.parser import run_themuse_parse
from src.crawlers.themuse.search_queries import DEFAULT_BATCH_CATEGORIES

_DEFAULT_PAGE_COUNT = 5


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="The Muse 채용공고 수집·파싱 배치 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--category",
        nargs="*",
        default=None,
        metavar="CATEGORY",
        help=(
            "수집할 The Muse 카테고리 이름 목록 (예: \"Software Engineering\"). "
            "생략 시 DEFAULT_BATCH_CATEGORIES 전체."
        ),
    )
    parser.add_argument(
        "--level",
        default=None,
        metavar="LEVEL",
        help=(
            "레벨 필터 (예: \"Senior Level\", \"Mid Level\", \"Entry Level\"). "
            "--category와 함께 사용 가능."
        ),
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
            f"카테고리별 최대 수집 페이지 수 (페이지당 {RESULTS_PER_PAGE}건). "
            f"예) --max-pages 5 → 카테고리당 최대 100건. "
            f"생략 시 기본값 {_DEFAULT_PAGE_COUNT}페이지."
        ),
    )
    parser.add_argument(
        "--api-key",
        default=None,
        metavar="KEY",
        help=(
            "The Muse API 키 (선택). 미등록 시 생략 가능 — 시간당 500건 제한. "
            "등록 시 시간당 3,600건으로 상향."
        ),
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="수집을 건너뛰고 파싱만 실행",
    )
    parser.add_argument(
        "--no-parse",
        action="store_true",
        help="수집 후 파싱 건너뜀",
    )
    parser.add_argument(
        "--reparse",
        action="store_true",
        help="이미 PARSED된 raw도 포함해 job_postings를 다시 생성 (--parse-only와 함께 사용)",
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

    page_count = args.max_pages if args.max_pages is not None else _DEFAULT_PAGE_COUNT
    save_dir   = args.save_dir
    raw_save_dir = f"{save_dir}/raw_job_postings" if save_dir else None

    if not args.parse_only:
        if args.category:
            # 특정 카테고리만 단건 또는 복수 실행
            logger.info(
                "The Muse 수집 시작 — %d개 카테고리, crawl_date=%s, max_pages=%d",
                len(args.category),
                args.crawl_date or "오늘",
                page_count,
            )
            for cat in args.category:
                fetch_themuse(
                    category=cat,
                    level=args.level,
                    crawl_date=args.crawl_date,
                    save_path=raw_save_dir,
                    page_count=page_count,
                    api_key=args.api_key,
                )
        else:
            # 기본 배치 실행
            categories = DEFAULT_BATCH_CATEGORIES
            logger.info(
                "The Muse 배치 수집 시작 — %d개 카테고리, crawl_date=%s, max_pages=%d",
                len(categories),
                args.crawl_date or "오늘",
                page_count,
            )
            run_themuse_batch(
                categories=categories,
                crawl_date=args.crawl_date,
                save_dir=raw_save_dir,
                page_count=page_count,
                api_key=args.api_key,
            )

    if not args.no_parse:
        logger.info("파싱 단계 시작%s", " (재파싱)" if args.reparse else "")
        run_themuse_parse(
            crawl_date=args.crawl_date,
            base_dir=save_dir,
            reparse=args.reparse,
        )

    logger.info("모든 단계 완료")


if __name__ == "__main__":
    main()
