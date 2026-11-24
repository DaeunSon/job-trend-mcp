# 축소 MVP (PostgreSQL 전환 · 검색 API · 수동 배포) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** JSON 메모리 조회로 돌던 MCP tool 5개를 PostgreSQL 조회로 옮기고, 검색 REST API 1개와 함께 HTTPS 공개 도메인의 EC2 1대에 손으로 배포한다.

**Architecture:** 정규화된 공고 JSON을 `postings` · `posting_skills` · `posting_observations` 세 테이블에 멱등 upsert한다. MCP tool과 FastAPI는 같은 `src/db/queries.py`를 쓴다. 기존 메모리 경로(`store=` 인자)는 지우지 않고 남겨, 수집 쪽 스크립트(품질 게이트 · 실험)가 DB 없이 계속 돌게 하고 SQL 결과를 검증하는 기준(parity)으로 쓴다. 서버는 Nginx(TLS · IP별 요청 제한) 뒤에 systemd 서비스 2개(API 8001, MCP 8000)와 로컬 PostgreSQL을 둔다.

**Tech Stack:** Python 3.12+, PostgreSQL 16, psycopg 3 (`psycopg[binary,pool]`, ORM 없음), 번호 붙인 SQL 파일 + 작은 마이그레이션 실행기, FastAPI + uvicorn, mcp SDK v2, pytest, Nginx, certbot, systemd, Ubuntu 24.04 (ARM).

**Spec:** `docs/superpowers/specs/2026-11-21-job-trend-platform-design.md` (§6 1-1 · 1-4, §12.2 ~ §12.4)

**작업 브랜치:** `mvp-db-api` (`main` d0c7053 에서 분기). merge · push · 배포는 사람이 한다.

## 범위

| 과제 | 태스크 | 마감 |
|---|---|---|
| #13 | Task 1 | 11/24 |
| #14 | Task 2, 3 | 11/25 |
| #15 | Task 4, 5 | 11/26 |
| #17 (코드) | Task 6 | 11/27 |
| #16, #17 (배포) | Task 7 | 11/27 |
| #18 | Task 8 | 11/27 |

**이번 계획에서 뺀 것 (설계 §12.2 표에는 있음):** 수집 업로드 엔드포인트와 `collect.yml` 연결, Docker Compose 배포, 이미지 빌드 · 자동 배포, S3 백업, 외부 가동 감시, LLM 보강(2단계 축소판). 그래서 배포 직후 DB에는 8월 스냅샷 659건만 있고 매일 갱신되지 않는다. README에 그대로 적는다(Task 8).

**설계 문서와 다르게 정한 것 3가지**

1. **재정규화 범위 (§12.3).** 스냅샷에 원문(`raw_job_postings`)이 59개뿐이라(공고 파일 516개) 사이트 파서를 다시 돌릴 수 없다. 스킬만 다시 정리하고(노이즈 제거 · 표준 이름 재조회), 직무는 현재 taxonomy에 없는 값만 빈 값으로 바꾼다.
2. **테스트 전환 (§6 1-4).** `tests/test_mcp_server.py`의 JSON fixture 테스트 52개는 DB fixture로 바꾸지 않고 그대로 둔다. 같은 시나리오를 DB로 도는 테스트와, 두 경로의 결과가 같은지 보는 parity 테스트를 새로 더한다.
3. **집계 위치.** 필터 · 정렬 · 페이지 · 건수 · 스킬/직군 집계는 SQL로 한다. 급여 그룹 통계와 회사별 분포는 SQL이 걸러 준 행을 기존 파이썬 코드로 계산한다(통화 · 기간을 섞지 않는 규칙과 반올림을 그대로 지키기 위해).

## Global Constraints

- 기존 테스트가 깨지면 안 된다. 기준선 `N0` = Task 1에서 잰 `pytest tests -q` 통과 수(설계 문서 기준 1,108). 이후 모든 태스크는 `passed ≥ N0`, `failed 0`, `skipped 0`.
- MCP tool 이름 5개와 파라미터는 `tests/test_mcp_tool_contract.py`의 `EXPECTED` 그대로다. 이 파일은 고치지 않는다.
- `evals/`, `scripts/collect_all.py`, `scripts/quality_gate.py`, `src/crawlers/**`, `src/mcp_server/data_loader.py`는 고치지 않는다(다른 클론에 커밋 안 된 변경이 있어 충돌을 피한다. Task 4의 `server.py` import 한 줄 삭제는 예외).
- import 경로는 `src.…` 그대로다. 패키지 이름을 바꾸지 않는다.
- 공고 식별 키는 `(source_name, source_job_id)`. 필드 이름 `first_collected_at` / `last_seen_at`은 `src/models/schemas.py`와 같게 쓴다.
- 스냅샷 적재 표시는 `ingest_source = 'backfill:20260803'`. 적재 결과는 공고 659건, 관측 1,155건이고 다시 돌려도 같다.
- 적재는 `crawl_status`를 바꾸지 않는다(보이지 않는다고 마감 처리하지 않는다).
- 공개 응답(REST · MCP)에 공고 본문(`description`)을 넣지 않는다. 요약 필드와 `original_url`만.
- PostgreSQL 포트(5432)는 외부에 열지 않는다. 앱 서버는 `127.0.0.1`에만 바인딩한다(`run.py`가 `0.0.0.0`을 거부하는 동작 유지).
- 공개 MCP는 인증 없는 읽기 전용이고 IP별 요청 제한을 Nginx에서 건다.
- 비밀값(DB 비밀번호 등)은 저장소에 넣지 않는다. 서버에서는 `/etc/job-trend/env`(권한 600).
- EC2는 서울 리전 t4g.small, gp3 20GB. AWS 예산 알림은 2만 원 · 3만 원 두 단계.
- 커밋 메시지는 기존처럼 한국어 문장으로 쓴다(예: `PostgreSQL 스키마와 마이그레이션 실행기를 추가한다`).

## Review Focus

1. 적재를 두 번 돌리거나 중간에 끊긴 뒤 다시 돌려도 659 / 1,155가 그대로다 → Task 3 `test_ingest_twice_is_idempotent`, `test_failed_run_leaves_no_partial_rows`.
2. 같은 공고의 옛 레코드가 새 레코드보다 나중에 들어와도 내용이 옛것으로 덮이지 않는다 → Task 3 `test_older_record_does_not_overwrite_newer`.
3. 지역 · 키워드 입력에 `%`, `_`, `'`가 들어와도 글자 그대로 찾고 SQL 오류가 나지 않는다 → Task 4 `test_location_special_chars_are_literal`, Task 6 `test_keyword_special_chars_are_literal`.
4. DB가 꺼져 있거나 `DATABASE_URL`이 없어도 MCP 서버 모듈 import는 성공하고(stdio 호스트가 import하므로), tool 호출은 원인을 말하는 오류를 내며, `/healthz`는 503이다 → Task 4 `test_server_imports_without_database`, `test_tool_raises_database_unavailable`, Task 6 `test_healthz_503_when_db_down`.
5. 직무가 빈 공고(스냅샷 레코드의 375건)와 현재 설정에 없는 사이트 `indeed`(53건)가 빠지지 않고 전체 · 미분류 건수에 들어간다 → Task 3 `test_unknown_source_and_empty_function_are_kept`, Task 4 `test_category_counts_include_uncategorized`.

추가 안전장치: 테스트는 DB 이름이 `_test`로 끝나지 않으면 시작하지 않는다 → Task 2 `test_refuses_non_test_database`.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `pyproject.toml` (새로) | 패키지 메타 · 의존성 · pytest 설정 |
| `requirements.txt` (수정) | `-e .[dev]` 한 줄 |
| `docker-compose.dev.yml` (새로) | 로컬 개발 · 테스트용 PostgreSQL 16만 |
| `src/db/connection.py` (새로) | `DATABASE_URL` 읽기, 연결 풀, `DatabaseUnavailable` |
| `src/db/migrate.py` + `src/db/migrations/0001_init.sql` (새로) | 스키마와 적용 기록 |
| `src/db/ingest.py` (새로) | 문서 → 행 변환, 멱등 upsert |
| `src/db/renormalize.py` (새로) | 스냅샷 문서의 스킬 · 직무 재정리 |
| `src/db/queries.py` (새로) | tool · API가 같이 쓰는 SQL |
| `scripts/backfill_snapshot.py` (새로) | 스냅샷 tar → DB |
| `scripts/check_sql_parity.py` (새로) | 스냅샷 전체로 메모리 경로와 SQL 경로 비교 |
| `src/mcp_server/tools/*.py` (수정) | `store` 없으면 SQL 경로 |
| `src/mcp_server/server.py` (수정) | import 시점의 `get_store()` 삭제 |
| `src/api/app.py` (새로) | FastAPI: `/healthz`, `/api/v1/postings` |
| `scripts/measure_api_latency.py` (새로) | p50 · p95 측정 |
| `deploy/nginx/job-trend.conf`, `deploy/systemd/*.service`, `deploy/env.example` (새로) | 서버 설정 원본 |
| `docs/deploy/manual-ec2.md`, `docs/deploy/manual-pain-log.md` (새로) | 수동 구축 절차 · 불편 기록 |
| `docs/metrics/phase1.md` (새로) | 1단계 수치 |
| `tests/conftest.py` (새로) | DB fixture, `sample_store` 공유 |

---

### Task 1: `pyproject.toml` · editable install (#13)

**Files:**
- Create: `pyproject.toml`, `tests/test_packaging.py`
- Modify: `requirements.txt`, `.gitignore`, `.github/workflows/ci.yml`(Install 단계), `README.md` · `docs/mcp_server.md`(`PYTHONPATH` 안내)

**Interfaces:**
- Produces: `pip install -e ".[dev]"` 로 어디서든 `import src.…`, `import evals` 가능. 이후 태스크는 `PYTHONPATH` 없이 `.venv/bin/python` 을 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_packaging.py`

```python
def test_import_without_pythonpath(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, "-c", "import src.mcp_server.run, src.normalization, evals"],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
```

- [ ] **Step 2: 환경 준비와 실패 확인** — 지금 `.venv`에는 의존성이 없다.

Run: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest tests/test_packaging.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'src'`)

- [ ] **Step 3: `pyproject.toml` 작성**
  - `[build-system]` setuptools ≥ 68. `[project]` name `job-trend-mcp`, version `0.2.0`, `requires-python = ">=3.12"`.
  - `dependencies`: 지금 `requirements.txt`의 실행 의존성 전부(같은 하한) + `psycopg[binary,pool]>=3.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.30`.
  - `[project.optional-dependencies] dev`: `pytest>=8.0.0`, `pytest-mock>=3.12.0`, `pytest-cov`, `httpx>=0.27`.
  - `[tool.setuptools.packages.find]` `include = ["src*", "evals*"]`. `[tool.setuptools.package-data]` `"src.db" = ["migrations/*.sql"]`, `"src.config" = ["*.json"]`, `"evals" = ["*.json", "prompts/*.md"]`.
  - `[tool.pytest.ini_options]` `testpaths = ["tests"]`.
  - `requirements.txt`는 `-e .[dev]` 한 줄로 바꾼다. CI Install 단계는 `pip install -e ".[dev]"`.
  - `.gitignore`에 `data/data-archive/`, `.superpowers/` 추가.

- [ ] **Step 4: 통과 확인과 기준선 기록**

Run: `.venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest tests -q`
Expected: 전부 통과. 마지막 줄의 통과 수에서 1을 뺀 값이 `N0`. 보고서에 적는다. 1,108과 다르면 숫자만 적고 계속한다.

- [ ] **Step 5: 문서의 `PYTHONPATH=.` 안내를 `pip install -e ".[dev]"` 한 번으로 바꾼다** (`README.md`, `docs/mcp_server.md`의 설치 · 실행 절, Claude Desktop 설정 예시의 `env.PYTHONPATH`). `docs/HANDOFF.md`는 과거 기록이라 그대로 둔다.

- [ ] **Step 6: Commit** — `pyproject.toml 을 추가해 PYTHONPATH 없이 실행되게 한다`

---

### Task 2: DB 기반 — 연결 · 스키마 · 테스트 fixture (#14)

**Files:**
- Create: `docker-compose.dev.yml`, `src/db/__init__.py`, `src/db/connection.py`, `src/db/migrate.py`, `src/db/migrations/0001_init.sql`, `tests/conftest.py`, `tests/test_db_migrate.py`
- Modify: `.github/workflows/ci.yml`, `tests/test_mcp_server.py`(`sample_store` fixture를 conftest로 옮기기만)

**Interfaces:**
- Produces:
  - `src.db.connection`: `class DatabaseUnavailable(RuntimeError)`, `get_database_url() -> str`(없으면 `DatabaseUnavailable("DATABASE_URL is not set")`), `connection() -> ContextManager[psycopg.Connection]`(풀에서 빌림, `row_factory=dict_row`, 정상 종료 시 commit · 예외 시 rollback, 접속 실패는 `DatabaseUnavailable`, 접속 대기는 최대 3초), `reset_pool() -> None`.
  - `src.db.migrate`: `apply_migrations(conn) -> list[str]`(이번에 적용한 버전 이름), CLI `python -m src.db.migrate`.
  - `tests/conftest.py`: `db_conn`(테스트마다 트랜잭션을 열고 끝나면 rollback), `SAMPLE_DOCS`, `sample_store`.
- 로컬 DB: `docker compose -f docker-compose.dev.yml up -d` → `postgres:16`, 포트 `127.0.0.1:54329`, 사용자 · 비밀번호 `jobtrend`, DB `jobtrend_test`. `TEST_DATABASE_URL=postgresql://jobtrend:jobtrend@127.0.0.1:54329/jobtrend_test`.

**스키마 (`0001_init.sql`)** — 열 이름은 이후 태스크가 그대로 쓴다.

```sql
CREATE TABLE postings (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_name          text NOT NULL,
  source_job_id        text NOT NULL,
  doc_id               text,
  title                text NOT NULL DEFAULT '',
  normalized_title     text NOT NULL DEFAULT '',
  company_name         text,
  company_key          text NOT NULL DEFAULT '',
  job_function_name    text NOT NULL DEFAULT '',
  job_category_name    text NOT NULL DEFAULT '',
  employment_type_name text NOT NULL DEFAULT '',
  employment_type_norm text NOT NULL DEFAULT '',
  work_arrangement     text,
  city_name            text,
  location_blob        text NOT NULL DEFAULT '',
  salary_min           numeric,
  salary_max           numeric,
  currency_code        text,
  pay_period           text,
  crawl_status         text NOT NULL DEFAULT 'ACTIVE',
  posted_on            date,
  sort_key             text NOT NULL DEFAULT '',
  recrawl_key          text NOT NULL DEFAULT '',
  first_collected_at   timestamptz,
  last_seen_at         timestamptz,
  ingest_source        text NOT NULL,
  doc                  jsonb NOT NULL,
  updated_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_name, source_job_id)
);
CREATE INDEX postings_function_idx ON postings (job_function_name);
CREATE INDEX postings_category_idx ON postings (job_category_name);
CREATE INDEX postings_company_idx  ON postings (company_key);
CREATE INDEX postings_sort_idx     ON postings (sort_key DESC, id);

CREATE TABLE posting_skills (
  posting_id     bigint NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
  canonical_name text NOT NULL,
  PRIMARY KEY (posting_id, canonical_name)
);
CREATE INDEX posting_skills_name_idx ON posting_skills (canonical_name);

CREATE TABLE posting_observations (
  posting_id    bigint NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
  observed_on   date NOT NULL,
  ingest_source text NOT NULL,
  PRIMARY KEY (posting_id, observed_on)
);
CREATE INDEX posting_observations_date_idx ON posting_observations (observed_on);
```

`schema_migrations(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())`은 실행기가 만든다. 버전은 파일 이름(`0001_init`).

- [ ] **Step 1: 로컬 DB 띄우기** — Docker Desktop을 켠 뒤 `docker compose -f docker-compose.dev.yml up -d`.
Expected: `docker compose -f docker-compose.dev.yml ps` 에 `healthy`. Docker를 못 쓰면 멈추고 사람에게 알린다(대안: `brew install postgresql@16`).

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_db_migrate.py`

```python
def test_apply_creates_tables(db_conn):
    names = {r["table_name"] for r in db_conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert {"postings", "posting_skills", "posting_observations", "schema_migrations"} <= names

def test_apply_twice_applies_nothing(db_conn):
    assert apply_migrations(db_conn) == []

def test_unique_posting_key(db_conn):
    insert = ("INSERT INTO postings (source_name, source_job_id, ingest_source, doc) "
              "VALUES ('jumpit', '1', 't', '{}')")
    db_conn.execute(insert)
    with pytest.raises(psycopg.errors.UniqueViolation):
        db_conn.execute(insert)

def test_refuses_non_test_database(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:p@127.0.0.1:54329/jobtrend")
    with pytest.raises(RuntimeError, match="_test"):
        conftest.resolve_test_database_url()

def test_get_database_url_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(DatabaseUnavailable, match="DATABASE_URL is not set"):
        get_database_url()
```

- [ ] **Step 3: 실패 확인** — Run: `TEST_DATABASE_URL=… .venv/bin/python -m pytest tests/test_db_migrate.py -q` → FAIL (`No module named 'src.db'`)

- [ ] **Step 4: 구현**
  - `connection.py`, `migrate.py`, `0001_init.sql` 은 위 Interfaces · 스키마대로.
  - `tests/conftest.py`:
    - `resolve_test_database_url() -> str`: `TEST_DATABASE_URL`이 없으면 `RuntimeError("TEST_DATABASE_URL is not set …docker compose 명령 안내…")`, DB 이름이 `_test`로 끝나지 않으면 `RuntimeError`.
    - 세션 fixture(autouse): 위 URL을 `DATABASE_URL` 환경변수에도 넣고 `apply_migrations`를 한 번 실행 · commit 한다. 그래서 `Client(mcp)`로 도는 기존 계약 테스트는 빈 테스트 DB를 본다.
    - `db_conn`: 별도 연결, 테스트가 끝나면 rollback · close.
    - `tests/test_mcp_server.py`의 `sample_store` fixture와 문서 5개를 conftest로 옮기고 문서 목록을 `SAMPLE_DOCS`로 내보낸다. 각 문서에 `source_job_id`(= `id`), `created_at` · `first_collected_at` · `last_seen_at`(= `"2026-08-01T00:00:00+00:00"`)을 더한다. 테스트 본문은 고치지 않는다.
  - CI: `test` job에 `services.postgres`(`postgres:16`, `POSTGRES_USER/PASSWORD=jobtrend`, `POSTGRES_DB=jobtrend_test`, 포트 `5432:5432`, `pg_isready` health check)와 `env.TEST_DATABASE_URL=postgresql://jobtrend:jobtrend@127.0.0.1:5432/jobtrend_test`.

- [ ] **Step 5: 통과 확인** — Run: `TEST_DATABASE_URL=… .venv/bin/python -m pytest tests -q` → `passed ≥ N0 + 5`, failed 0, skipped 0

- [ ] **Step 6: Commit** — `PostgreSQL 스키마와 마이그레이션 실행기를 추가한다`

---

### Task 3: 멱등 적재와 스냅샷 backfill (#14)

**Files:**
- Create: `src/db/ingest.py`, `src/db/renormalize.py`, `scripts/backfill_snapshot.py`, `tests/test_db_ingest.py`, `tests/test_renormalize.py`

**Interfaces:**
- Consumes: `db_conn`, `SAMPLE_DOCS`, 스키마(Task 2). 기존 함수 `src.mcp_server.tools.search._location_blob`, `_norm_enum_token`, `src.mcp_server.tools.company_activity._norm_company_key`, `src.mcp_server.tools.salary_summary._parse_amount`, `src.mcp_server.data_loader._recrawl_sort_key`, `src.normalization.skill_noise_filter.is_skill_noise`, `src.taxonomy.skills.lookup_skill_canonical`, `src.taxonomy.job_functions.is_valid_function`.
- Produces:
  - `renormalize_doc(doc: dict) -> dict` (입력을 바꾸지 않고 새 dict 반환)
  - `@dataclass IngestResult: inserted: int; updated: int; unchanged: int; skipped: int; observations: int`
  - `upsert_posting(conn, doc: dict, *, ingest_source: str) -> Literal["inserted", "updated", "unchanged", "skipped"]`
  - `ingest_documents(conn, docs: Iterable[dict], *, ingest_source: str) -> IngestResult`
  - `delete_ingest_source(conn, ingest_source: str) -> int` (지운 공고 수)
  - CLI: `python scripts/backfill_snapshot.py --archive <tar.gz> [--ingest-source backfill:20260803] [--delete]`

**정한 규칙**
- 행 변환: `company_key`, `location_blob`, `employment_type_norm`, `salary_min/max`는 위 기존 함수로 계산한다(메모리 경로와 같은 값이 나오게). `sort_key` = `posted_at or last_seen_at or created_at`(문자열). `recrawl_key` = `_recrawl_sort_key(doc)`. `posted_on`은 `posted_at` 앞 10자를 날짜로 읽고, 안 읽히면 NULL. `crawl_status`가 비면 `'ACTIVE'`. `doc`에는 문서 전체를 넣는다.
- `source_name`이나 `source_job_id`가 비면 `skipped`.
- 새 공고: insert. 있는 공고: `first_collected_at = LEAST`, `last_seen_at = GREATEST`. 들어온 문서의 `recrawl_key`가 저장된 값 **이상**일 때만 내용 열 · `doc` · `posting_skills`를 바꾼다(`updated`), 아니면 `unchanged`. `ingest_source`는 처음 넣은 값을 유지한다.
- `posting_skills`: 문서 `skills[].canonical_name` 중 빈 값을 빼고 공고 안에서 중복 없이.
- 관측: `observed_on` = `created_at`의 UTC 날짜(없으면 `last_seen_at`). `ON CONFLICT DO NOTHING`. 새로 들어간 건수만 `observations`에 센다.
- `ingest_documents`는 호출자의 트랜잭션 안에서만 쓴다(직접 commit 하지 않는다). backfill 스크립트는 전체를 한 트랜잭션으로 넣는다.
- `delete_ingest_source`: 그 표시의 관측을 지우고, 관측이 하나도 안 남은 공고를 지운다.
- `renormalize_doc`: ① 스킬 — `is_skill_noise(raw_text)`면 버리고, `lookup_skill_canonical(raw_text)`가 값을 주면 그것으로, 없으면 기존 `canonical_name` 유지. ② `job_function_name`이 비어 있지 않은데 `is_valid_function`이 거짓이면 `job_function_name`과 `job_category_name`을 `""`로. 그 밖의 필드는 그대로.
- backfill 스크립트: tar를 임시 폴더에 풀고(`tarfile`의 `filter="data"`), `data/job_postings/**/*.json`의 레코드 전부(중복 제거 없이)를 `renormalize_doc` → `ingest_documents`. 끝나면 `IngestResult`와 DB의 `postings` · `posting_observations` 건수, `observed_on` 최소 · 최대를 한 줄씩 출력한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_db_ingest.py` — 헬퍼 `doc(**over)`(`SAMPLE_DOCS[0]`을 깊은 복사해 덮어씀)와 `count(conn, table)`(행 수)는 `tests/conftest.py`에 두고 이후 태스크의 테스트도 `from tests.conftest import doc, count`로 쓴다.

```python
def test_insert_maps_columns(db_conn):
    assert upsert_posting(db_conn, doc(), ingest_source="t") == "inserted"
    row = db_conn.execute("SELECT * FROM postings").fetchone()
    assert (row["company_key"], row["employment_type_norm"]) == ("acme", "fulltime")
    assert (row["salary_min"], row["salary_max"]) == (Decimal("60000000"), Decimal("80000000"))
    assert "서울" in row["location_blob"] and row["posted_on"] == date(2026, 8, 1)
    assert count(db_conn, "posting_skills") == 2 and count(db_conn, "posting_observations") == 1

def test_ingest_twice_is_idempotent(db_conn):
    first = ingest_documents(db_conn, SAMPLE_DOCS, ingest_source="t")
    second = ingest_documents(db_conn, SAMPLE_DOCS, ingest_source="t")
    assert (first.inserted, second.inserted, second.observations) == (5, 0, 0)
    assert count(db_conn, "postings") == 5 and count(db_conn, "posting_observations") == 5

def test_recrawl_adds_observation_and_widens_dates(db_conn):
    upsert_posting(db_conn, doc(), ingest_source="t")
    later = doc(title="A (recrawl)", created_at="2026-08-03T00:00:00+00:00",
                last_seen_at="2026-08-03T00:00:00+00:00")
    assert upsert_posting(db_conn, later, ingest_source="t") == "updated"
    row = db_conn.execute("SELECT * FROM postings").fetchone()
    assert row["title"] == "A (recrawl)"
    assert row["first_collected_at"].date() == date(2026, 8, 1)
    assert row["last_seen_at"].date() == date(2026, 8, 3)
    assert count(db_conn, "posting_observations") == 2

def test_older_record_does_not_overwrite_newer(db_conn):
    newer = doc(title="new", created_at="2026-08-03T00:00:00+00:00")
    older = doc(title="old", created_at="2026-07-30T00:00:00+00:00")
    upsert_posting(db_conn, newer, ingest_source="t")
    assert upsert_posting(db_conn, older, ingest_source="t") == "unchanged"
    assert db_conn.execute("SELECT title FROM postings").fetchone()["title"] == "new"
    assert count(db_conn, "posting_observations") == 2

def test_missing_key_is_skipped(db_conn):
    assert upsert_posting(db_conn, doc(source_job_id=""), ingest_source="t") == "skipped"
    assert count(db_conn, "postings") == 0

def test_unknown_source_and_empty_function_are_kept(db_conn):
    d = doc(source_name="indeed", job_function_name="", job_category_name="")
    assert upsert_posting(db_conn, d, ingest_source="t") == "inserted"

def test_bad_posted_at_becomes_null(db_conn):
    upsert_posting(db_conn, doc(posted_at="상시채용"), ingest_source="t")
    assert db_conn.execute("SELECT posted_on FROM postings").fetchone()["posted_on"] is None

def test_failed_run_leaves_no_partial_rows(db_conn):
    bad = doc(source_job_id="x2", skills="not-a-list-of-dicts", salary=object())
    with pytest.raises(Exception):
        with db_conn.transaction():
            ingest_documents(db_conn, [doc(), bad], ingest_source="t")
    assert count(db_conn, "postings") == 0

def test_delete_ingest_source_keeps_postings_seen_elsewhere(db_conn):
    upsert_posting(db_conn, doc(), ingest_source="backfill:x")
    upsert_posting(db_conn, doc(created_at="2026-11-25T00:00:00+00:00"), ingest_source="daily")
    upsert_posting(db_conn, doc(source_job_id="only-backfill"), ingest_source="backfill:x")
    assert delete_ingest_source(db_conn, "backfill:x") == 1
    assert count(db_conn, "postings") == 1 and count(db_conn, "posting_observations") == 1
```

`tests/test_renormalize.py`:

```python
def test_drops_noise_and_recanonicalizes_skills():
    noise = next(s for s in ["우대사항", "경력", "신입", "etc"] if is_skill_noise(s))
    d = {"skills": [{"raw_text": noise, "canonical_name": noise},
                    {"raw_text": "python", "canonical_name": "python"},
                    {"raw_text": "zz-unknown", "canonical_name": "Keep Me"}],
         "job_function_name": "Backend Engineer", "job_category_name": "Engineering & Technology"}
    out = renormalize_doc(d)
    assert [s["canonical_name"] for s in out["skills"]] == ["Python", "Keep Me"]
    assert len(d["skills"]) == 3  # 입력은 그대로

def test_invalid_function_becomes_uncategorized():
    out = renormalize_doc({"skills": [], "job_function_name": "Retired Role",
                           "job_category_name": "Engineering & Technology"})
    assert (out["job_function_name"], out["job_category_name"]) == ("", "")
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_db_ingest.py tests/test_renormalize.py -q` → FAIL (import 오류)

- [ ] **Step 3: 구현** — 위 Interfaces와 "정한 규칙"대로.

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests -q` → `passed ≥ N0 + 16`, failed 0, skipped 0

- [ ] **Step 5: 스냅샷을 실제로 적재해 확인** — 개발용 DB `jobtrend`를 따로 만든다(`docker compose -f docker-compose.dev.yml exec db createdb -U jobtrend jobtrend`).

Run (두 번):
`DATABASE_URL=postgresql://jobtrend:jobtrend@127.0.0.1:54329/jobtrend .venv/bin/python -m src.db.migrate && DATABASE_URL=… .venv/bin/python scripts/backfill_snapshot.py --archive data/data-archive/data_snapshot_20260803.tar.gz`
Expected: 첫 실행 `inserted=659 observations=1155`, 두 번째 `inserted=0 observations=0`, 두 번 모두 `postings=659 observations=1155`. 숫자가 다르면 멈추고 보고한다(스냅샷 실측: 레코드 1,155, 고유 키 659, 키 누락 0).

- [ ] **Step 6: Commit** — `공고 멱등 적재와 8월 스냅샷 backfill 스크립트를 추가한다`

---

### Task 4: MCP tool 5개를 SQL 조회로 (#15)

**Files:**
- Create: `src/db/queries.py`, `scripts/check_sql_parity.py`, `tests/test_db_tools.py`, `tests/test_db_tools_parity.py`
- Modify: `src/mcp_server/tools/search.py`, `skill_trend.py`, `category_stats.py`, `salary_summary.py`, `company_activity.py`, `src/mcp_server/server.py`(42행 `get_store()` 호출과 그 import 삭제), `scripts/run_eval.py`(`_dataset_label`이 DB의 공고 수 · `last_seen_at` 최댓값을 쓰게)

**Interfaces:**
- Consumes: `connection()`, `DatabaseUnavailable`(Task 2), `ingest_documents`(Task 3).
- Produces — tool 함수 5개는 끝에 `conn: psycopg.Connection | None = None` 인자를 더한다. **`store`를 주면 지금 코드 그대로(메모리 경로)**, 안 주면 SQL 경로(`conn`이 없으면 `connection()`에서 빌림). 응답 dict의 키 · `status` · `message` 문구는 두 경로가 같아야 하므로 응답을 만드는 코드는 공유하고, 후보를 고르고 세는 부분만 갈린다. SQL 경로의 이름 해석(`resolve_job_function`, `resolve_source_name`, `known_*`)은 `load()`하지 않은 `JobPostingStore()` 인스턴스로 한다.
- `src/db/queries.py` (전부 `conn` 첫 인자, 값은 반드시 바인드 파라미터로):
  - `count_postings(conn) -> int`
  - `search_postings(conn, *, job_function=None, job_category=None, source_name=None, location=None, employment_type=None, work_arrangement=None, keyword=None, skill=None, posted_from: date | None = None, active_only=True, limit=20, offset=0) -> tuple[int, list[dict]]` — (조건에 맞는 전체 수, `doc` 목록). 정렬 `sort_key DESC, id`.
  - `skill_counts(conn, *, job_function, source_name=None, active_only=True, top_n=15) -> tuple[int, list[tuple[str, int]]]` — (공고 수, 스킬별 공고 수). 정렬 `count DESC, canonical_name`.
  - `category_counts(conn, *, source_name=None, active_only=True) -> dict[str, int]` — 키는 `job_category_name`(빈 문자열 포함).
  - `salary_rows(conn, *, job_function=None, location=None, source_name=None, active_only=True) -> tuple[int, list[dict]]` — (조건에 맞는 공고 수, 숫자 급여가 있는 공고의 `salary_min, salary_max, currency_code, pay_period`).
  - `company_index(conn, *, source_name=None, active_only=True) -> dict[str, str]` — `company_key` → 가장 많이 쓰인 `company_name`.
  - `company_postings(conn, company_key, *, source_name=None, active_only=True) -> list[dict]` — `doc` 목록, `sort_key DESC, id`.
- 필터 조건(메모리 경로와 같은 뜻): 지역 `position(lower(입력) in location_blob) > 0`, 고용형태 `employment_type_norm = 정규화값 OR position(lower(입력) in lower(employment_type_name)) > 0`, 근무형태 `position(lower(입력) in lower(coalesce(work_arrangement, ''))) > 0`, `active_only`면 `crawl_status = 'ACTIVE'`. `LIKE`는 쓰지 않는다. `keyword` · `skill` · `posted_from`은 Task 6에서 쓴다(`keyword`: `title` · `normalized_title` · `company_name` 중 하나에 대소문자 무시 `position`, `skill`: `posting_skills.canonical_name` 일치, `posted_from`: `posted_on >= 값`).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_db_tools.py` — fixture `seeded(db_conn)`는 `ingest_documents(db_conn, SAMPLE_DOCS, ingest_source="t")` 후 `db_conn`을 돌려준다. `tests/test_mcp_server.py`의 `TestSearch` · `TestSkillTrend` · `TestCategoryStats` · `TestSalarySummary` · `TestCompanyActivity` 중 `store=sample_store`만 쓰는 테스트를 같은 이름 · 같은 단언으로 `conn=seeded`로 옮긴다(fixture 문서를 직접 만드는 `test_spacexx_does_not_suggest_paychex`, `test_suggest_rejects_loose_similarity`, 재수집 테스트는 빼고). 그리고 다음을 더한다.

```python
def test_location_special_chars_are_literal(seeded):
    for q in ["%", "_", "서울'; DROP TABLE postings;--"]:
        out = search_job_postings(location=q, conn=seeded)
        assert out["status"] == "empty" and out["total_matched"] == 0
    assert count(seeded, "postings") == 5

def test_category_counts_include_uncategorized(seeded):
    upsert_posting(seeded, doc(source_job_id="u1", source_name="indeed",
                               job_function_name="", job_category_name=""), ingest_source="t")
    out = get_posting_count_by_category(conn=seeded)
    assert out["uncategorized_count"] == 1
    assert out["total_postings"] == sum(c["count"] for c in out["categories"]) + 1

def test_results_have_no_description(seeded):
    out = search_job_postings(conn=seeded)
    assert all("description" not in r for r in out["results"])

def test_server_imports_without_database():
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "TEST_DATABASE_URL")}
    proc = subprocess.run([sys.executable, "-c", "import src.mcp_server.server"],
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

def test_tool_raises_database_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none_test")
    reset_pool()
    try:
        with pytest.raises(DatabaseUnavailable):
            search_job_postings()
    finally:
        monkeypatch.undo(); reset_pool()
```

`tests/test_db_tools_parity.py` — 같은 `SAMPLE_DOCS`를 `sample_store`와 `seeded` 양쪽에 두고 비교한다.

```python
CASES = [
    (search_job_postings, {}), (search_job_postings, {"job_function": "Backend Engineer"}),
    (search_job_postings, {"job_function": "Backend Engineer", "active_only": False}),
    (search_job_postings, {"job_category": "data & analytics"}),
    (search_job_postings, {"location": "서울", "employment_type": "Full-time"}),
    (search_job_postings, {"work_arrangement": "remote", "source_name": "원티드"}),
    (search_job_postings, {"job_function": "zz-not-a-role"}), (search_job_postings, {"limit": 1}),
    (get_skill_trend, {"job_function": "Backend Engineer"}),
    (get_skill_trend, {"job_function": "Data Analyst", "source_name": "jumpit"}),
    (get_posting_count_by_category, {}), (get_posting_count_by_category, {"source_name": "wanted"}),
    (get_salary_summary, {}), (get_salary_summary, {"job_function": "Backend Engineer"}),
    (get_salary_summary, {"job_function": "Backend Engineer", "location": "부산"}),
    (get_company_hiring_activity, {"company_name": "acme"}),
    (get_company_hiring_activity, {"company_name": "Acm"}),
    (get_company_hiring_activity, {"company_name": ""}),
]

@pytest.mark.parametrize("fn, kwargs", CASES)
def test_sql_path_equals_memory_path(fn, kwargs, sample_store, seeded):
    assert comparable(fn(**kwargs, conn=seeded)) == comparable(fn(**kwargs, store=sample_store))
```

`comparable(out)`: 순서가 동률일 때 달라질 수 있는 목록(`results`, `postings`, `skills`, `job_function_counts`, `location_counts`, `suggestions`)을 정렬해서 비교하고, Task 5가 더하는 키(`series`, `series_note`, `collection_gaps`)는 뺀다.

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_db_tools.py tests/test_db_tools_parity.py -q` → FAIL (`unexpected keyword argument 'conn'`)

- [ ] **Step 3: 구현** — `queries.py`와 tool 5개의 SQL 경로, `server.py`의 import 시점 로드 삭제, `run_eval.py`의 데이터 표시.

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests -q` → failed 0, skipped 0, `tests/test_mcp_server.py`(52개) · `tests/test_mcp_tool_contract.py` 전부 통과

- [ ] **Step 5: 스냅샷 전체로 비교** — `scripts/check_sql_parity.py --archive <tar.gz>`: 스냅샷을 풀어 `renormalize_doc` 한 문서를 임시 폴더에 JSON으로 써서 `JobPostingStore().load()`로 읽고(메모리 쪽), `DATABASE_URL`의 DB(Task 3 Step 5에서 적재한 것)와 비교한다. 질문 목록: 직무 53개 각각에 대해 검색(`limit=100`) · 스킬(`top_n=50`) · 급여, 사이트 11개 각각에 대해 직군 건수 · 검색, 공고가 많은 회사 20곳의 채용 현황, 필터 없는 검색 · 직군 건수 · 급여. 비교 항목: `status`, 건수 필드 전부, 스킬 · 직군 · 직무 · 지역별 건수(이름 → 수), 급여 `summaries`. 한 줄 요약 `parity OK: <n> queries` 또는 다른 질문 목록을 출력하고 다르면 종료 코드 1.

Run: `DATABASE_URL=…/jobtrend .venv/bin/python scripts/check_sql_parity.py --archive data/data-archive/data_snapshot_20260803.tar.gz`
Expected: `parity OK`. 스킬 상위 N의 경계에서 동률 때문에 이름만 다른 경우는 건수가 같으면 통과로 본다.

- [ ] **Step 6: Commit** — `MCP tool 5개가 PostgreSQL 을 조회하게 한다`

---

### Task 5: 스킬 트렌드 시계열 (#15)

**Files:**
- Modify: `src/db/queries.py`, `src/mcp_server/tools/skill_trend.py`, `src/mcp_server/server.py`(`get_skill_trend` 설명에 아래 문장 추가), `docs/mcp_server.md`
- Test: `tests/test_skill_trend_series.py`

**Interfaces:**
- Consumes: `skill_counts`, `posting_observations`.
- Produces:
  - `queries.skill_weekly_series(conn, *, job_function, skills: list[str], source_name=None, active_only=True) -> list[dict]` — 주(월요일 시작, `date_trunc('week', observed_on)`)마다 `{"week_start": date, "posting_count": int, "counts": {skill: int}}`, 오래된 주부터.
  - `get_skill_trend`의 SQL 경로 응답에 키 3개 추가(파라미터는 그대로, `status`가 `ok` · `empty`일 때만. `unknown_param`에는 넣지 않는다. 메모리 경로에는 넣지 않는다):
    - `series`: `[{"week_start": "2026-07-27", "posting_count": 120, "skills": [{"skill": "Python", "count": 60, "share": 0.5}]}]` — `skills`는 응답의 상위 `top_n` 스킬만, 순서도 같다. `share` = `count / posting_count`, 소수 넷째 자리 반올림. 그 주에 0건인 스킬도 `count: 0`으로 넣는다. 공고 수는 그 주에 한 번이라도 관측된 공고 수.
    - `collection_gaps`: 이웃한 두 주 사이가 7일보다 벌어지면 `{"from": "<앞 주 시작 + 7일>", "to": "<뒤 주 시작 − 1일>"}`.
    - `series_note`: `"Weekly values come from a capped daily collection sample, not a full census. Compare share, not count. Weeks listed in collection_gaps have no data."`
  - tool 설명에 추가할 문장: `series 는 주 단위 추이이고 수집 표본 기준이므로 건수가 아니라 share(비율)로 비교한다.`

- [ ] **Step 1: 실패하는 테스트 작성** — 관측일이 다른 문서를 넣어 확인한다.

```python
@pytest.fixture
def weekly(db_conn):
    def be(i, day, skills):
        ts = f"{day}T00:00:00+00:00"
        return doc(source_job_id=f"w{i}", created_at=ts, last_seen_at=ts, first_collected_at=ts,
                   skills=[{"raw_text": s, "canonical_name": s} for s in skills])
    ingest_documents(db_conn, [
        be(1, "2026-07-29", ["Python", "Docker"]), be(2, "2026-07-30", ["Python"]),
        be(3, "2026-08-04", ["Go"]),                # 다음 주
        be(4, "2026-11-24", ["Python", "Go"]),      # 공백 뒤
    ], ingest_source="t")
    return db_conn

def test_series_buckets_by_week_with_share(weekly):
    out = get_skill_trend("Backend Engineer", conn=weekly)
    assert [w["week_start"] for w in out["series"]] == ["2026-07-27", "2026-08-03", "2026-11-23"]
    first = out["series"][0]
    assert first["posting_count"] == 2
    assert {s["skill"]: (s["count"], s["share"]) for s in first["skills"]} == {
        "Python": (2, 1.0), "Go": (0, 0.0), "Docker": (1, 0.5)}

def test_series_skills_follow_top_n_order(weekly):
    out = get_skill_trend("Backend Engineer", top_n=1, conn=weekly)
    assert [[s["skill"] for s in w["skills"]] for w in out["series"]] == [["Python"]] * 3

def test_gap_is_reported_not_bridged(weekly):
    out = get_skill_trend("Backend Engineer", conn=weekly)
    assert out["collection_gaps"] == [{"from": "2026-08-10", "to": "2026-11-22"}]
    assert "share" in out["series_note"]

def test_same_posting_seen_twice_in_a_week_counts_once(weekly):
    ts = "2026-07-31T00:00:00+00:00"
    upsert_posting(weekly, doc(source_job_id="w1", created_at=ts, last_seen_at=ts,
                               skills=[{"raw_text": "Python", "canonical_name": "Python"},
                                       {"raw_text": "Docker", "canonical_name": "Docker"}]),
                   ingest_source="t")
    assert get_skill_trend("Backend Engineer", conn=weekly)["series"][0]["posting_count"] == 2

def test_empty_has_empty_series_and_unknown_has_none(db_conn):
    assert get_skill_trend("Backend Engineer", conn=db_conn)["series"] == []
    assert "series" not in get_skill_trend("zz-not-a-role", conn=db_conn)
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_skill_trend_series.py -q` → FAIL (`KeyError: 'series'`)
- [ ] **Step 3: 구현** — 위 Interfaces대로. `docs/mcp_server.md`의 `get_skill_trend` 절에 새 필드 3개와 "표본 기준" 설명을 더한다.
- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests -q` → failed 0, skipped 0 (계약 테스트 포함)
- [ ] **Step 5: 스냅샷 DB에서 눈으로 확인** — Run: `DATABASE_URL=…/jobtrend .venv/bin/python -c "from src.mcp_server.tools.skill_trend import get_skill_trend as g; import json; print(json.dumps(g('Backend Engineer', top_n=3)['series'], ensure_ascii=False, indent=1))"` → 7/27 주와 8/3 주가 나온다.
- [ ] **Step 6: Commit** — `get_skill_trend 가 주 단위 추이를 함께 돌려준다`

---

### Task 6: 검색 REST API (#17)

**Files:**
- Create: `src/api/__init__.py`, `src/api/app.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `queries.search_postings`, `queries.count_postings`, `connection()`, `DatabaseUnavailable`, `summarize_posting`(`tools/search.py`), `JobPostingStore()`의 이름 해석, `lookup_skill_canonical`.
- Produces: `src.api.app:app` (FastAPI). 실행 `uvicorn src.api.app:app --host 127.0.0.1 --port 8001`. DB 연결은 FastAPI 의존성 `get_conn`으로 주입한다(테스트가 `app.dependency_overrides[get_conn]`으로 `db_conn`을 넣는다). 엔드포인트는 `def`(동기)로 쓴다.
  - `GET /healthz` → 200 `{"status": "ok", "postings": <int>}`, DB에 못 붙으면 503 `{"status": "unavailable"}`.
  - `GET /api/v1/postings` — 쿼리: `job_function`, `job_category`, `location`, `employment_type`, `work_arrangement`, `source_name`, `q`(2 ~ 100자), `skill`, `posted_from`(`YYYY-MM-DD`), `active_only`(기본 true), `limit`(1 ~ 100, 기본 20), `offset`(0 이상, 기본 0).
    - 200 `{"total": int, "limit": int, "offset": int, "items": [summarize_posting(doc) …], "note": "Collected sample from capped daily crawls; not a full census."}`. 0건이어도 200.
    - 알 수 없는 `job_function` · `job_category` · `source_name` · `skill` → 400 `{"detail": <MCP tool과 같은 안내 문구>, "param": "<이름>"}`. `skill`은 `lookup_skill_canonical`로 표준 이름을 찾고, 없으면 400 (`Unknown skill '<입력>'.`).
    - 범위를 벗어난 `limit` · `offset` · `q` 길이 · 날짜 형식 → FastAPI 기본 422.
    - DB에 못 붙으면 503 `{"detail": "database unavailable"}`.

- [ ] **Step 1: 실패하는 테스트 작성** — `client` fixture는 `seeded`를 `get_conn`에 덮어쓴 `TestClient(app)`.

```python
def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok", "postings": 5}

def test_search_filters_and_paginates(client):
    body = client.get("/api/v1/postings", params={"job_function": "백엔드", "limit": 1}).json()
    assert (body["total"], body["limit"], body["offset"], len(body["items"])) == (2, 1, 0, 1)
    page2 = client.get("/api/v1/postings",
                       params={"job_function": "백엔드", "limit": 1, "offset": 1}).json()
    assert page2["items"][0]["original_url"] != body["items"][0]["original_url"]

def test_items_are_summaries_without_description(client):
    item = client.get("/api/v1/postings").json()["items"][0]
    assert set(item) == {"title", "company", "location", "employment_type", "work_arrangement",
                         "job_function", "job_category", "posted_at", "original_url", "source_name"}

def test_keyword_skill_and_date_filters(client):
    get = lambda **p: client.get("/api/v1/postings", params=p).json()["total"]
    assert get(q="frontend") == 1 and get(q="ACME") == 3
    assert get(skill="kubernetes") == 1 and get(posted_from="2026-08-02") == 2

def test_keyword_special_chars_are_literal(client):
    for q in ["%%", "__", "a'; DROP TABLE postings;--"]:
        r = client.get("/api/v1/postings", params={"q": q})
        assert r.status_code == 200 and r.json()["total"] == 0
    assert client.get("/healthz").json()["postings"] == 5

def test_empty_result_is_200(client):
    r = client.get("/api/v1/postings", params={"location": "제주"})
    assert r.status_code == 200 and r.json()["items"] == []

@pytest.mark.parametrize("param, value", [("job_function", "zz-not-a-role"), ("source_name", "linkedin"),
                                          ("job_category", "zz"), ("skill", "zz-not-a-skill")])
def test_unknown_filter_value_is_400(client, param, value):
    r = client.get("/api/v1/postings", params={param: value})
    assert r.status_code == 400 and r.json()["param"] == param

@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1},
                                    {"q": "a"}, {"posted_from": "8월"}])
def test_out_of_range_is_422(client, params):
    assert client.get("/api/v1/postings", params=params).status_code == 422

def test_healthz_503_when_db_down(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none_test")
    reset_pool()
    try:
        with TestClient(app) as c:
            assert c.get("/healthz").status_code == 503
            assert c.get("/api/v1/postings").status_code == 503
    finally:
        monkeypatch.undo(); reset_pool()
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_api.py -q` → FAIL (`No module named 'src.api'`)
- [ ] **Step 3: 구현** — 위 Interfaces대로.
- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/python -m pytest tests -q` → failed 0, skipped 0
- [ ] **Step 5: 로컬에서 띄워 확인** — Run: `DATABASE_URL=…/jobtrend .venv/bin/uvicorn src.api.app:app --port 8001 &` 뒤 `curl -s "127.0.0.1:8001/api/v1/postings?job_function=Backend%20Engineer&limit=1"` → `total`이 0보다 크고 `items` 1개. `curl -s 127.0.0.1:8001/healthz` → `"postings": 659`.
- [ ] **Step 6: Commit** — `공고 검색 REST API 를 추가한다`

---

### Task 7: EC2 수동 구축과 공개 배포 (#16, #17)

**이 태스크는 사람이 한다.** 에이전트는 Step 1(저장소에 들어갈 파일)까지만 하고 멈춘다. 콘솔 작업 · 비용 발생 · 외부 공개가 들어 있다.

**Files:**
- Create: `deploy/nginx/job-trend.conf`, `deploy/systemd/job-trend-api.service`, `deploy/systemd/job-trend-mcp.service`, `deploy/env.example`, `docs/deploy/manual-ec2.md`, `docs/deploy/manual-pain-log.md`

**정한 값**
- 리전 `ap-northeast-2`. VPC `10.0.0.0/16`, 퍼블릭 서브넷 `10.0.1.0/24`, 인터넷 게이트웨이, 라우팅 `0.0.0.0/0 → IGW`.
- 보안 그룹: 22는 내 IP만, 80 · 443은 전체. 그 밖은 닫는다(5432 포함).
- EC2: Ubuntu Server 24.04 LTS (arm64), t4g.small, gp3 20GB, 탄력적 IP 1개.
- AWS Budgets: 월 비용 예산 `$21.4`(3만 원, 환율 1,400원), 알림은 실제 비용 67%(약 2만 원) · 100%(3만 원) 두 개, 이메일 수신.
- 서버 배치: 사용자 `jobtrend`, 코드 `/opt/job-trend-mcp`(git clone), 가상환경 `/opt/job-trend-mcp/.venv`, 환경 파일 `/etc/job-trend/env`(root 소유 · 600), 로그는 journald.
- PostgreSQL 16(apt), DB `jobtrend`, 역할 `jobtrend`, `listen_addresses`는 기본값(`localhost`) 그대로.
- `deploy/env.example` 키: `DATABASE_URL=postgresql://jobtrend:<비밀번호>@127.0.0.1:5432/jobtrend`, `MCP_TRANSPORT=streamable-http`, `MCP_HOST=127.0.0.1`, `MCP_PORT=8000`, `MCP_ALLOWED_HOSTS=<도메인>`.
- systemd 유닛 2개: `EnvironmentFile=/etc/job-trend/env`, `User=jobtrend`, `WorkingDirectory=/opt/job-trend-mcp`, `Restart=on-failure`, `After=postgresql.service`. API `ExecStart=/opt/job-trend-mcp/.venv/bin/uvicorn src.api.app:app --host 127.0.0.1 --port 8001`, MCP `ExecStart=/opt/job-trend-mcp/.venv/bin/python -m src.mcp_server.server`.
- Nginx: `limit_req_zone $binary_remote_addr zone=perip:10m rate=5r/s;` 를 `/api/` · `/mcp` 에 `burst=20 nodelay`로 적용, 초과 시 429(`limit_req_status 429`). `/healthz` 와 `/api/` → `127.0.0.1:8001`. `/mcp` → `127.0.0.1:8000` (`proxy_http_version 1.1`, `proxy_buffering off`, `proxy_read_timeout 300s`, `proxy_set_header Host $host`). 그 밖의 경로는 404. TLS는 `certbot --nginx`가 붙인다.
- 불편 기록(`manual-pain-log.md`)은 표 형식: 시각 · 한 일 · 걸린 시간 · 불편했던 점 · 다시 하면 자동화할 것. 시작 · 끝 시각을 반드시 적는다(Task 8의 "수동 배포 시간").

- [ ] **Step 1: 설정 파일과 절차 문서 작성 (에이전트)** — 위 값대로 `deploy/` 파일 4개와 `docs/deploy/manual-ec2.md`(아래 Step 2 ~ 8을 명령어와 함께 풀어 쓴 것), 빈 표만 있는 `manual-pain-log.md`. Commit: `수동 배포용 Nginx · systemd 설정과 절차 문서를 추가한다`. **여기서 멈춘다.**
- [ ] **Step 2: 예산 알림부터 만든다** — 확인: Budgets 화면에 알림 2개.
- [ ] **Step 3: 네트워크와 서버 생성** — 확인: `ssh ubuntu@<탄력적 IP>` 접속, 다른 네트워크에서 `nc -vz <IP> 5432` 가 실패.
- [ ] **Step 4: 서버 설치** — `apt install postgresql nginx python3-venv git certbot python3-certbot-nginx`, DB · 역할 생성, 코드 clone, `pip install -e .`, `/etc/job-trend/env` 작성, `python -m src.db.migrate`. 확인: `psql -c '\dt'` 에 테이블 4개.
- [ ] **Step 5: 데이터 적재** — 스냅샷 tar를 `scp`로 올리고 `scripts/backfill_snapshot.py` 실행. 확인: `postings=659 observations=1155`.
- [ ] **Step 6: 서비스 등록** — 유닛 2개를 `/etc/systemd/system/`에 복사, `systemctl enable --now`. 확인: `curl -s 127.0.0.1:8001/healthz` 가 `"postings": 659`, `systemctl is-active job-trend-api job-trend-mcp` 가 둘 다 `active`, 재부팅 뒤에도 같다.
- [ ] **Step 7: 도메인 · HTTPS** — DNS A 레코드 → 탄력적 IP, Nginx 설정 복사 후 `nginx -t`, `certbot --nginx -d <도메인>`. 확인(내 컴퓨터에서):
  - `curl -s https://<도메인>/healthz` → 200
  - `curl -s "https://<도메인>/api/v1/postings?job_function=Backend%20Engineer&limit=1"` → `items` 1개
  - `curl -s -o /dev/null -w '%{http_code}' https://<도메인>/` → 404
  - 빠르게 100번 호출하면 429가 섞여 나온다
- [ ] **Step 8: 공개 MCP 확인(ngrok 없이)** — Claude 웹 커스텀 커넥터의 URL을 `https://<도메인>/mcp`로 바꾸고(지금 등록된 것은 옛 주소라 404), "백엔드 공고에서 많이 요구하는 스킬"을 물어 `get_skill_trend`가 호출되는지 본다. 421이 나오면 `MCP_ALLOWED_HOSTS`를 확인한다(`docs/HANDOFF.md`의 421 절).
- [ ] **Step 9: 불편 기록 정리 후 Commit** — `EC2 수동 구축 기록을 남긴다`

---

### Task 8: 수치 기록과 README (#18)

**Files:**
- Create: `scripts/measure_api_latency.py`, `tests/test_measure_api_latency.py`, `docs/metrics/phase1.md`
- Modify: `README.md`

**Interfaces:**
- Produces: `percentile(values: list[float], p: float) -> float`(nearest-rank, 빈 목록이면 `ValueError`), CLI `python scripts/measure_api_latency.py --base-url <url> [--requests 200] [--concurrency 1]` — 정해 둔 검색 질의 5개(필터 없음, `job_function=Backend Engineer`, `location=서울`, `q=engineer`, `skill=python`)를 돌아가며 호출하고 `requests=… errors=… p50_ms=… p95_ms=… max_ms=…` 한 줄을 출력한다. 요청 간격 250ms(Nginx 제한 5r/s 아래).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_percentile_nearest_rank():
    values = [float(v) for v in range(1, 101)]
    assert (percentile(values, 50), percentile(values, 95), percentile(values, 100)) == (50.0, 95.0, 100.0)
    assert percentile([7.0], 95) == 7.0

def test_percentile_empty_raises():
    with pytest.raises(ValueError):
        percentile([], 95)
```

- [ ] **Step 2: 실패 확인** → **Step 3: 구현** → **Step 4:** `.venv/bin/python -m pytest tests -q` 가 failed 0, skipped 0
- [ ] **Step 5: 측정** — Run: `.venv/bin/python scripts/measure_api_latency.py --base-url https://<도메인>` (배포 뒤). 서버 안에서 `--base-url http://127.0.0.1:8001` 로도 한 번(네트워크 구간을 뺀 값).
- [ ] **Step 6: `docs/metrics/phase1.md` 작성** — 표 한 장, 값마다 잰 날짜와 방법을 적는다. 못 잰 칸은 "아직 안 잼"으로 둔다.
  - 수동 배포 소요 시간(불편 기록의 시작 ~ 끝), 단계별 시간
  - API p50 · p95(공개 도메인 / 서버 내부), 요청 수 · 오류 수
  - 월 비용 추정(EC2 · EBS · IP 항목별, AWS 요금 계산기 기준)과 예산 알림 설정
  - 적재: 공고 659 · 관측 1,155, 수집일 범위, 소요 시간
  - 테스트 수: `N0` → 지금
  - parity 결과(`check_sql_parity.py`의 질의 수)
- [ ] **Step 7: README 정리** — 처음 보는 사람이 README만 보고 써 볼 수 있게: 공개 주소 2개(API · MCP)와 `curl` 예시 3개, Claude 커넥터 연결 방법, 로컬 실행(`pip install -e ".[dev]"` → `docker compose -f docker-compose.dev.yml up -d` → migrate → backfill → uvicorn), 구성 그림(Nginx → API/MCP → PostgreSQL), 그리고 **지금의 한계**(데이터는 2026-07-29 ~ 08-04 수집 표본 659건이고 매일 갱신되지 않음, 8월은 arbeitnow 편중, 인증 없음 · 읽기 전용, 다음 순서: 수집 → DB 연결, Compose, Terraform).
- [ ] **Step 8: Commit** — `1단계 수치와 README 를 정리한다`
