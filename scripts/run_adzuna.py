#!/usr/bin/env python3
"""
Adzuna HTML 크롤 수집·파싱 진입점.

공식 API 키 불필요. curl_cffi 로 국가별 검색·상세 페이지를 수집한다.

주의사항
--------
- 요청 간격은 crawler 내부 랜덤 딜레이(약 0.8~2.5초). CLI 조절 옵션 없음.
- www.adzuna.com(US) 는 CAPTCHA — country 는 gb/au 만 지원.
- 연속 대량 실행 시 429 가능. --max-pages 1 / --max-jobs 로 소량 확인 권장.
- --parse-only 는 adzuna_*.json 만 파싱한다 (Indeed 파일과 섞이지 않음).

예시
----
  python scripts/run_adzuna.py --what "backend engineer" --country gb --max-pages 1
  python scripts/run_adzuna.py --what python --country gb --where London --max-pages 1
  python scripts/run_adzuna.py --batch --countries gb au --max-pages 1
  python scripts/run_adzuna.py --parse-only
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.crawlers.adzuna.crawler import crawl_adzuna, run_adzuna_batch
from src.crawlers.adzuna.parser import run_adzuna_parse
from src.crawlers.adzuna.search_queries import DEFAULT_BATCH_FUNCTIONS, DEFAULT_COUNTRIES


def main() -> None:
    parser = argparse.ArgumentParser(description="Adzuna HTML 크롤 수집·파싱")
    parser.add_argument("--what", default=None, help="검색 키워드")
    parser.add_argument("--country", default="gb", help="국가 코드 (gb/au)")
    parser.add_argument("--where", default=None, help="지역 필터 (w=)")
    parser.add_argument("--batch", action="store_true", help="기본 직무×국가 배치")
    parser.add_argument("--countries", nargs="*", default=None)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--max-jobs", type=int, default=None)
    parser.add_argument("--crawl-date", default=None)
    parser.add_argument("--save-dir", default=None)
    parser.add_argument("--parse-only", action="store_true")
    parser.add_argument("--no-parse", action="store_true")
    parser.add_argument("--reparse", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)
    raw_dir = f"{args.save_dir}/raw_job_postings" if args.save_dir else None

    if not args.parse_only:
        if args.batch:
            run_adzuna_batch(
                job_functions=DEFAULT_BATCH_FUNCTIONS,
                countries=args.countries or DEFAULT_COUNTRIES,
                crawl_date=args.crawl_date,
                save_dir=raw_dir,
                max_pages=args.max_pages,
                max_jobs=args.max_jobs,
            )
        else:
            if not args.what:
                parser.error("--what 또는 --batch 가 필요합니다")
            crawl_adzuna(
                what=args.what,
                country=args.country,
                where=args.where,
                crawl_date=args.crawl_date,
                save_path=raw_dir,
                max_pages=args.max_pages,
                max_jobs=args.max_jobs,
            )

    if not args.no_parse:
        run_adzuna_parse(
            crawl_date=args.crawl_date,
            base_dir=args.save_dir,
            reparse=args.reparse,
        )
    logger.info("완료")


if __name__ == "__main__":
    main()
