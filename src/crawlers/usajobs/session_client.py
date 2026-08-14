"""
USAJobs 전용 세션 클라이언트.

GET /Search/Results 로 쿠키(akavpau_usajobs 등)를 시드한 뒤,
동일 requests.Session 으로 POST /Search/ExecuteSearch 를 호출한다.

이 GET-시드-후-POST 패턴은 현재 USAJobs에만 있어 common/ 이나 BaseCrawler 로
올리지 않는다. (재사용처가 없으면 억지 공통화하지 않음)
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests
from requests import Response, Session

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.usajobs.gov"
_RESULTS_PATH = "/Search/Results"
_RESULTS_URL = (
    f"{_BASE_URL}{_RESULTS_PATH}"
    "?hp=public&s=startdate&sd=desc&p=1"
)


class USAJobsSessionClient:
    """동일 Session 으로 쿠키 시드 + JSON POST 를 수행하는 USAJobs 전용 헬퍼."""

    def __init__(
        self,
        session: Session,
        *,
        user_agent: str,
        wait_fn: Callable[[], None],
        retry_count: int,
        timeout: int | tuple[int, int],
        is_blocked_fn: Callable[[str], bool],
        results_url: str = _RESULTS_URL,
        base_url: str = _BASE_URL,
    ) -> None:
        self._session = session
        self._user_agent = user_agent
        self._wait = wait_fn
        self._retry_count = retry_count
        self._timeout = timeout
        self._is_blocked = is_blocked_fn
        self._results_url = results_url
        self._base_url = base_url
        self._session_seeded = False

    @property
    def session(self) -> Session:
        return self._session

    @property
    def session_seeded(self) -> bool:
        return self._session_seeded

    def seed_session(self, force: bool = False) -> bool:
        """
        GET /Search/Results 로 세션 쿠키를 심는다.

        Returns
        -------
        성공 시 True. 이미 시드됐고 force=False 이면 재요청 없이 True.
        """
        if self._session_seeded and not force:
            logger.debug(
                "[usajobs] 세션 이미 시드됨 (cookies=%s) — 재사용",
                list(self._session.cookies.keys()),
            )
            return True

        logger.info(
            "[usajobs] 세션 쿠키 시드 GET %s (Session id=%s)",
            self._results_url,
            id(self._session),
        )
        headers = {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,*/*;q=0.8"
            ),
            "Referer": f"{self._base_url}/",
        }
        last_exc: Exception | None = None
        resp: Response | None = None

        for attempt in range(1, self._retry_count + 1):
            try:
                self._wait()
                resp = self._session.get(
                    self._results_url,
                    headers=headers,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                break
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                logger.warning(
                    "[usajobs] 세션 시드 HTTP 오류 (시도 %d/%d): %d",
                    attempt, self._retry_count, status,
                )
                if status in (403, 429):
                    time.sleep(2.0 ** attempt * 3)
                last_exc = exc
                resp = None
            except requests.exceptions.RequestException as exc:
                backoff = 2.0 ** attempt
                logger.warning(
                    "[usajobs] 세션 시드 실패 (시도 %d/%d): %s — %.1fs 후 재시도",
                    attempt, self._retry_count, exc, backoff,
                )
                time.sleep(backoff)
                last_exc = exc
                resp = None

        if resp is None:
            logger.error("[usajobs] 세션 시드 실패: %s", last_exc)
            self._session_seeded = False
            return False

        if self._is_blocked(resp.text or ""):
            logger.warning("[usajobs] 세션 시드 중 차단 감지")
            self._session_seeded = False
            return False

        cookie_names = list(self._session.cookies.keys())
        self._session_seeded = True
        logger.info(
            "[usajobs] 세션 시드 완료 — status=%d, cookies=%s, Session id=%s",
            resp.status_code,
            cookie_names,
            id(self._session),
        )
        return True

    def post_json(self, url: str, payload: dict[str, Any]) -> Response:
        """
        동일 self._session 으로 JSON POST.
        rate limit·재시도를 적용한다. 새 Session 생성 금지.
        """
        self._wait()
        last_exc: Exception | None = None
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self._results_url,
            "Origin": self._base_url,
            "User-Agent": self._user_agent,
        }

        for attempt in range(1, self._retry_count + 1):
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                logger.debug(
                    "[usajobs] POST %s → %d (Session id=%s)",
                    url, response.status_code, id(self._session),
                )
                return response
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                logger.warning(
                    "[usajobs] POST HTTP 오류 (시도 %d/%d): %s → %d",
                    attempt, self._retry_count, url, status,
                )
                if status in (403, 429):
                    sleep_time = 2.0 ** attempt * 3
                    logger.info("[usajobs] 차단 계열, %.1fs 대기 후 재시도", sleep_time)
                    time.sleep(sleep_time)
                last_exc = exc
            except requests.exceptions.RequestException as exc:
                backoff = 2.0 ** attempt
                logger.warning(
                    "[usajobs] POST 실패 (시도 %d/%d): %s — %.1fs 후 재시도",
                    attempt, self._retry_count, exc, backoff,
                )
                time.sleep(backoff)
                last_exc = exc

        raise last_exc  # type: ignore[misc]
