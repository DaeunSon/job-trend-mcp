"""
Remotive 채용공고 수집·파싱 배치 실행 진입점.

이용약관 준수 사항
------------------
- 분당 2회 초과 금지, 하루 최대 4회 권장
- Jooble·Google Jobs·LinkedIn Jobs 등 제3자 채용 사이트 재게시 금지
- 출처(remotive) 및 원문 URL 표기 의무 (source_name·original_url 필드로 자동 충족)
- API 키·인증 불필요 (완전 공개 API)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기본 실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 기본 배치 카테고리 전체 수집 + 파싱 (약 19개 카테고리, 카테고리 간 35초 간격)
  python scripts/run_remotive.py

  # 특정 카테고리만
  python scripts/run_remotive.py --category software-development devops data

  # 키워드 검색
  python scripts/run_remotive.py --search "python backend"

  # 날짜 라벨 지정 (저장 경로용, 기본값: 오늘)
  python scripts/run_remotive.py --crawl-date 2026-07-27

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
수집 시간 단축 — 카테고리 수를 줄이는 것이 유일한 방법
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Remotive API는 카테고리당 단일 요청으로 전체 결과를 반환합니다.
  수집 시간은 카테고리 수에만 비례하며, --max-pages / --max-jobs는
  저장 건수만 제한할 뿐 호출 시간에는 영향을 주지 않습니다.

    카테고리 19개 (기본) → 약 11분  (35초 × 18 간격)
    카테고리  5개        → 약  3분
    카테고리  1개        → 즉시 완료

  python scripts/run_remotive.py --category software-development
  python scripts/run_remotive.py --category software-development devops data artificial-intelligence

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
저장 건수 상한 (호출 시간과 무관)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 카테고리당 최대 N × 20건 저장 (호출은 카테고리당 1회 동일)
  python scripts/run_remotive.py --max-pages 1   # 카테고리당 20건만 저장
  python scripts/run_remotive.py --max-jobs 50   # 카테고리당 50건만 저장

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파싱 제어
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 수집 건너뛰고 파싱만 (기존 raw 파일 재파싱)
  python scripts/run_remotive.py --parse-only

  # 이미 파싱된 raw 데이터 재파싱
  python scripts/run_remotive.py --parse-only --reparse --crawl-date 2026-07-28

  # 수집만 (파싱 건너뜀)
  python scripts/run_remotive.py --no-parse

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용 가능한 Remotive 카테고리 slug 목록
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  software-development, devops, artificial-intelligence, data, qa,
  design, product, project-management, marketing, finance,
  human-resources, sales, business-development, operations, strategy,
  legal, compliance, research, customer-service, information-technology,
  engineering, writing, communications, account-management, medical,
  education, knowledge-management, supply-chain, travel-hospitality, all-others

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기타
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # DEBUG 로그 출력
  python scripts/run_remotive.py -v --category software-development
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawlers.remotive.client import (
    RESULTS_PER_PAGE,
    fetch_remotive,
    run_remotive_batch,
)
from src.crawlers.remotive.parser import run_remotive_parse
from src.crawlers.remotive.search_queries import (
    DEFAULT_BATCH_CATEGORIES,
    get_all_category_slugs,
)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remotive 채용공고 수집·파싱 배치 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--category",
        nargs="*",
        default=None,
        metavar="SLUG",
        help=(
            "수집할 Remotive 카테고리 slug 목록. "
            "생략 시 DEFAULT_BATCH_CATEGORIES(약 19개) 전체."
        ),
    )
    parser.add_argument(
        "--search",
        default=None,
        metavar="KEYWORD",
        help=(
            "키워드 검색어 (예: 'python backend'). "
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
            f"카테고리별 최대 저장 페이지 수 ({RESULTS_PER_PAGE}건/페이지 기준). "
            f"N × {RESULTS_PER_PAGE}건을 저장 상한으로 환산한다. "
            "※ Remotive API는 단일 요청으로 전체를 반환하므로 "
            "이 옵션으로 네트워크 호출 비용·시간은 줄어들지 않음. "
            "호출 시간을 줄이려면 --category로 카테고리 수를 줄일 것. "
            "--max-jobs와 함께 쓰면 먼저 도달한 쪽에서 중단."
        ),
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        metavar="N",
        help=(
            "카테고리별 최대 저장 건수 상한 (중복 제거 후 신규 기준). "
            "※ Remotive API는 단일 요청으로 전체를 반환하므로 "
            "이 옵션으로 네트워크 호출 비용·시간은 줄어들지 않음. "
            "--max-pages와 함께 쓰면 먼저 도달한 쪽에서 중단."
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

    # --max-pages와 --max-jobs를 합산해 유효 max_jobs를 계산한다.
    # 두 조건이 함께 지정되면 더 작은 값을 사용한다 (먼저 도달한 쪽 우선).
    max_jobs: int | None = None
    if args.max_pages is not None:
        max_jobs = args.max_pages * RESULTS_PER_PAGE
    if args.max_jobs is not None:
        max_jobs = args.max_jobs if max_jobs is None else min(max_jobs, args.max_jobs)

    save_dir = args.save_dir
    raw_save_dir = f"{save_dir}/raw_job_postings" if save_dir else None

    if not args.parse_only:
        if args.search and not args.category:
            # 키워드 검색 단독 실행
            logger.info(
                "Remotive 키워드 검색 시작 — search='%s', crawl_date=%s%s",
                args.search,
                args.crawl_date or "오늘",
                f", max_jobs={max_jobs}" if max_jobs else "",
            )
            fetch_remotive(
                search=args.search,
                crawl_date=args.crawl_date,
                save_path=raw_save_dir,
                max_jobs=max_jobs,
            )

        elif args.search and args.category:
            # 카테고리 + 키워드 조합
            logger.info(
                "Remotive 조합 검색 시작 — category=%s, search='%s', crawl_date=%s%s",
                args.category,
                args.search,
                args.crawl_date or "오늘",
                f", max_jobs={max_jobs}" if max_jobs else "",
            )
            for cat in args.category:
                fetch_remotive(
                    category=cat,
                    search=args.search,
                    crawl_date=args.crawl_date,
                    save_path=raw_save_dir,
                    max_jobs=max_jobs,
                )

        else:
            # 카테고리 배치 실행 (기본)
            categories = args.category if args.category else DEFAULT_BATCH_CATEGORIES
            logger.info(
                "Remotive 배치 수집 시작 — %d개 카테고리, crawl_date=%s%s",
                len(categories),
                args.crawl_date or "오늘",
                f", max_jobs={max_jobs}" if max_jobs else "",
            )
            run_remotive_batch(
                categories=categories,
                crawl_date=args.crawl_date,
                save_dir=raw_save_dir,
                max_jobs=max_jobs,
            )

    if not args.no_parse:
        logger.info("파싱 단계 시작%s", " (재파싱)" if args.reparse else "")
        run_remotive_parse(
            crawl_date=args.crawl_date,
            base_dir=save_dir,
            reparse=args.reparse,
        )

    logger.info("모든 단계 완료")


if __name__ == "__main__":
    main()
