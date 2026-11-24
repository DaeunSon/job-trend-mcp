# MCP 서버 연결 가이드

로컬 설치부터 Claude Desktop(stdio)·Claude 웹 커스텀 커넥터(HTTP + ngrok)까지입니다.  
tool 스펙·응답 예시는 [mcp_server.md](mcp_server.md)를 보세요.

작성 기준: 2026-08-14. **두 경로 모두 실연결·tool 호출 검증 완료.**

---

## 무엇을 고를지

| 경로 | 언제 | 전송 |
|------|------|------|
| **A. 로컬 (Claude Desktop / Cursor)** | 본인 PC에서 Claude·Cursor로 쓸 때 | stdio |
| **B. 웹 (Claude 커스텀 커넥터)** | 브라우저 Claude에서 쓸 때 | Streamable HTTP + ngrok |

공통: 프로젝트 루트에 venv를 만들고 한 번 설치합니다. `PYTHONPATH`는 필요 없습니다.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

---

## 0. 공통 설치 (로컬·웹 모두)

필요: **Python 3.10+**, git. 웹 연결이면 **ngrok**도 필요합니다.

```bash
cd /ABS/PATH/to/job-trend-mcp

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

필수 `.env`는 없습니다. MCP 조회만 하면 Playwright / `curl_cffi`는 필요 없습니다.

데이터가 `data/job_postings/`에 있어야 tool이 공고를 반환합니다. 비어 있으면 서버는 뜨지만 검색 결과가 비습니다.

설치가 됐는지 확인:

```bash
python scripts/demo_mcp_tools.py
```

5개 tool이 in-memory로 호출됩니다. 여기서 막히면 Desktop/웹 등록 전에 고칩니다.

---

## A. 로컬 연결 — Claude Desktop

stdio로 이 PC의 Python이 MCP 서버를 띄웁니다.

### A-1. 설정 파일

macOS:

`~/Library/Application Support/Claude/claude_desktop_config.json`

아래를 넣습니다. **경로 네 곳**을 본인 머신 절대 경로로 바꿉니다.

```json
{
  "mcpServers": {
    "job-trend-mcp": {
      "command": "/ABS/PATH/to/job-trend-mcp/.venv/bin/python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/ABS/PATH/to/job-trend-mcp"
    }
  }
}
```

| 키 | 왜 필요한지 |
|----|-------------|
| `command` | 시스템 Python이 아니라 **이 프로젝트 venv**의 python |
| `args` | stdio 기본 실행 (`--transport` 생략 = stdio) |
| `cwd` | 프로젝트 루트. `data/` 로드 기준 |

Cursor도 같은 JSON 패턴입니다 (`~/.cursor/mcp.json` 또는 프로젝트 MCP 설정).

시스템 Python을 `command`에 넣지 마세요. `mcp` 패키지가 없는 인터프리터면 바로 실패합니다.

### A-2. Claude Desktop 재시작

설정을 저장한 뒤 Claude Desktop을 **완전 종료(Quit) 후 다시 실행**합니다.  
창만 닫으면 MCP 설정이 다시 안 읽히는 경우가 있습니다.

### A-3. 확인

1. Claude Desktop 설정에서 `job-trend-mcp`가 연결되어 있는지 봅니다.
2. 새 대화에서 아래처럼 물어봅니다. 기대 tool이 호출되면 성공입니다.

| 질문 예 | 기대 tool |
|---------|-----------|
| 백엔드 개발자 채용공고 검색해줘 | `search_job_postings` |
| 백엔드에 많이 나오는 기술스택 | `get_skill_trend` |
| 직군별 채용공고 수 | `get_posting_count_by_category` |
| 서울 백엔드 급여 요약 | `get_salary_summary` |
| SpaceX 채용 현황 | `get_company_hiring_activity` |

### A-4. Inspector로만 보고 싶을 때

Desktop 없이 tool UI만 띄울 때:

```bash
cd /ABS/PATH/to/job-trend-mcp
source .venv/bin/activate
mcp dev src/mcp_server/server.py
```

`npx`가 PATH에 있어야 합니다. `pip install -e ".[dev]"`를 마친 venv여야 합니다.

---

## B. 웹 연결 — Claude 커스텀 커넥터

로컬 HTTP 서버를 ngrok으로 노출해, 브라우저 Claude에 커스텀 커넥터로 붙입니다.

보안: HTTP는 **`127.0.0.1`만** 듣습니다. `0.0.0.0` 바인딩은 코드에서 거부합니다.  
외부 노출은 터널로만 하고, 테스트가 끝나면 서버와 ngrok을 종료하세요.  
정식 OAuth는 없습니다 (무인증 MCP — 가능성 확인용).

### B-1. MCP HTTP 서버

**터미널 1** — 프로젝트 루트, venv 활성화 후:

```bash
cd /ABS/PATH/to/job-trend-mcp
source .venv/bin/activate

MCP_ALLOWED_HOSTS='*.ngrok-free.dev' \
  python -m src.mcp_server.server --transport streamable-http --port 8000
```

동일:

```bash
python -m src.mcp_server.server \
  --transport streamable-http --port 8000 \
  --allowed-host '*.ngrok-free.dev'
```

정상 기동 시 stderr에 비슷한 줄이 나옵니다.

```text
Streamable HTTP listening on http://127.0.0.1:8000/mcp
```

`MCP_ALLOWED_HOSTS` / `--allowed-host`는 **서버를 띄울 때마다** 넣습니다.  
기본값에 ngrok 와일드카드가 없고, `export`는 그 터미널 세션에만 남습니다.

와일드카드(`*.ngrok-free.dev`)를 쓰는 이유: ngrok **무료 플랜**은 터널을 다시 켤 때마다 서브도메인이 바뀝니다. 정확한 호스트를 매번 고치지 않아도 Host **421**을 피할 수 있습니다.

### B-2. ngrok 터널

**터미널 2:**

```bash
ngrok http 8000
```

표시되는 HTTPS 주소를 복사합니다. 예: `https://abcd1234.ngrok-free.dev`

Claude에 넣을 URL은 **뒤에 `/mcp`를 붙인 것**입니다.

```text
https://abcd1234.ngrok-free.dev/mcp
```

### B-3. Claude 웹에 커넥터 등록

1. [Claude](https://claude.ai) 에 로그인합니다.
2. 설정 → 커넥터(Connectors) → 커스텀 커넥터 추가로 갑니다.  
   (메뉴 이름은 Claude 웹 UI 개편에 따라 조금 다를 수 있습니다.)
3. 원격 MCP URL에 `https://<ngrok-host>/mcp` 를 넣습니다.
4. 저장한 뒤 새 대화에서 커넥터를 켭니다.
5. A-3과 같은 질문으로 tool 호출을 확인합니다.

### B-4. 연결 직후 로그에서 헷갈리는 것

브라우저/네트워크에 **먼저 404가 나와도 실패가 아닙니다.**

| 요청 | 흔한 응답 | 의미 |
|------|-----------|------|
| `/.well-known/oauth-protected-resource` 등 | 404 | OAuth 미구현 (의도적) |
| `/register` | 404 | 동적 클라이언트 등록 없음 |

Claude는 OAuth 메타가 없으면 **무인증 MCP로 폴백**합니다. 초반 404만으로 연결 실패로 보지 마세요.

진짜 장애는 그 다음입니다.

| 증상 | 원인 | 조치 |
|------|------|------|
| **421** Invalid Host | Host 헤더가 allowlist 밖 | 서버를 `MCP_ALLOWED_HOSTS='*.ngrok-free.dev'`와 함께 **다시** 실행 |
| 타임아웃 / 끊김 | 로컬 서버 또는 ngrok 미기동 | 터미널 1·2 재기동 후, **새 ngrok URL**로 커넥터를 갱신 |
| tool은 보이는데 공고가 없음 | `data/job_postings/` 비어 있음 | 프로젝트 루트에서 서버를 띄웠는지, JSON이 있는지 확인 |
| `No module named 'src'` | 패키지 미설치 | venv에서 `pip install -e ".[dev]"` |

터널을 끄고 다시 켜면 ngrok 주소가 바뀝니다. 커넥터 URL을 새 주소 + `/mcp`로 바꿔야 합니다.

테스트가 끝나면 **터미널 1(서버)과 터미널 2(ngrok)를 종료**하세요.

---

## 자주 막히는 지점

### `ModuleNotFoundError: No module named 'src'`

패키지가 설치되지 않은 python 입니다.

- 프로젝트 venv에서 `pip install -e ".[dev]"`를 한 번 실행합니다.
- Claude Desktop / Cursor: `command`가 그 venv의 python인지 확인합니다.

### Desktop에서 서버가 안 붙음

1. Claude를 Quit 후 재실행했는지
2. `command`가 `.venv/bin/python` 절대 경로인지 (`which python`이 아닌 venv)
3. JSON 콤마·따옴표가 깨지지 않았는지
4. `logs/mcp_tool_calls_YYYYMMDD.jsonl` 이 생기는지 (호출이 들어오면 생김)

### 웹에서 421

allowlist 없이 HTTP 서버를 띄운 상태입니다. B-1 명령 그대로 서버를 다시 켭니다.  
ngrok만 재시작한 것으로는 421이 해소되지 않습니다.

### HTTP를 `0.0.0.0`으로 열고 싶다

거부됩니다. `127.0.0.1` + ngrok만 사용합니다 (`src/mcp_server/run.py`).

---

## 환경 변수·CLI 요약

| 항목 | 기본 | 설명 |
|------|------|------|
| (생략) / `--transport stdio` | stdio | Desktop / Cursor |
| `--transport streamable-http` | — | 웹 커넥터용 |
| `--host` / `MCP_HOST` | `127.0.0.1` | `0.0.0.0` 거부 |
| `--port` / `MCP_PORT` | `8000` | |
| `--path` / `MCP_PATH` | `/mcp` | 커넥터 URL 경로 |
| `--allowed-host` / `MCP_ALLOWED_HOSTS` | 없음 | 웹 연결 시 `*.ngrok-free.dev` **매번** 지정 |

관련 코드: `src/mcp_server/run.py`, `src/mcp_server/server.py`.
