"""
사람인 SERP HTML 구조 디버깅 스크립트 v2.
카드 내부 구조(회사명, 조건, 마감일) 상세 분석.
"""
import sys
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

URL = (
    "https://www.saramin.co.kr/zf_user/search/recruit"
    "?searchword=%EB%B0%B1%EC%97%94%EB%93%9C+%EA%B0%9C%EB%B0%9C%EC%9A%94%EC%9E%90"
    "&recruitPage=1&recruitPageCount=40"
)

resp = requests.get(URL, headers={
    "User-Agent": UA,
    "Referer": "https://www.saramin.co.kr/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}, timeout=20)

print(f"Status: {resp.status_code}")
print(f"HTML 길이: {len(resp.text):,} bytes")
print()

soup = BeautifulSoup(resp.text, "lxml")

# ── 1. 총 건수 셀렉터 확인 ──────────────────────────────────────────────────
print("=" * 70)
print("[총 건수 셀렉터]")
tag = soup.select_one("span.cnt_result")
if tag:
    print(f"  span.cnt_result → {tag.get_text(strip=True)!r}")
else:
    print("  span.cnt_result → 없음")

# ── 2. 카드 개수 확인 ─────────────────────────────────────────────────────
print()
cards = soup.select("div.item_recruit")
print(f"[div.item_recruit 카드 수] {len(cards)}개")
print()

if not cards:
    print("카드가 없습니다. 다른 셀렉터를 확인합니다.")
    for sel in ["article.list-post", ".list-item", "div.box-item", "[data-rec-idx]"]:
        found = soup.select(sel)
        if found:
            print(f"  ✅ {sel!r} → {len(found)}개")
    sys.exit(1)

# ── 3. 첫 번째 카드 전체 요소 분석 ──────────────────────────────────────────
print("=" * 70)
print("[첫 번째 카드 자식 요소 구조]")
first = cards[0]

def print_tree(el, depth=0, max_depth=5):
    if depth > max_depth:
        return
    indent = "  " * depth
    classes = el.get("class", [])
    cls_str = f".{'.'.join(classes)}" if classes else ""
    text_only = el.get_text(strip=True)[:60] if el.string else ""
    print(f"{indent}<{el.name}{cls_str}> {text_only!r}")
    for child in el.children:
        if hasattr(child, "name") and child.name:
            print_tree(child, depth + 1, max_depth)

print_tree(first)

# ── 4. 카드 내부 셀렉터 시험 ─────────────────────────────────────────────────
print()
print("=" * 70)
print("[카드 내부 셀렉터 시험]")

selectors = {
    "제목": [
        "h2.job_tit a",
        "h1.job_tit a",
        ".job_tit a",
        "strong.job-tit a",
    ],
    "회사명": [
        "a.coName",
        ".coName a",
        ".corp_name a",
        "a.corp_name",
        ".company_name a",
        "strong.corp-name a",
        ".company a",
    ],
    "조건(지역/경력/학력/고용형태)": [
        ".job_condition span",
        ".job-condition span",
        ".condition span",
        ".work-info span",
        ".recruit-info span",
        ".tag_recruit span",
        ".keywords span",
    ],
    "마감일": [
        ".job_date .date",
        ".job_date span",
        ".deadline .date",
        ".date-info .date",
        "span.date",
        ".dday",
        ".end-date",
        ".dead-line",
    ],
}

for label, sel_list in selectors.items():
    print(f"\n  [{label}]")
    for sel in sel_list:
        found = first.select(sel)
        if found:
            for el in found[:3]:
                text = el.get_text(strip=True)
                print(f"    ✅ {sel!r:35s} → {text!r}")
            break
        else:
            print(f"    ❌ {sel!r:35s}")

# ── 5. 여러 카드 샘플 출력 ───────────────────────────────────────────────────
print()
print("=" * 70)
print("[카드 샘플 3개 — 주요 텍스트]")

for i, card in enumerate(cards[:3]):
    print(f"\n  === 카드 #{i+1} ===")
    # 제목
    tit = card.select_one("h2.job_tit a, .job_tit a")
    print(f"  제목: {tit.get_text(strip=True)!r}" if tit else "  제목: 없음")
    # 회사명
    co = card.select_one("a.coName, .coName a, .corp_name a, a.corp_name")
    print(f"  회사: {co.get_text(strip=True)!r}" if co else "  회사: 없음")
    # 조건
    cond = card.select(".job_condition span, .job-condition span, .condition span")
    print(f"  조건: {[s.get_text(strip=True) for s in cond]}" if cond else "  조건: 없음")
    # 마감일
    dl = card.select_one(".job_date .date, .job_date span, .deadline span, span.date, .dday")
    print(f"  마감: {dl.get_text(strip=True)!r}" if dl else "  마감: 없음")
    # rec_idx
    link = card.select_one("a[href*='rec_idx']")
    if link:
        m = re.search(r"rec_idx=(\d+)", link.get("href", ""))
        print(f"  rec_idx: {m.group(1)}" if m else "  rec_idx: 파싱 실패")

# ── 6. 카드 첫 번째 전체 HTML (더 넓은 영역) ────────────────────────────────
print()
print("=" * 70)
print("[첫 번째 카드 원본 HTML (처음 8000자)]")
html = str(first)
print(html[:8000])
if len(html) > 8000:
    print(f"... (총 {len(html)} chars, 잘림)")
