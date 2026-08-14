"""
curl_cffi(Chrome TLS 지문) 기반 HTML 크롤 공통 클라이언트.

adzuna처럼 Cloudflare류 TLS 핑거프린팅을 우회할 때 사용한다.
impersonate / 기본 헤더 / 세션 수명은 공통화하고,
차단 HTML 시그널·HTTP 상태코드 정책은 사이트별로 주입·자체 판단한다.
"""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterable, Mapping
from typing import Any

from curl_cffi import requests as curl_requests

from src.crawlers.common.http_utils import BROWSER_USER_AGENT, is_blocked

logger = logging.getLogger(__name__)

DEFAULT_IMPERSONATE = "chrome124"
DEFAULT_TIMEOUT = 25.0


def default_browser_headers(
    *,
    accept_language: str = "en-US,en;q=0.9",
    accept: str = (
        "text/html,application/xhtml+xml,application/json,*/*;q=0.8"
    ),
) -> dict[str, str]:
    """사이트별 Accept-Language / Accept 만 바꿔 쓰는 기본 브라우저 헤더."""
    return {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept-Language": accept_language,
        "Accept": accept,
    }


def random_delay(low: float, high: float) -> None:
    """요청 간격용 균등 난수 sleep."""
    time.sleep(random.uniform(low, high))


class CurlCffiClient:
    """
    curl_cffi Session 래퍼.

    Parameters
    ----------
    impersonate : TLS 지문 (기본 chrome124)
    timeout : 기본 요청 timeout(초)
    headers : 세션 기본 헤더
    block_signals : 사이트별 차단 HTML 시그널 (공통 정규식으로 합치지 않음)
    """

    def __init__(
        self,
        *,
        impersonate: str = DEFAULT_IMPERSONATE,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Mapping[str, str] | None = None,
        block_signals: Iterable[str] = (),
    ) -> None:
        self.timeout = timeout
        self.block_signals = tuple(block_signals)
        self.session = curl_requests.Session(impersonate=impersonate)
        if headers:
            self.session.headers.update(dict(headers))

    def get(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Session.get 위임. timeout 미지정 시 self.timeout."""
        return self.session.get(
            url,
            timeout=self.timeout if timeout is None else timeout,
            headers=dict(headers) if headers is not None else None,
            params=params,
            **kwargs,
        )

    def is_blocked(self, text: str) -> bool:
        """생성 시 주입된 block_signals 로 차단 여부 판정."""
        return is_blocked(text, signals=self.block_signals)

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "CurlCffiClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
