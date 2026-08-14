"""검색어 목록 배치 실행 공통 루프."""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def run_query_batch(
    *,
    source_name: str,
    job_functions: Sequence[str],
    crawl_fn: Callable[..., Any],
    crawl_date: str | None = None,
    inter_query_delay: tuple[float, float] = (1.0, 2.0),
    count_saved_only: bool = False,
    **crawl_kwargs: Any,
) -> None:
    """
    job_functions를 순회하며 crawl_fn을 반복 호출한다.
    한 검색어가 실패해도 나머지는 계속 진행한다 (부분 실패 허용).

    crawl_fn 시그니처는 최소한 (query, crawl_date=...) 를 받아야 한다.
    추가 키워드는 crawl_kwargs로 그대로 전달한다.

    count_saved_only
        False(기본): 예외만 실패로 집계 (saramin/jobkorea 스타일).
        True: crawl_fn 반환값이 truthy일 때만 성공으로 집계.
              빈 결과("")는 성공·실패 모두 아님 — wanted/jumpit/rallit 기존 의미.
    """
    _crawl_date = crawl_date or date.today().isoformat()
    total = len(job_functions)
    failed = 0
    saved_count = 0
    delay_min, delay_max = inter_query_delay

    logger.info(
        "[%s] 배치 시작 — 검색어 %d개, crawl_date=%s",
        source_name, total, _crawl_date,
    )

    for idx, query in enumerate(job_functions, start=1):
        label = f"[{idx}/{total}] query={query!r}"
        try:
            logger.info("[%s] %s 시작", source_name, label)
            result = crawl_fn(query=query, crawl_date=_crawl_date, **crawl_kwargs)
            if count_saved_only:
                if result:
                    saved_count += 1
                    logger.info("[%s] %s 완료", source_name, label)
                else:
                    logger.info("[%s] %s — 결과 없음 (건너뜀)", source_name, query)
            else:
                logger.info("[%s] %s 완료", source_name, label)
        except Exception as exc:
            failed += 1
            logger.error("[%s] %s 실패: %s", source_name, label, exc, exc_info=True)

        if idx < total:
            extra = random.uniform(delay_min, delay_max)
            logger.debug("[%s] 검색어 간 추가 대기 %.1fs", source_name, extra)
            time.sleep(extra)

    if count_saved_only:
        logger.info(
            "[%s] 배치 완료 — 성공: %d건, 실패: %d건",
            source_name, saved_count, failed,
        )
    else:
        logger.info(
            "[%s] 배치 종료 — 전체 %d개, 실패 %d개",
            source_name, total, failed,
        )
