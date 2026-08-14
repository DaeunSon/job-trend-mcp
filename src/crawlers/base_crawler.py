"""
크롤러 공통 인터페이스.

- 요청 간격 (rate limiting)
- robots.txt 체크 (로깅 목적, 강제 차단은 하지 않음)
- 실패 시 지수 백오프 재시도
- User-Agent 설정
"""
from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any
from urllib import robotparser
from urllib.parse import urlparse

import requests
from requests import Response, Session

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = (10, 30)    # (connect_timeout, read_timeout) 단위: 초
_DEFAULT_RETRY_COUNT = 3
_DEFAULT_BACKOFF_BASE = 2.0    # 지수 백오프 밑(초)


class BaseCrawler(ABC):
    """모든 사이트별 크롤러가 상속하는 기반 클래스."""

    def __init__(
        self,
        source_name: str,
        base_url: str,
        user_agent: str,
        rate_limit_min: float = 2.0,   # 요청 최소 간격(초)
        rate_limit_max: float = 5.0,   # 요청 최대 간격(초)
        retry_count: int = _DEFAULT_RETRY_COUNT,
        timeout: int | tuple[int, int] = _DEFAULT_TIMEOUT,
    ) -> None:
        self.source_name = source_name
        self.base_url = base_url
        self.user_agent = user_agent
        self.rate_limit_min = rate_limit_min
        self.rate_limit_max = rate_limit_max
        self.retry_count = retry_count
        self.timeout = timeout

        self._session = self._build_session()
        self._robots_cache: dict[str, robotparser.RobotFileParser] = {}

    # ------------------------------------------------------------------
    # 공개 유틸 — 서브클래스에서 사용
    # ------------------------------------------------------------------

    def get(self, url: str, params: dict[str, Any] | None = None, **kwargs) -> Response:
        """
        GET 요청 + 재시도 + 요청 간격 적용.
        성공하면 Response 객체를, 모든 재시도 실패 시 마지막 예외를 raise.
        """
        self._wait()
        last_exc: Exception | None = None

        for attempt in range(1, self.retry_count + 1):
            try:
                response = self._session.get(
                    url, params=params, timeout=self.timeout, **kwargs
                )
                response.raise_for_status()
                logger.debug("[%s] GET %s → %d", self.source_name, url, response.status_code)
                return response

            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                logger.warning(
                    "[%s] HTTP 오류 (시도 %d/%d): %s → %d",
                    self.source_name, attempt, self.retry_count, url, status,
                )
                if status in (403, 429):
                    # 차단 계열: 더 길게 대기
                    sleep_time = _DEFAULT_BACKOFF_BASE ** attempt * 3
                    logger.info("차단 감지, %.1fs 대기 후 재시도", sleep_time)
                    time.sleep(sleep_time)
                last_exc = exc

            except requests.exceptions.ReadTimeout as exc:
                backoff = _DEFAULT_BACKOFF_BASE ** attempt * 2  # read timeout은 좀 더 길게
                logger.warning(
                    "[%s] 읽기 타임아웃 (시도 %d/%d): %s, %.1fs 후 재시도",
                    self.source_name, attempt, self.retry_count, url, backoff,
                )
                time.sleep(backoff)
                last_exc = exc

            except requests.exceptions.RequestException as exc:
                backoff = _DEFAULT_BACKOFF_BASE ** attempt
                logger.warning(
                    "[%s] 요청 실패 (시도 %d/%d): %s — %s, %.1fs 후 재시도",
                    self.source_name, attempt, self.retry_count, url, exc, backoff,
                )
                time.sleep(backoff)
                last_exc = exc

        raise last_exc  # type: ignore[misc]

    def check_robots(self, url: str) -> bool:
        """
        robots.txt 기준으로 url 접근 허용 여부를 반환한다.
        네트워크 오류 등으로 확인 불가 시 True(허용)로 처리하고 경고 로그를 남긴다.
        """
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        if robots_url not in self._robots_cache:
            rp = robotparser.RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                self._robots_cache[robots_url] = rp
            except Exception as exc:
                logger.warning("robots.txt 읽기 실패 (%s): %s — 허용으로 처리", robots_url, exc)
                return True

        rp = self._robots_cache[robots_url]
        allowed = rp.can_fetch(self.user_agent, url)
        if not allowed:
            logger.warning("[%s] robots.txt 불허: %s", self.source_name, url)
        return allowed

    # ------------------------------------------------------------------
    # 추상 메서드 — 서브클래스가 반드시 구현
    # ------------------------------------------------------------------

    @abstractmethod
    def crawl(self, *args: Any, **kwargs: Any) -> Any:
        """사이트별 크롤링 진입점."""
        ...

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _build_session(self) -> Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,*/*;q=0.8"
                ),
            }
        )
        return session

    def _wait(self) -> None:
        """요청 간격을 랜덤하게 적용한다."""
        sleep_time = random.uniform(self.rate_limit_min, self.rate_limit_max)
        logger.debug("[%s] %.2fs 대기", self.source_name, sleep_time)
        time.sleep(sleep_time)

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "BaseCrawler":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
