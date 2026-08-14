"""
Arbeitnow 채용공고 수집·파싱 배치 실행 진입점.

이용약관 준수 사항
------------------
- 남용 금지 — 분당 수 회 수준으로 보수적으로 호출 (호출 간 20초)
- arbeitnow.com 백링크 의무 (source_name·original_url 필드로 자동 충족)
- Jooble·Neuvoo·Google Jobs·LinkedIn Jobs 등 제3자 채용 사이트 재게시 금지
- API as-is 제공 — 가용성·정확성 보장 없음
- API 키·인증 불필요 (완전 공개 API)
- 참고: https://www.arbeitnow.com/blog/job-board-api

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기본 실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 전체 페이지 순회 수집 + 파싱 (links.next 가 없을 때까지)
  python scripts/run_arbeitnow.py

  # 날짜 라벨 지정 (저장 경로용, 기본값: 오늘)
  python scripts/run_arbeitnow.py --crawl-date 2026-07-30

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
수집량 제한
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 최대 N페이지만 수집 (페이지당 약 100건)
  python scripts/run_arbeitnow.py --max-pages 1   # 빠른 테스트 (~100건)
  python scripts/run_arbeitnow.py --max-pages 5

  # 특정 페이지만 단건 수집
  python scripts/run_arbeitnow.py --page 1 --max-pages 1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
파싱 제어
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 수집 건너뛰고 파싱만
  python scripts/run_arbeitnow.py --parse-only

  # 이미 파싱된 raw 데이터 재파싱
  python scripts/run_arbeitnow.py --parse-only --reparse --crawl-date 2026-07-30

  # 수집만 (파싱 건너뜀)
  python scripts/run_arbeitnow.py --no-parse

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기타
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python scripts/run_arbeitnow.py -v --max-pages 1
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawlers.arbeitnow.client import (
    RESULTS_PER_PAGE,
    fetch_arbeitnow,
    run_arbeitnow_batch,
)
from src.crawlers.arbeitnow.parser import run_arbeitnow_parse


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Arbeitnow 채용공고 수집·파싱 배치 실행",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--page",
        type=int,
        default=None,
        metavar="N",
        help="단건 페이지 수집 (지정 시 배치 대신 해당 페이지만 수집)",
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
            f"최대 수집 페이지 수 (페이지당 약 {RESULTS_PER_PAGE}건). "
            "생략 시 links.next 가 없을 때까지 순회."
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

    save_dir = args.save_dir

    if not args.parse_only:
        if args.page is not None:
            logger.info(
                "Arbeitnow 단건 수집 — page=%d, crawl_date=%s",
                args.page,
                args.crawl_date or "오늘",
            )
            fetch_arbeitnow(
                page=args.page,
                crawl_date=args.crawl_date,
                save_path=save_dir,
            )
        else:
            logger.info(
                "Arbeitnow 배치 수집 시작 — crawl_date=%s, max_pages=%s",
                args.crawl_date or "오늘",
                args.max_pages,
            )
            run_arbeitnow_batch(
                crawl_date=args.crawl_date,
                save_dir=save_dir,
                max_pages=args.max_pages,
            )

    if not args.no_parse:
        logger.info("파싱 단계 시작%s", " (재파싱)" if args.reparse else "")
        run_arbeitnow_parse(
            crawl_date=args.crawl_date,
            base_dir=save_dir,
            reparse=args.reparse,
        )

    logger.info("모든 단계 완료")


if __name__ == "__main__":
    main()
