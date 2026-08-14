"""
공식 공개 API 계열 클라이언트 공통 베이스.

themuse · remotive · arbeitnow 처럼 인증 없이 JSON 목록 API를 호출하는 패턴을 공유한다.
사이트별 엔드포인트·페이지네이션·rate limit 값은 RateLimitPolicy / 서브클래스에 남긴다.
봇 우회 로직은 없다.
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import requests
from requests import Response

from src.crawlers.common.http_utils import BROWSER_USER_AGENT
from src.models.schemas import RawJobPosting

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitPolicy:
    """사이트별 rate limit / retry 정책. 공통 클래스에 특정 사이트 값을 하드코딩하지 않는다."""

    min_interval_seconds: float
    max_retries: int = 3
    backoff_base: float = 2.0
    # HTTP 상태코드 → backoff 배수 (예: {403: 3, 429: 3})
    status_backoff_multipliers: dict[int, float] = field(default_factory=dict)
    # 응답 헤더 기반 한도 (The Muse)
    header_remaining: str | None = None
    header_reset: str | None = None
    header_threshold: int | None = None
    # 429 시 header_reset 초만큼 대기
    honor_429_reset_header: bool = False


@dataclass
class ApiCallResult:
    """call_api 결과. data 가 None 이면 호출 실패."""

    data: dict[str, Any] | None
    rate_remaining: int | None = None
    rate_reset: int | None = None


def parse_int_header(resp: Any, header_name: str) -> int | None:
    """응답 헤더에서 정수값을 파싱한다. 없거나 실패 시 None."""
    try:
        headers = getattr(resp, "headers", {}) or {}
        val = headers.get(header_name)
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


class ApiClientBase(ABC):
    """
    공개 JSON Jobs API 클라이언트 골격.

    서브클래스는 엔드포인트·job id/url 추출·페이지 응답에서 jobs 목록 위치만 구현한다.
    """

    source_name: str
    base_url: str
    api_path: str
    rate_limit: RateLimitPolicy
    collection_name: str = "raw_job_postings"
    timeout: tuple[float, float] = (10.0, 30.0)
    allow_redirects: bool = True
    user_agent: str = BROWSER_USER_AGENT

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    @property
    def api_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/{self.api_path.lstrip('/')}"

    def request_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def call_api(self, params: dict[str, Any] | None = None) -> ApiCallResult:
        """
        GET JSON 호출. 재시도·지수 백오프·(옵션) 레이트리밋 헤더 파싱.
        모든 재시도 실패 시 data=None.
        """
        policy = self.rate_limit
        tag = self.source_name
        last_exc: Exception | None = None

        for attempt in range(1, policy.max_retries + 1):
            try:
                resp: Response = requests.get(
                    self.api_url,
                    params=params or None,
                    headers=self.request_headers(),
                    timeout=self.timeout,
                    allow_redirects=self.allow_redirects,
                )
                resp.raise_for_status()

                try:
                    data = resp.json()
                except ValueError as exc:
                    logger.warning(
                        "[%s] JSON 파싱 실패 (시도 %d/%d): %s",
                        tag, attempt, policy.max_retries, exc,
                    )
                    last_exc = exc
                    if attempt < policy.max_retries:
                        time.sleep(policy.backoff_base ** attempt)
                    continue

                if not isinstance(data, dict):
                    logger.warning(
                        "[%s] 응답이 dict 아님 (시도 %d/%d): %s",
                        tag, attempt, policy.max_retries, type(data),
                    )
                    last_exc = TypeError(f"expected dict, got {type(data)}")
                    if attempt < policy.max_retries:
                        time.sleep(policy.backoff_base ** attempt)
                    continue

                rate_remaining = (
                    parse_int_header(resp, policy.header_remaining)
                    if policy.header_remaining
                    else None
                )
                rate_reset = (
                    parse_int_header(resp, policy.header_reset)
                    if policy.header_reset
                    else None
                )
                logger.debug(
                    "[%s] API 응답 수신 — params=%s, status=200, remaining=%s",
                    tag, params, rate_remaining,
                )
                return ApiCallResult(
                    data=data,
                    rate_remaining=rate_remaining,
                    rate_reset=rate_reset,
                )

            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                logger.warning(
                    "[%s] HTTP 오류 (시도 %d/%d): %d — params=%s",
                    tag, attempt, policy.max_retries, status, params,
                )
                if (
                    status == 429
                    and policy.honor_429_reset_header
                    and policy.header_reset
                    and exc.response is not None
                ):
                    reset_sec = parse_int_header(exc.response, policy.header_reset) or 60
                    logger.warning(
                        "[%s] 429 Too Many Requests — %ds 대기 후 재시도",
                        tag, reset_sec,
                    )
                    time.sleep(reset_sec)
                else:
                    mult = policy.status_backoff_multipliers.get(status, 1.0)
                    backoff = policy.backoff_base ** attempt * mult
                    if attempt < policy.max_retries:
                        logger.info("[%s] %.1fs 후 재시도", tag, backoff)
                        time.sleep(backoff)
                last_exc = exc

            except requests.exceptions.RequestException as exc:
                backoff = policy.backoff_base ** attempt
                logger.warning(
                    "[%s] 요청 실패 (시도 %d/%d): %s, %.1fs 후 재시도",
                    tag, attempt, policy.max_retries, exc, backoff,
                )
                if attempt < policy.max_retries:
                    time.sleep(backoff)
                last_exc = exc

        logger.error("[%s] 모든 재시도 실패 — params=%s: %s", tag, params, last_exc)
        return ApiCallResult(data=None)

    def sleep_interval(self) -> None:
        """사이트 rate_limit.min_interval_seconds 만큼 대기."""
        time.sleep(self.rate_limit.min_interval_seconds)

    def maybe_wait_rate_limit(
        self,
        rate_remaining: int | None,
        rate_reset: int | None,
    ) -> bool:
        """
        헤더 잔여 한도가 threshold 이하면 reset 초만큼 대기.
        대기했으면 True (호출 측에서 일반 interval sleep 을 건너뛸 수 있음).
        """
        policy = self.rate_limit
        if (
            policy.header_threshold is None
            or rate_remaining is None
            or rate_remaining > policy.header_threshold
        ):
            return False
        wait_sec = rate_reset if rate_reset is not None else 60
        logger.warning(
            "[%s] %s=%d ≤ %d — %ds 대기",
            self.source_name,
            policy.header_remaining,
            rate_remaining,
            policy.header_threshold,
            wait_sec,
        )
        time.sleep(wait_sec)
        return True

    # ------------------------------------------------------------------
    # RawJobPosting 조립
    # ------------------------------------------------------------------

    def jobs_to_raw_dicts(
        self,
        jobs: list[dict[str, Any]],
        saved_ids: set[tuple[str, str]],
        *,
        max_jobs: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        API job dict 목록 → RawJobPosting.to_dict() 목록.
        이미 저장된 (source_name, source_job_id)는 건너뛴다.

        Returns
        -------
        (raw_docs, skipped_count)
        """
        raw_docs: list[dict[str, Any]] = []
        skipped = 0
        tag = self.source_name

        for job in jobs:
            if max_jobs is not None and len(raw_docs) >= max_jobs:
                break
            if not isinstance(job, dict):
                logger.warning("[%s] 비정상 공고 항목 건너뜀: %r", tag, type(job))
                continue

            source_job_id = self.extract_job_id(job)
            if not source_job_id:
                logger.warning("[%s] id 필드 없는 공고 건너뜀", tag)
                continue

            if (tag, source_job_id) in saved_ids:
                skipped += 1
                continue

            try:
                posting = RawJobPosting(
                    source_name=tag,
                    source_job_id=source_job_id,
                    original_url=self.extract_original_url(job, source_job_id),
                    raw_html="",
                    raw_text=json.dumps(job, ensure_ascii=False),
                    parse_status="PENDING",
                )
                raw_docs.append(posting.to_dict())
            except Exception as exc:
                logger.warning(
                    "[%s] RawJobPosting 생성 실패 (id=%s): %s",
                    tag, source_job_id, exc,
                )
                continue

        return raw_docs, skipped

    # ------------------------------------------------------------------
    # 사이트별 훅
    # ------------------------------------------------------------------

    @abstractmethod
    def extract_jobs(self, page_data: dict[str, Any]) -> list[dict[str, Any]]:
        """페이지 응답에서 공고 dict 목록을 꺼낸다."""

    @abstractmethod
    def extract_job_id(self, job: dict[str, Any]) -> str:
        """공고 고유 ID 문자열."""

    @abstractmethod
    def extract_original_url(self, job: dict[str, Any], source_job_id: str) -> str:
        """원문 URL."""
