# MCP 서버

작성 기준: `src/mcp_server/` 코드 (2026-08-14).  
Python SDK: **mcp v2** (`from mcp.server import MCPServer`).

로컬 설치·Claude Desktop·웹 커넥터 절차는 [mcp_connection_guide.md](mcp_connection_guide.md)를 보세요.  
현황 한 장 요약은 [project_overview.md](project_overview.md)입니다.

서버 시작 시 `data/job_postings/**/*.json`을 한 번 메모리에 올립니다
(약 1천 건·수 MB 규모 — `data_loader.py` 주석의 실측 근거).

**검증:** MCP Inspector·`demo_mcp_tools.py`·HTTP 클라이언트뿐 아니라,
**Claude Desktop 실연결(stdio)로도 검증 완료** (2026-08-11).
자연어 5문항에 대해 기대 tool이 각각 호출됨
(`search_job_postings` / `get_skill_trend` / `get_posting_count_by_category` /
`get_salary_summary` / `get_company_hiring_activity`).

---

## Tool 목록

| Tool | 파일 | 역할 |
|------|------|------|
| `search_job_postings` | `tools/search.py` | 직무·지역 등으로 공고 검색 |
| `get_skill_trend` | `tools/skill_trend.py` | 직무별 기술스택 빈도 |
| `get_posting_count_by_category` | `tools/category_stats.py` | 직군별 공고 수 |
| `get_salary_summary` | `tools/salary_summary.py` | 직무·지역 급여 통계 |
| `get_company_hiring_activity` | `tools/company_activity.py` | 회사별 채용 현황 |

등록 진입점: `src/mcp_server/server.py`

공통 응답 패턴:

- `status`: `"ok"` | `"unknown_param"` | `"empty"` | `"no_salary_data"` | `"unknown_company"`
- `message`: 안내 문구 (`ok`이면 `null`)
- 잘못된 taxonomy 값은 예외 대신 `unknown_param` + 사용 가능 목록
- 급여 숫자 없음 / 회사명 불일치는 예외 대신 안내 상태 코드
---

## 1. `search_job_postings`

조건에 맞는 채용공고를 검색합니다. 조건을 생략하면 최근 공고부터 반환합니다.

### 파라미터

| 이름 | 타입 | 기본값 | 필수 | 설명 |
|------|------|--------|------|------|
| `job_function` | `str \| None` | `None` | 아니오 | taxonomy 직무명. 한글·약칭·고신뢰 오타는 alias/보정으로 해석 |
| `job_category` | `str \| None` | `None` | 아니오 | taxonomy 직군명 |
| `location` | `str \| None` | `None` | 아니오 | city/region/country/raw_text 부분 일치 (대소문자 무시) |
| `employment_type` | `str \| None` | `None` | 아니오 | `FULL_TIME` / `Full-time` / `full time` 정규화 동등 비교 + 부분 일치 |
| `work_arrangement` | `str \| None` | `None` | 아니오 | `ONSITE` / `REMOTE` / `HYBRID` 등 |
| `source_name` | `str \| None` | `None` | 아니오 | 수집 사이트. `jobkorea` / `saramin` / `rallit` / `arbeitnow` 등 `ALL_SOURCES` 값. 대소문자 무시 |
| `limit` | `int` | `20` | 아니오 | 1~100으로 클램프 |
| `active_only` | `bool` | `True` | 아니오 | `crawl_status == ACTIVE`만 |

### 반환

```json
{
  "status": "ok",
  "message": null,
  "count": 3,
  "total_matched": 102,
  "results": [
    {
      "title": "...",
      "company": "...",
      "location": "...",
      "employment_type": "...",
      "work_arrangement": "...",
      "job_function": "...",
      "job_category": "...",
      "posted_at": "2026-08-04",
      "original_url": "https://...",
      "source_name": "jumpit"
    }
  ]
}
```

요약 필드만 반환합니다 (`description` 등 본문 제외).

`source_name` 해석: `src/config/sources.py` 의 `ALL_SOURCES` 정확·대소문자 무시. 없으면 `unknown_param` + `available_source_names`.

로드는 `data/job_postings` 만 사용한다 (`raw_job_postings` 아님). 같은 `id`(또는 `source_name`+`source_job_id`)가 재수집 파일로 여러 개면 **최신 `created_at` 1건**만 남긴다. `total_matched` 는 이 고유 공고 수이다.

`job_function` 해석 (`data_loader.resolve_job_function`): taxonomy 정확·대소문자 무시 → seed alias(한글·약칭) → 토큰 부분집합이 유일하면 채택(`DevOps Engineer` → `DevOps / Platform Engineer`) → difflib ≥ 0.90 오타 보정 → 실패 시 `unknown_param` + `Did you mean`.

### 호출 예시 (실측)

```python
# MCP Client / demo_mcp_tools.py
await client.call_tool(
    "search_job_postings",
    {"job_function": "Backend Engineer", "location": "서울", "limit": 3},
)
```

응답 요약 (2026-08-10, 로컬 `data/`):

- `status`: `ok`
- `total_matched`: 102
- 상위 예: 지엔에이컴퍼니(jumpit), 코어로보틱스(rallit), 디라티오(rallit)

```python
await client.call_tool(
    "search_job_postings",
    {
        "job_function": "Backend Engineer",
        "location": "서울",
        "source_name": "jobkorea",
        "limit": 20,
    },
)
# status=ok — 해당 사이트 고유 공고만. total_matched 는 목록 길이(count)가 아니라 전체 건수.
```

한글·약칭은 alias로 표준 직무에 매핑됩니다.

```python
await client.call_tool("search_job_postings", {"job_function": "백엔드 개발자"})
# status=ok — Backend Engineer 로 해석
```

taxonomy에 없고 alias/오타 보정도 실패하면 안내합니다.

```python
await client.call_tool("search_job_postings", {"job_function": "not-a-real-role-xyz"})
# status=unknown_param, results=[], available_job_functions=[...]
# message에 Did you mean 후보가 붙을 수 있음
```

---

## 2. `get_skill_trend`

특정 직무 공고의 `skills[].canonical_name` 빈도를 집계합니다 (`raw_text` 미사용).  
공고당 동일 스킬은 1회만 카운트합니다.

### 파라미터

| 이름 | 타입 | 기본값 | 필수 | 설명 |
|------|------|--------|------|------|
| `job_function` | `str` | — | **예** | taxonomy 직무명 |
| `top_n` | `int` | `15` | 아니오 | 1~50 |
| `active_only` | `bool` | `True` | 아니오 | ACTIVE만 |
| `source_name` | `str \| None` | `None` | 아니오 | 수집 사이트 필터 |

### 반환

```json
{
  "status": "ok",
  "message": null,
  "job_function": "Backend Engineer",
  "posting_count": 189,
  "skills": [
    {"skill": "Java", "count": 89},
    {"skill": "AWS", "count": 66}
  ]
}
```

### 호출 예시 (실측)

```python
await client.call_tool(
    "get_skill_trend",
    {"job_function": "Backend Engineer", "top_n": 10},
)
```

상위 스킬 예: Java 89, AWS 66, MySQL 44, Python 40, Docker 38 …

---

## 3. `get_posting_count_by_category`

taxonomy 직군 **15개 전체**를 기준으로 건수를 반환합니다. 0건 직군도 포함합니다.

### 파라미터

| 이름 | 타입 | 기본값 | 필수 | 설명 |
|------|------|--------|------|------|
| `active_only` | `bool` | `True` | 아니오 | ACTIVE만 |
| `source_name` | `str \| None` | `None` | 아니오 | 수집 사이트 필터 |

### 반환

```json
{
  "status": "ok",
  "message": null,
  "total_postings": 659,
  "uncategorized_count": 78,
  "categories": [
    {"category": "Engineering & Technology", "count": 567},
    {"category": "Education & Training", "count": 0}
  ]
}
```

`uncategorized_count`: taxonomy에 없는(또는 빈) `job_category_name` 건수.

### 호출 예시

```python
await client.call_tool("get_posting_count_by_category", {})
```

---

## 4. `get_salary_summary`

조건에 맞는 공고 중 `salary.min_amount` / `max_amount`가 있는 건만으로
최소·최대·평균을 계산합니다. **통화·pay_period가 섞이면 그룹별로 분리**하며
환율 변환은 하지 않습니다.

신뢰도 필드:

| 필드 | 의미 |
|------|------|
| `matched_postings` | 필터에 걸린 공고 수 |
| `salary_data_count` | **전체** 숫자 급여 표본 수 (권위 있는 건수 — 자연어 요약 시 이 값을 쓸 것) |
| `summaries[*].group_sample_count` | 통화·`pay_period` **그룹별** 표본 수 (합 = `salary_data_count`) |

숫자 급여가 없으면 예외 대신 `status: "no_salary_data"`.  
`ok`일 때 `message`에 `salary_data_count`와 그룹 분할 안내가 포함됩니다
(같은 필드명을 최상위·그룹에 중복 쓰지 않아 LLM이 그룹 수치를 전체로 오인하지 않도록 함).

### 파라미터

| 이름 | 타입 | 기본값 | 필수 | 설명 |
|------|------|--------|------|------|
| `job_function` | `str \| None` | `None` | 아니오 | taxonomy 직무명 |
| `location` | `str \| None` | `None` | 아니오 | city/region/country/raw_text 부분 일치 |
| `source_name` | `str \| None` | `None` | 아니오 | 수집 사이트 필터 |

### 반환

```json
{
  "status": "ok",
  "message": "salary_data_count=9 posting(s) have numeric salary (matched_postings=102). Stats are split by currency/pay_period: KRW/ANNUAL=7, KRW/UNKNOWN=2. Use salary_data_count for the overall count; do not treat a single group's group_sample_count as the total.",
  "matched_postings": 102,
  "salary_data_count": 9,
  "job_function": "Backend Engineer",
  "location": "서울",
  "summaries": [
    {
      "currency_code": "KRW",
      "pay_period": "ANNUAL",
      "group_sample_count": 7,
      "min": 30000000,
      "max": 75010000,
      "avg": 44002857.14
    },
    {
      "currency_code": "KRW",
      "pay_period": "UNKNOWN",
      "group_sample_count": 2,
      "min": 6000,
      "max": 6000,
      "avg": 6000
    }
  ]
}
```

`avg`는 각 공고의 mid((min+max)/2, 한쪽만 있으면 그 값)의 평균입니다.

---

## 5. `get_company_hiring_activity`

`company.name`(정규화 값) 기준으로 ACTIVE 공고의 직무·지역 분포와 대표 공고를 반환합니다.
대소문자·공백 차이는 관대하게 맞춥니다. 정확 일치가 없으면 `unknown_company` + 후보 제안
(부분문자열 우선 + `difflib.get_close_matches`, cutoff **0.75**).

### 파라미터

| 이름 | 타입 | 기본값 | 필수 | 설명 |
|------|------|--------|------|------|
| `company_name` | `str` | — | **예** | 회사명 (`company.name`) |
| `limit` | `int` | `20` | 아니오 | 대표 공고 수 (1~100) |
| `source_name` | `str \| None` | `None` | 아니오 | 수집 사이트 필터 |

### 반환

```json
{
  "status": "ok",
  "message": null,
  "company_name": "SpaceX",
  "matched_postings": 28,
  "job_function_counts": [{"job_function": "Backend Engineer", "count": 4}],
  "location_counts": [{"location": "Hawthorne", "count": 10}],
  "postings": [
    {
      "title": "...",
      "job_function": "...",
      "location": "...",
      "posted_at": "2026-08-01"
    }
  ]
}
```

---

## 모니터링

`server.py`의 5개 tool은 `@monitor_tool`로 감쌉니다. 기존 tool 로직은 그대로이고, 호출마다 JSONL 한 줄을 남깁니다.

기록: 시각, tool 이름, 파라미터, 소요 ms, 결과 건수, `status`, 에러, `unknown_param`/`empty` 여부.

- 기본 경로: `logs/mcp_tool_calls_YYYYMMDD.jsonl`
- 덮어쓰기: 환경변수 `MCP_MONITOR_LOG`
- stdout은 MCP stdio용이므로 요약은 stderr. `MCP_MONITOR_QUIET=1`이면 요약 생략
- 실사용 패턴 시뮬레이션: `PYTHONPATH=. python scripts/simulate_mcp_queries.py`
- 튜닝 전후 비교: `PYTHONPATH=. python scripts/compare_mcp_tuning.py`

코드: `src/mcp_server/monitoring.py`

---

## 전송 방식 (transport)

연결 절차(Desktop / 웹 커넥터)는 [mcp_connection_guide.md](mcp_connection_guide.md)를 보세요. 여기 표는 실행 옵션 요약입니다.

| 방식 | 실행 | 비고 |
|------|------|------|
| stdio (기본) | `python -m src.mcp_server.server` | Cursor / Claude Desktop / `mcp dev` |
| Streamable HTTP | `python -m src.mcp_server.server --transport streamable-http --port 8000` | `http://127.0.0.1:8000/mcp` |

- CLI: `--transport`, `--host`, `--port`, `--path`, `--allowed-host` (`src/mcp_server/run.py`)
- 환경변수: `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `MCP_PATH`, `MCP_ALLOWED_HOSTS`
- HTTP 기본 host는 **`127.0.0.1`**. `0.0.0.0` 바인딩은 거부.
- ngrok 등 터널로 붙일 때는 SDK DNS-rebinding 보호 때문에 allowlist가 필요하다.
  - **서버를 실행할 때마다** `*.ngrok-free.dev`를 함께 넘겨야 한다.
    기본 설정에 ngrok 와일드카드가 들어 있지 않으며, `export`는 그 터미널 세션에만 남는다.
  - **왜 와일드카드인가:** ngrok **무료 플랜**은 터널을 재시작할 때마다
    `xxxx.ngrok-free.dev` 서브도메인이 바뀐다. 정확한 호스트를 매번 다시 넣기보다
    `*.ngrok-free.dev`로 두면 서브도메인이 바뀌어도 Host **421**을 피할 수 있다
    (SDK 기본은 포트 `:*`만 지원 → 우리 쪽에서 DNS `*.domain` 매칭을 보강).

```bash
# 권장: 실행 한 줄에 allowlist 포함 (매번 이렇게)
MCP_ALLOWED_HOSTS='*.ngrok-free.dev' \
  python -m src.mcp_server.server --transport streamable-http --port 8000

# 또는 CLI 인자 (역시 실행할 때마다)
python -m src.mcp_server.server --transport streamable-http --port 8000 \
  --allowed-host '*.ngrok-free.dev'

# export 는 선택 — 같은 터미널에서 여러 번 띄울 때만 편함 (새 터미널이면 다시 필요)
export MCP_ALLOWED_HOSTS="*.ngrok-free.dev"
python -m src.mcp_server.server --transport streamable-http --port 8000
```

- 원격 확인이 필요하면 **임시 터널**을 쓰고, 테스트 후 터널·서버를 종료할 것.
- 정식 OAuth/인증은 미구현 (가능성 확인용 no-auth).

---

## 로컬 테스트

단계별 설치·Desktop/웹 등록은 [mcp_connection_guide.md](mcp_connection_guide.md)가 기준입니다. 아래는 tool 개발용 짧은 재확인입니다.

### `PYTHONPATH` / `src` 모듈 해석 (필독)

이 프로젝트는 `src/` 레이아웃이고 **pip로 설치되는 패키지가 아닙니다**
(`pyproject.toml` / `setup.py` 없음). 그래서 Python이 프로젝트 루트를
모듈 검색 경로에 넣지 않으면 `from src...` import가 실패합니다.

실제로 확인된 실패:

| 상황 | 증상 |
|------|------|
| `mcp dev src/mcp_server/server.py` (PYTHONPATH 없음) | `ModuleNotFoundError: No module named 'src'` |
| Claude Desktop 등에서 `command`/`args`/`cwd`만 넣고 `env.PYTHONPATH` 없음 | 동일 (`cwd`가 호스트에서 무시·미적용되면 `-m src...`도 실패) |

대응:

1. **터미널 / Inspector** — 프로젝트 루트에서 `PYTHONPATH=.`를 앞에 붙인다.
2. **외부 앱(MCP 설정 JSON)** — `cwd`와 함께 `env.PYTHONPATH`에 **프로젝트 루트 절대 경로**를 넣는다.
3. (장기) editable install용 `pyproject.toml` 추가 — [HANDOFF.md](HANDOFF.md) 「알려두면 좋은 개선사항」 참고. 현재는 문서·환경변수로 우회.

### 1) 스크립트 (가장 빠름)

```bash
# 프로젝트 루트에서 (보통 PYTHONPATH 불필요 — 스크립트가 sys.path를 보정)
python scripts/demo_mcp_tools.py
```

### 2) 유닛 테스트

```bash
pytest tests/test_mcp_server.py -v
```

### 3) MCP Inspector

```bash
# PYTHONPATH를 반드시 지정해야 함 (안 하면 ModuleNotFoundError: No module named 'src')
# mcp dev는 파일을 스크립트로 띄우므로, 프로젝트 루트가 sys.path에 자동으로 안 들어감
PYTHONPATH=. mcp dev src/mcp_server/server.py
```

`npx`가 PATH에 있어야 합니다. Inspector UI에서 Tools 탭으로 각 tool을 호출합니다.

### 4) Cursor / Claude Desktop

stdio로 서버를 띄웁니다. **프로젝트 루트**에서:

```bash
python -m src.mcp_server.server
```

외부 앱 설정에는 `cwd`만 믿지 말고 **`env.PYTHONPATH`를 반드시** 넣으세요.
(Claude Desktop에서 `cwd`만으로는 `src`를 못 찾는 사례가 확인됨.)

macOS Claude Desktop 설정 파일:
`~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "job-trend-mcp": {
      "command": "/ABS/PATH/to/job-trend-mcp/.venv/bin/python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/ABS/PATH/to/job-trend-mcp",
      "env": {
        "PYTHONPATH": "/ABS/PATH/to/job-trend-mcp"
      }
    }
  }
}
```

Cursor (`~/.cursor/mcp.json` 또는 프로젝트 MCP 설정)도 동일 패턴입니다.

설정 저장 후 Claude Desktop은 **완전 종료(Quit) 후 재실행**해야 MCP가 다시 붙습니다.

### 5) Claude Desktop 실연결 검증 (완료 — 1안 로컬 stdio)

Inspector뿐 아니라 **Claude Desktop에 `job-trend-mcp`를 등록한 뒤**
자연어로 tool 5개를 호출해 검증했습니다 (2026-08-11, `env.PYTHONPATH` 포함 설정).

| 질문 | 호출된 tool | 결과 요약 |
|------|-------------|-----------|
| 백엔드 개발자 채용공고 검색 | `search_job_postings` | Backend Engineer 189건 등 — 성공 |
| 백엔드 요구 기술스택 | `get_skill_trend` | Java 89, AWS, MySQL… — 성공 |
| 직군별 채용공고 수 | `get_posting_count_by_category` | 전체 1155, Eng&Tech 567 — 성공 |
| 서울 백엔드 급여 | `get_salary_summary` | 매칭 102 / `salary_data_count` 9 — 성공 |
| SpaceX 채용 현황 | `get_company_hiring_activity` | 28건, SE·FSE 위주 — 성공 |

자연어 스모크 예: 「Backend Engineer 스킬 트렌드 알려줘」 → `get_skill_trend` 호출.

### 6) Claude 웹 커스텀 커넥터 검증 (완료 — 2안 Streamable HTTP + ngrok)

Streamable HTTP + ngrok 터널로 **Claude 웹 커스텀 커넥터**에 연결해
tool 호출까지 검증 완료했습니다. 연결 시 트러블슈팅은 [HANDOFF.md](HANDOFF.md)
「Claude 웹 커스텀 커넥터 — OAuth 404는 정상, 421이 진짜 문제」를 참고하세요.

**최종 상태:** 1안(로컬 stdio · Claude Desktop) · 2안(웹 · Claude 커스텀 커넥터)
둘 다 실제 제품 연결까지 검증됨.

---

## 관련 코드

- `src/mcp_server/data_loader.py` — 로드·인덱스·직무명 resolve (alias·오타 보정)
- `src/mcp_server/monitoring.py` — tool 호출 JSONL 로그
- `src/taxonomy/job_functions.py` / `job_categories.py` — 허용값
- `src/storage/json_writer.py` — 디스크 레이아웃 (새/레거시 경로 모두 로드)
