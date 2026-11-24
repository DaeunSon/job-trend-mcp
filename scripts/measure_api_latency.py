"""공고 검색 API 응답 시간 측정.

정해 둔 질의 5개를 돌아가며 호출하고 p50 / p95 를 한 줄로 출력한다.
요청 간격 250ms 는 Nginx 제한(5 r/s) 아래로 맞춘 값이다.

    python scripts/measure_api_latency.py --base-url http://127.0.0.1:8001
"""
from __future__ import annotations

import argparse
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

QUERIES: list[dict[str, str]] = [
    {},
    {"job_function": "Backend Engineer"},
    {"location": "서울"},
    {"q": "engineer"},
    {"skill": "python"},
]
INTERVAL_SEC = 0.25


def percentile(values: list[float], p: float) -> float:
    """nearest-rank 백분위수. 빈 목록이면 ValueError."""
    if not values:
        raise ValueError("values is empty")
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _call(url: str) -> tuple[float, bool]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            resp.read()
            ok = resp.status == 200
    except (urllib.error.URLError, OSError):
        ok = False
    return (time.perf_counter() - start) * 1000, ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=1)
    args = ap.parse_args()

    base = args.base_url.rstrip("/") + "/api/v1/postings"
    urls = [
        base + ("?" + urllib.parse.urlencode(q) if q else "")
        for q in (QUERIES[i % len(QUERIES)] for i in range(args.requests))
    ]
    results: list[tuple[float, bool]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = []
        for url in urls:
            futures.append(pool.submit(_call, url))
            time.sleep(INTERVAL_SEC)
        results = [f.result() for f in futures]

    errors = sum(1 for _, ok in results if not ok)
    times = [ms for ms, ok in results if ok]
    if not times:
        print(f"requests={len(results)} errors={errors} (성공 응답 없음)")
        raise SystemExit(1)
    print(
        f"requests={len(results)} errors={errors} "
        f"p50_ms={percentile(times, 50):.1f} p95_ms={percentile(times, 95):.1f} "
        f"max_ms={max(times):.1f}"
    )


if __name__ == "__main__":
    main()
