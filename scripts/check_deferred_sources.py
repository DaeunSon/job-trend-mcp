#!/usr/bin/env python3
"""
Adzuna HTML 크롤 엔드포인트 접근성 점검.

Cloudflare/CAPTCHA 우회는 시도하지 않고, 현재 응답 상태만 확인한다.
잡플래닛·LinkedIn·로켓펀치는 프로젝트 제외 — 프로브하지 않는다.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests
from curl_cffi import requests as curl_requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BLOCK_SIGNALS = (
    "just a moment",
    "attention required",
    "cf-browser-verification",
    "sorry, you have been blocked",
    "verify you are human",
    "captcha",
    "human verification",
    "additional verification required",
)


@dataclass
class ProbeTarget:
    name: str
    url: str
    use_curl_cffi: bool
    note: str


TARGETS: list[ProbeTarget] = [
    ProbeTarget(
        "adzuna_uk",
        "https://www.adzuna.co.uk/search?q=python",
        True,
        "UK SERP — article[data-aid] 추출 가능해야 함",
    ),
    ProbeTarget(
        "adzuna_us",
        "https://www.adzuna.com/search?q=python",
        True,
        "US 는 Human Verification(405) 예상 — 수집 대상 제외",
    ),
]


def _blocked(status: int | None, text: str) -> bool:
    if status in (401, 403, 405, 429, 503):
        return True
    low = (text or "")[:8000].lower()
    return any(sig in low for sig in BLOCK_SIGNALS)


def main() -> int:
    print(f"{'target':<14} {'status':<8} {'blocked':<8} note")
    print("-" * 90)

    for target in TARGETS:
        try:
            if target.use_curl_cffi:
                resp = curl_requests.get(
                    target.url, impersonate="chrome124", timeout=20,
                    headers={"User-Agent": UA},
                )
            else:
                resp = requests.get(
                    target.url, timeout=20, headers={"User-Agent": UA},
                )
            status = resp.status_code
            text = resp.text or ""
            blocked = _blocked(status, text)
            if target.name == "adzuna_uk" and status == 200 and 'data-aid="' in text:
                blocked = False
            print(f"{target.name:<14} {status!s:<8} {str(blocked):<8} {target.note}")
        except Exception as exc:
            print(f"{target.name:<14} {'err':<8} {'True':<8} {exc}")
        time.sleep(0.8)

    print("-" * 90)
    print("excluded: jobplanet / linkedin / rocketpunch (프로브 안 함)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
