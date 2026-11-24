# job-trend-mcp

여러 취업 사이트에서 채용공고를 수집·표준화해 PostgreSQL에 담고, **REST API**와 **MCP(Model Context Protocol) 서버**로 공개하는 프로젝트입니다. LLM이 트렌드 분석·질의응답에 쓸 수 있습니다.

## 공개 주소

배포 후 채움 (서버는 아직 배포 전, 도메인 미정).

| 용도 | 주소 |
|------|------|
| REST API | `https://<도메인>/api/v1/postings` |
| MCP (Streamable HTTP) | `https://<도메인>/mcp` |

```bash
curl https://<도메인>/healthz
curl "https://<도메인>/api/v1/postings?job_function=Backend%20Engineer&limit=5"
curl "https://<도메인>/api/v1/postings?skill=python&location=서울&limit=5"
```

검색 파라미터: `job_function`, `job_category`, `location`, `employment_type`, `work_arrangement`, `source_name`, `q`, `skill`, `posted_from`, `active_only`, `limit`, `offset`.

**Claude 커넥터 연결:** Claude 설정 → 커넥터 → 커스텀 커넥터 추가에 `https://<도메인>/mcp` 를 넣습니다(인증 없음). 단계별 안내는 [docs/mcp_connection_guide.md](docs/mcp_connection_guide.md).

## 구성

```
Claude / curl ──HTTPS──> Nginx (IP별 요청 제한 5 r/s)
                           ├─ /api/v1/*, /healthz ─> FastAPI (127.0.0.1:8001) ─┐
                           └─ /mcp ───────────────> MCP 서버 (127.0.0.1:8000) ─┤
                                                                               v
                                                                   PostgreSQL (localhost만)
```

배포 절차는 [docs/deploy/manual-ec2.md](docs/deploy/manual-ec2.md), 측정한 수치는 [docs/metrics/phase1.md](docs/metrics/phase1.md).

## 로컬 실행

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
docker compose -f docker-compose.dev.yml up -d      # PostgreSQL (127.0.0.1:54329)
export DATABASE_URL=postgresql://jobtrend:jobtrend@127.0.0.1:54329/jobtrend
.venv/bin/python -m src.db.migrate
.venv/bin/python scripts/backfill_snapshot.py --archive data/data-archive/data_snapshot_20260803.tar.gz
.venv/bin/uvicorn src.api.app:app --host 127.0.0.1 --port 8001
curl "http://127.0.0.1:8001/api/v1/postings?limit=3"
```

MCP 서버는 같은 `DATABASE_URL` 로 아래 "MCP 서버 실행"을 따릅니다. 응답 시간 측정: `python scripts/measure_api_latency.py --base-url http://127.0.0.1:8001`.

## 지금의 한계

- 데이터는 2026-07-29 ~ 08-04에 수집한 표본 659건이며 매일 갱신되지 않습니다. 8월 표본은 arbeitnow에 치우쳐 있습니다.
- 인증 없는 읽기 전용입니다. 공개 응답에는 공고 본문(`description`)을 넣지 않고 요약 필드와 `original_url`만 줍니다.
- MCP tool 을 `store=` 없이 부르는 개발 스크립트(`scripts/simulate_mcp_queries.py`, `scripts/compare_mcp_tuning.py`, `scripts/run_eval.py`)는 이제 `DATABASE_URL` 이 필요합니다.
- 테스트는 `TEST_DATABASE_URL`(예: `postgresql://jobtrend:jobtrend@127.0.0.1:54329/jobtrend_test`)과 개발용 PostgreSQL(`docker compose -f docker-compose.dev.yml up -d`)이 있어야 돕니다.
- 다음 순서: 수집 → DB 연결, Compose, Terraform.

---

## 수집 흐름

1. 사이트별 크롤러가 원문 수집 → `data/raw_job_postings/`
2. 사이트별 파서 + 공통 `build_job_posting()` 정규화 → `data/job_postings/`
3. 스냅샷을 PostgreSQL에 적재하면 REST API와 MCP tool 이 조회

---

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Adzuna 접근 점검 등 Playwright가 필요한 경우에만
playwright install chromium
```

### 환경 변수

현재 **필수 `.env` 항목은 없습니다.** Adzuna도 공식 API 키 없이 HTML 크롤입니다.

Adzuna HTML 크롤과 `scripts/check_deferred_sources.py`는 `curl_cffi`를 사용합니다.
로컬에 없다면 추가로 설치하세요.

```bash
pip install curl_cffi
```

---

## 크롤러 실행

사이트별 진입점은 `scripts/run_*.py` 입니다. 공통 패턴:

| 옵션 | 의미 |
|------|------|
| (인자 없음 / `--batch`) | 기본 검색어·직무 목록으로 배치 수집 |
| `--parse-only` | 수집 건너뛰고 raw → job_postings 파싱만 |
| `--reparse` | 이미 `PARSED`인 raw도 다시 파싱 (`--parse-only`와 함께) |
| `--no-parse` | 수집만 하고 파싱 생략 |
| `--crawl-date` / `--date` | 저장 날짜 라벨 `YYYY-MM-DD` (스크립트마다 이름 상이) |
| `-v` / `--verbose` | DEBUG 로그 |

### 활성 사이트 예시

```bash
# 원티드 (내부 JSON API) — 직무 지정 + 페이지 제한
python scripts/run_wanted.py --function "Backend Engineer" --max-pages 1

# 사람인 (HTML SERP)
python scripts/run_saramin.py -q "백엔드 개발자" --max-pages 2

# Remotive / The Muse / Arbeitnow (공식 공개 API)
python scripts/run_remotive.py --category software-dev
python scripts/run_themuse.py --max-pages 1
python scripts/run_arbeitnow.py --max-pages 1

# Adzuna (HTML 크롤, gb/au)
python scripts/run_adzuna.py --what "backend engineer" --country gb --max-pages 1

# 파싱만 / 재파싱
python scripts/run_wanted.py --parse-only
python scripts/run_wanted.py --parse-only --reparse --crawl-date 2026-07-28
```

나머지: `run_jobkorea.py`, `run_jumpit.py`, `run_rallit.py`, `run_usajobs.py`, `run_work24.py`.  
각 파일 상단 docstring에 사이트별 옵션이 정리되어 있습니다.

MCP tool 품질 로그·시뮬레이션:

```bash
python scripts/simulate_mcp_queries.py
python scripts/compare_mcp_tuning.py
```

---

## MCP 서버 실행

단계별 연결(로컬 설치, Claude Desktop, 웹 커넥터)은 [docs/mcp_connection_guide.md](docs/mcp_connection_guide.md)를 보세요.

SDK: PyPI `mcp` **v2** (`MCPServer`). 전송 방식은 **stdio**(기본)와 **Streamable HTTP**를 지원합니다.

먼저 한 번 설치합니다. 이후에는 `PYTHONPATH` 없이 어디서든 `src.…` 를 import 할 수 있습니다.
상세는 [docs/mcp_server.md](docs/mcp_server.md).

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
# 시연용 — tool 직접 호출 (in-memory)
python scripts/demo_mcp_tools.py

# MCP Inspector
mcp dev src/mcp_server/server.py

# 1안) 로컬 stdio (Cursor / Claude Desktop) — 프로젝트 루트에서 실행
python -m src.mcp_server.server
# 동일: --transport stdio

# 2안) Streamable HTTP — 기본 바인딩 127.0.0.1 (외부 직접 오픈 금지)
python -m src.mcp_server.server --transport streamable-http --port 8000
# 엔드포인트: http://127.0.0.1:8000/mcp

# ngrok 등 원격 터널 사용 시 — 실행할 때마다 allowlist를 함께 넘겨야 함
# (기본값에 *.ngrok-free.dev 가 들어 있지 않음. 안 넣으면 Host 421)
# ngrok 무료 플랜은 재시작마다 서브도메인이 바뀌므로 *.ngrok-free.dev 와일드카드를 씀
MCP_ALLOWED_HOSTS='*.ngrok-free.dev' python -m src.mcp_server.server --transport streamable-http --port 8000
# 동일: --allowed-host '*.ngrok-free.dev'
```

환경변수 대안: `MCP_TRANSPORT`, `MCP_HOST`(기본 `127.0.0.1`), `MCP_PORT`, `MCP_PATH`, `MCP_ALLOWED_HOSTS`.  
`0.0.0.0` 바인딩은 거부합니다.  
ngrok 사용 시 **서버를 띄울 때마다** `MCP_ALLOWED_HOSTS='*.ngrok-free.dev'` 또는 `--allowed-host '*.ngrok-free.dev'`를 같이 작성해야 합니다 (`export`는 해당 터미널 세션에만 유지됨).  
무료 ngrok은 터널 재시작마다 도메인이 바뀌므로, 호스트를 매번 고치지 않으려면 DNS 와일드카드가 필요합니다.

**연결 검증 상태:** 1안(Claude Desktop · stdio) · 2안(Claude 웹 커스텀 커넥터 · HTTP+ngrok) 모두 실연결 완료. 상세·OAuth/421 트러블슈팅은 [docs/HANDOFF.md](docs/HANDOFF.md)·[docs/mcp_server.md](docs/mcp_server.md).

Cursor / Claude Desktop 등록 시 `pip install -e ".[dev]"` 를 마친 venv 의 python 을 `command` 로 지정하면
`env.PYTHONPATH` 가 필요 없습니다.

```json
{
  "mcpServers": {
    "job-trend-mcp": {
      "command": "/ABS/PATH/job-trend-mcp/.venv/bin/python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/ABS/PATH/job-trend-mcp"
    }
  }
}
```

도구 상세·응답 예시는 [docs/mcp_server.md](docs/mcp_server.md)를 보세요.
---

## 프로젝트 구조

```
job-trend-mcp/
├── src/
│   ├── config/              # crawl_sources 시딩 (sources.py)
│   ├── crawlers/            # 사이트별 수집·파서 (adzuna, arbeitnow, …)
│   │   └── common/          # HTML SERP / JSON API 공통 베이스
│   ├── mcp_server/          # MCP 서버 (tool 5개 + monitoring.py)
│   ├── models/              # 컬렉션 dataclass (schemas.py)
│   ├── normalization/       # build_job_posting, alias, location 등
│   ├── storage/             # JSON 저장/조회 (json_writer.py)
│   └── taxonomy/            # 표준 직군·직무·스킬·고용형태 등
├── scripts/                 # run_*.py, demo_mcp_tools.py, simulate_mcp_queries.py
├── tests/                   # 유닛 테스트 (pytest tests)
├── data/                    # 로컬 JSON (git 제외) — raw / job_postings / aliases
├── docs/                    # 상세 문서
├── requirements.txt
└── README.md
```

---

## 문서

| 문서 | 내용 |
|------|------|
| [docs/project_overview.md](docs/project_overview.md) | 현황 요약 (흐름·11사이트·저장 필드·MCP 5기능·연결 검증) |
| [docs/mcp_connection_guide.md](docs/mcp_connection_guide.md) | MCP 연결 가이드 (로컬 설치, Claude Desktop, 웹 커넥터) |
| [docs/mcp_server.md](docs/mcp_server.md) | MCP tool 스펙·예시 |
| [docs/data_schema.md](docs/data_schema.md) | 컬렉션 스키마·저장 경로·taxonomy 수치 |
| [docs/deploy/manual-ec2.md](docs/deploy/manual-ec2.md) | EC2 수동 배포 절차 |
| [docs/metrics/phase1.md](docs/metrics/phase1.md) | 1단계 수치 |
| [docs/HANDOFF.md](docs/HANDOFF.md) | 인수인계 (완료/제외, 새 사이트 추가법) |
| [docs/crawling_sprint_summary.md](docs/crawling_sprint_summary.md) | 1차 스프린트 기록 (**역사적 참고** — 최신 상태는 위 문서·코드 우선) |

---

## 테스트

```bash
TEST_DATABASE_URL=postgresql://jobtrend:jobtrend@127.0.0.1:54329/jobtrend_test pytest tests
```

2026-11-24 기준 → **1278 passed**.
