# 인수인계 (HANDOFF)

이 프로젝트를 처음 보는 분을 위한 현황 정리입니다.  
작성 기준: 코드·`src/config/sources.py`·테스트 실측 (2026-08-14).

현황 요약 → [project_overview.md](project_overview.md)  
스키마 상세 → [data_schema.md](data_schema.md)  
MCP tool → [mcp_server.md](mcp_server.md)  
MCP 연결 (로컬·웹) → [mcp_connection_guide.md](mcp_connection_guide.md)  
설치·실행 요약 → [../README.md](../README.md)

---

## 프로젝트가 하는 일

1. 여러 취업 사이트에서 채용공고를 가져온다.
2. 사이트마다 다른 표기를 **공통 표준**(직군·직무·스킬 등)으로 맞춘다.
3. JSON으로 저장한 뒤, MCP 서버 tool로 LLM이 조회하게 한다.

아직 DB는 없고 `data/` 아래 JSON이 저장소입니다.

---

## 완료된 것

### MCP 서버 (1차·로컬 stdio + 2차·웹 HTTP)

- tool **5개**: 공고 검색 / 스킬 트렌드 / 직군별 건수 / 급여 요약 / 회사 채용 현황
- 호출마다 JSONL 모니터링 (`src/mcp_server/monitoring.py`, `@monitor_tool`)
- 직무명: taxonomy seed alias·고신뢰 오타 보정·실패 시 `Did you mean` 제안
- `employment_type`: `FULL_TIME` / `Full-time` 정규화 비교
- `pytest tests/test_mcp_server.py` 통과
- 실행: `python scripts/demo_mcp_tools.py` 또는 `PYTHONPATH=. mcp dev src/mcp_server/server.py`
- 품질 시뮬레이션: `python scripts/simulate_mcp_queries.py`
- **검증 (최종):**
  - **1안 로컬 stdio** — Claude Desktop 실연결 완료 (2026-08-11, 자연어 5문항 → 기대 tool 각각 호출, `env.PYTHONPATH` 포함)
  - **2안 웹** — Streamable HTTP + ngrok → **Claude 웹 커스텀 커넥터** 실연결·tool 호출 완료
  - 상세 → [mcp_connection_guide.md](mcp_connection_guide.md) · tool 스펙은 [mcp_server.md](mcp_server.md)

### 수집·정규화 파이프라인 — 활성 11사이트

`ALL_SOURCES` **11개 전부** `is_active=True`입니다.  
모두 사이트별 추출 후 공통 `build_job_posting()`까지 연결되어 있습니다.

| 사이트 | `source_name` | 수집 방식 (실제) | 코드 |
|--------|---------------|------------------|------|
| 사람인 | `saramin` | HTML 웹 크롤링 (SERP+상세) | `crawlers/saramin/` |
| 잡코리아 | `jobkorea` | HTML 웹 크롤링 | `crawlers/jobkorea/` |
| 원티드 | `wanted` | 내부 JSON API (인증 없음) | `crawlers/wanted/` |
| 점핏 | `jumpit` | 내부 JSON API (`jumpit-api.saramin.co.kr`) | `crawlers/jumpit/` |
| 랠릿 | `rallit` | 내부 JSON API | `crawlers/rallit/` |
| 고용24 | `work24` | HTML 웹 크롤링 (공공 포털) | `crawlers/work24/` |
| USAJobs | `usajobs` | 내부 JSON API (`POST /Search/ExecuteSearch`) | `crawlers/usajobs/` |
| Adzuna | `adzuna` | HTML 크롤 (gb/au, 공식 API 미사용) | `crawlers/adzuna/` |
| Remotive | `remotive` | **공식 공개 API** | `crawlers/remotive/` |
| The Muse | `themuse` | **공식 공개 API** | `crawlers/themuse/` |
| Arbeitnow | `arbeitnow` | **공식 공개 API** | `crawlers/arbeitnow/` |

참고: `CrawlSource.source_type`이 `WEB_CRAWLING`이어도 원티드·점핏·랠릿·USAJobs처럼
**내부 JSON API**를 쓰는 경우가 있습니다. 위 표의 「수집 방식」을 우선하세요.

### 품질 스냅샷

- `pytest tests` → **1108 passed** (2026-08-14)
- taxonomy: 직군 15 / 직무 53 / 스킬 91 ([data_schema.md](data_schema.md))

---

## 제외 확정 (크롤러 없음 / `ALL_SOURCES` 미등록)

### 법적·정책 리스크

| 대상 | 사유 |
|------|------|
| 잡플래닛 | AI 학습·무단 수집 금지 고지 |
| LinkedIn | robots·파트너 승인제 |
| 로켓펀치 | 이용약관상 고위험 |

### 서비스 종료

| 대상 | 사유 |
|------|------|
| 프로그래머스 | 회사 공지로 채용 서비스 운영 중단 확인(2025년 4월경) — 관련 코드 삭제됨 |

### 채용공고 스키마와 불일치 (통계·참조·메타 API)

개별 채용공고(`job_postings`) 모델과 맞지 않아 제외.  
쓰려면 **별도 스키마·파이프라인**이 필요합니다.

| 대상 | 성격 |
|------|------|
| 국민연금공단 | 통계/참조 |
| O\*NET | 직업 분류·참조 |
| BLS | 노동통계 |
| Stack Overflow Developer Survey | 설문·통계 |
| Levels.fyi | 보상·레벨 참조 |
| JSearch | 크롤 대상 웹이 아닌 API 상품 |

---

## 직군 범위 (확정)

표준 직군은 **15개**로 유지한다. IT·사무직 중심 12개에 Education / Supply Chain / Healthcare / Other를 더한 현재 taxonomy가 제품 범위다. 고용24 전체 업종으로의 추가 확대는 하지 않는다.

그 외 제품 범위(어떤 LLM 호스트에 배포할지, DB 선정 등)는 이 문서 작성 시점에 코드로 고정된 결정이 없다.

---

## 새 사이트를 추가하려면

### 설계 원칙

```
사이트별 추출 (crawlers/{site}/parser.py)
        ↓  RawExtractedFields
공통 정규화 (normalization/posting_normalizer.build_job_posting)
        ↓
job_postings JSON 저장 (storage/json_writer)
```

- **꺼내는 것**만 사이트별로 구현합니다.
- 직군·직무·고용형태·근무형태 표준화는 공통 모듈에 맡깁니다.
- taxonomy 표준값은 `src/taxonomy/`, 사이트 검색어 매핑은 `crawlers/{site}/search_queries.py`.

### 예시: 원티드 구조 (최근 활성 사이트 패턴)

```
src/crawlers/wanted/
├── __init__.py
├── client.py           # API/목록·상세 수집, run_*_batch
├── parser.py           # raw → RawExtractedFields → build_job_posting
└── search_queries.py   # taxonomy 직무 ↔ 사이트 태그/검색 파라미터

scripts/run_wanted.py   # CLI 진입점 (--parse-only, --reparse, …)
tests/test_wanted_*.py
```

추가로 할 일:

1. `src/config/sources.py`에 `CrawlSource` 추가 후 `ALL_SOURCES`에 append  
2. rate limit·robots·약관을 `rate_limit_policy`에 기록  
3. 스모크 수집 1페이지 + 파싱 + 유닛 테스트

HTML SERP형(사람인·잡코리아)은 `crawlers/common/html_serp.py` 베이스를,  
JSON API형은 `common/json_api.py` / `api_client_base.py` 패턴을 참고하면 됩니다.

---

## 알려진 이슈

확인된 항목만 적습니다.

| 이슈 | 상태 | 비고 |
|------|------|------|
| `curl_cffi`가 `requirements.txt`에 없음 | **문서화됨** | Adzuna HTML 크롤·접근 점검에 필요. README에 수동 설치 안내 |
| 일부 공고 `job_category_name` 공란 / `_unknown` 직무 | **데이터 품질** | MCP `uncategorized_count` 등으로 관측 가능. alias·파서 보강 여지 |
| Adzuna US (`www.adzuna.com`) | **수집 제외** | CAPTCHA — gb/au만 |
| `company.name` 대소문자 불일치 (SumUp/sumup, Speechify/speechify) | **경미** | 동일 회사 표기 2건. company alias 추가하면 해소 |
| `get_company_hiring_activity` 유사도 오탐 (`spacexx`→Paychex) | **수정됨** | `difflib` cutoff 0.55→**0.75**. SpaceX≈0.92만 통과, Paychex≈0.71 제외 |
| `mcp dev` / Claude Desktop에서 `ModuleNotFoundError: No module named 'src'` | **문서화됨** | `PYTHONPATH` 미설정. README·[mcp_server.md](mcp_server.md)에 안내. 근본 해소는 아래 개선사항 |
| Claude 웹 커넥터 초반 OAuth 404 | **정상 동작** | `/register`, `/.well-known/oauth-*` 404 후 무인증 폴백. 진짜 장애는 Host **421** — 아래 절 참고 |

위 표 외, `pytest tests` 기준 **실패 중인 유닛 테스트는 없음**.

---

## Claude 웹 커스텀 커넥터 — OAuth 404는 정상, 421이 진짜 문제

Streamable HTTP를 ngrok으로 노출해 Claude 웹 **커스텀 커넥터**에 붙일 때,
브라우저/네트워크 로그에 아래가 **먼저** 보일 수 있습니다.

| 요청 | 흔한 응답 | 의미 |
|------|-----------|------|
| `/.well-known/oauth-protected-resource` 등 | **404** | 이 서버는 OAuth를 구현하지 않음 |
| `/register` (동적 클라이언트 등록) | **404** | 동일 |

Claude는 OAuth 메타/등록이 없으면 **무인증(no-auth) MCP로 폴백**합니다.
따라서 초반 404만으로는 연결 실패로 단정하면 안 됩니다. (정식 OAuth는 미구현 — 의도적)

그 다음에 나오는 응답이 실제 장애 신호입니다.

| 응답 | 원인 | 조치 |
|------|------|------|
| **421** Invalid Host | SDK DNS-rebinding 보호 — Host 헤더가 allowlist 밖 | 서버 실행 시 `MCP_ALLOWED_HOSTS='*.ngrok-free.dev'` (또는 `--allowed-host`) |
| 연결 타임아웃 / 터널 끊김 | ngrok·로컬 서버 미기동 | HTTP 서버·터널 재기동 후 커넥터 URL 갱신 |

**ngrok 무료 플랜**은 터널을 다시 켤 때마다 `*.ngrok-free.dev` 서브도메인이 바뀝니다.
정확한 호스트를 매번 넣기보다 DNS 와일드카드(`*.ngrok-free.dev`)를 쓰면 Host 421을 피할 수 있습니다.
(기본값에 ngrok 와일드카드는 **없음** — 실행할 때마다 함께 넘겨야 함.)

관련 코드: `src/mcp_server/run.py` (`match_allowed_host`, `resolve_run_config`).

---

## 알려두면 좋은 개선사항

큰 구조 변경은 당장 범위 밖이지만, 시간 날 때 검토하면 좋은 항목입니다.

### `pyproject.toml` + editable install로 `PYTHONPATH` 의존 제거

- **현황:** `pyproject.toml` / `setup.py`가 없다. `src/`는 소스 트리일 뿐 pip 패키지가 아니다.
- **증상:** `mcp dev`·Claude Desktop 등에서 `ModuleNotFoundError: No module named 'src'` — 매번 `PYTHONPATH` 또는 `env.PYTHONPATH`가 필요 (실수로 두 번 확인됨).
- **제안:** 최소 `pyproject.toml`(예: setuptools/`src` layout, package `src` 또는 패키지명을 `job_trend_mcp` 등으로 정리)을 추가한 뒤  
  `pip install -e .` 하면 site-packages에 링크되어 **어디서 실행해도** `import src...`가 가능해진다.
- **주의:** 패키지명·import 경로를 `src`에서 바꾸면 crawler/MCP 전반에 영향 → 변경 시 테스트·문서 일괄 갱신 필요. 인턴 종료 직전엔 문서 우회만으로 충분.

---

## 추천 온보딩 순서

1. README로 venv·의존성 설치  
2. `PYTHONPATH=. mcp dev ...` 또는 `python scripts/demo_mcp_tools.py`로 MCP 응답 확인  
3. `python scripts/run_wanted.py --function "Backend Engineer" --max-pages 1`로 수집 한 바퀴  
4. [data_schema.md](data_schema.md)로 필드·경로 숙지  
5. `sources.py`의 active/inactive·제외 사유 읽기  
6. 새 사이트 작업 시 원티드 또는 Adzuna 폴더를 템플릿으로 복사

질문·결정이 막히면 이 문서의 「알려진 이슈」와 「알려두면 좋은 개선사항」부터 확인하면 됩니다.