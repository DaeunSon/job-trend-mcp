"""
Adzuna 접속 가능 여부 확인 스크립트 (0단계).

본 크롤러/파서를 만들기 전에 최소한의 요청으로 접속 가능 여부만 빠르게 확인한다.
어느 방법이 통과했는지 로그로 남기고, 결과에 따라 크롤러 구현 방식을 결정한다.

시도 순서:
  1. requests   — 실제 브라우저와 동일한 헤더 구성
  2. curl_cffi  — Chrome/Firefox와 동일한 TLS 지문 위장
  3. Playwright — headless=False 실제 브라우저 창

실행:
  python scripts/test_adzuna_access.py
"""
from __future__ import annotations

import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TARGET_URL = "https://www.adzuna.com/backend-developer"
TIMEOUT = 15

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

BLOCK_SIGNALS = [
    "just a moment",
    "please enable javascript",
    "attention required",
    "enable javascript and cookies",
    "cf-browser-verification",
    "verifying you are human",
    "ddos protection by cloudflare",
    "checking if the site connection is secure",
    "access denied",
    "robot or human",
]


def _is_blocked(text: str) -> bool:
    lower = text.lower()
    for sig in BLOCK_SIGNALS:
        if sig in lower:
            return True
    return False


def _result_summary(method: str, status: int | str, blocked: bool, note: str = "") -> None:
    icon = "PASS" if not blocked else "BLOCK"
    logger.info("%-12s [%s] HTTP %s%s", method, icon, status, f" — {note}" if note else "")


# ---------------------------------------------------------------------------
# 방법 1: requests
# ---------------------------------------------------------------------------

def try_requests() -> bool:
    logger.info("─── 방법 1: requests ───────────────────────────────────────")
    try:
        import requests
    except ImportError:
        logger.error("requests 미설치")
        return False

    try:
        resp = requests.get(TARGET_URL, headers=BROWSER_HEADERS, timeout=TIMEOUT)
        blocked = _is_blocked(resp.text)
        _result_summary("requests", resp.status_code, blocked or resp.status_code >= 400)
        if not blocked and resp.status_code < 400:
            logger.info("requests 성공 — 응답 앞 300자:\n%s", resp.text[:300])
            return True
        else:
            logger.warning("requests 실패 — 응답 앞 300자:\n%s", resp.text[:300])
            return False
    except Exception as exc:
        logger.error("requests 예외: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 방법 2: curl_cffi (Chrome TLS 지문 위장)
# ---------------------------------------------------------------------------

def try_curl_cffi() -> bool:
    logger.info("─── 방법 2: curl_cffi ──────────────────────────────────────")
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        logger.warning("curl_cffi 미설치 — 건너뜀 (pip install curl_cffi)")
        return False

    try:
        resp = cffi_requests.get(
            TARGET_URL,
            headers=BROWSER_HEADERS,
            timeout=TIMEOUT,
            impersonate="chrome124",
        )
        blocked = _is_blocked(resp.text)
        _result_summary("curl_cffi", resp.status_code, blocked or resp.status_code >= 400)
        if not blocked and resp.status_code < 400:
            logger.info("curl_cffi 성공 — 응답 앞 300자:\n%s", resp.text[:300])
            return True
        else:
            logger.warning("curl_cffi 실패 — 응답 앞 300자:\n%s", resp.text[:300])
            return False
    except Exception as exc:
        logger.error("curl_cffi 예외: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 방법 3: Playwright headless=False
# ---------------------------------------------------------------------------

def try_playwright() -> bool:
    logger.info("─── 방법 3: Playwright (headless=False) ────────────────────")
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.warning("playwright 미설치 — 건너뜀 (pip install playwright && playwright install chromium)")
        return False

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent=BROWSER_HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = ctx.new_page()

            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
            except PWTimeout:
                logger.error("Playwright goto 타임아웃")
                browser.close()
                return False
            except Exception as exc:
                logger.warning("Playwright goto 예외 (리다이렉트일 수 있음): %s", exc)

            time.sleep(3)  # JS 챌린지 완료 대기

            try:
                html = page.content()
            except Exception as exc:
                logger.error("Playwright content() 실패: %s", exc)
                browser.close()
                return False

            browser.close()

        blocked = _is_blocked(html)
        status = "200(추정)" if not blocked else "BLOCKED"
        _result_summary("playwright", status, blocked)
        if not blocked:
            from bs4 import BeautifulSoup
            text = BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
            logger.info("Playwright 성공 — 텍스트 앞 300자:\n%s", text[:300])
            return True
        else:
            logger.warning("Playwright 차단 — 응답 앞 300자:\n%s", html[:300])
            return False

    except Exception as exc:
        logger.error("Playwright 예외: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=" * 60)
    logger.info("Adzuna 접속 테스트 시작: %s", TARGET_URL)
    logger.info("=" * 60)

    results: dict[str, bool] = {}

    results["requests"] = try_requests()
    if results["requests"]:
        logger.info("\n[결론] requests 로 접속 성공 → 본 크롤러를 requests 기반으로 구현 가능")
        _print_summary(results)
        return

    time.sleep(2)
    results["curl_cffi"] = try_curl_cffi()
    if results["curl_cffi"]:
        logger.info("\n[결론] curl_cffi 로 접속 성공 → 본 크롤러를 curl_cffi 기반으로 구현 가능")
        _print_summary(results)
        return

    time.sleep(2)
    results["playwright"] = try_playwright()
    if results["playwright"]:
        logger.info("\n[결론] Playwright(headless=False) 로 접속 성공 → 본 크롤러를 Playwright 기반으로 구현")
        _print_summary(results)
        return

    logger.error("\n[결론] 세 방법 모두 실패 — Adzuna 크롤러 구현 보류")
    _print_summary(results)
    sys.exit(1)


def _print_summary(results: dict[str, bool]) -> None:
    logger.info("")
    logger.info("=" * 60)
    logger.info("접속 테스트 결과 요약")
    logger.info("=" * 60)
    for method, ok in results.items():
        logger.info("  %-12s : %s", method, "PASS" if ok else "FAIL / SKIP")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
