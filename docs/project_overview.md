# 프로젝트 현황 요약

작성 기준: 2026-08-14 (코드·`ALL_SOURCES`·연결 검증).  
스키마 → [data_schema.md](data_schema.md) · MCP tool → [mcp_server.md](mcp_server.md) · 연결 방법 → [mcp_connection_guide.md](mcp_connection_guide.md)

---

## 한 줄

사이트별 원문 공고를 수집하고, 공통 정규화 과정을 거쳐 표준 필드로 저장한 뒤, MCP 서버로 조회합니다.

---

## 1. 전체 흐름

```
사이트별 수집 (원문 HTML / JSON)
        ↓
공통 정규화 (build_job_posting)
        ↓
표준 필드 저장 (data/job_postings JSON)
        ↓
MCP 서버 tool 조회
```

- 사이트마다 **값을 꺼내는 부분**만 다릅니다.
- 직군·직무·스킬·고용형태 등은 공통 모듈에서 표준값으로 맞춥니다.
- DB는 아직 없고, 저장소는 로컬 JSON입니다.

---

## 2. 수집 대상 — 국내 6 · 해외 5 · 총 11

`ALL_SOURCES` 11개 전부 `is_active=True`입니다.

### 국내 6

| 사이트 | 수집 방식 |
|--------|-----------|
| 사람인 | HTML 크롤 |
| 잡코리아 | HTML 크롤 |
| 원티드 | 내부 JSON API |
| 점핏 | 내부 JSON API |
| 랠릿 | 내부 JSON API |
| 고용24 | HTML 크롤 |

### 해외 5

| 사이트 | 수집 방식 |
|--------|-----------|
| Remotive | 공식 공개 API |
| The Muse | 공식 공개 API |
| Arbeitnow | 공식 공개 API |
| USAJobs | 내부 JSON API |
| Adzuna | HTML 크롤 (gb/au, US는 CAPTCHA로 제외) |

제외·보류(약관, 봇 방어, 통계 스키마 불일치 등)는 [HANDOFF.md](HANDOFF.md)를 보세요.

---

## 3. 저장 데이터

표준 채용공고(`job_postings`)에 아래를 저장합니다.

| 항목 | 표준 규모 (코드 실측) |
|------|----------------------|
| 직군 | 15개 |
| 직무 | 53개 |
| 스킬 | 91개 |
| 고용형태 | 정규직·계약 등 |
| 급여 | 금액·통화·지급 주기 |
| 그 외 | 경력, 근무형태, 지역, 회사 |

원문은 `data/raw_job_postings/`에 따로 남겨, 파서를 고쳐도 다시 쓸 수 있습니다.

---

## 4. MCP 서버 — 기능 5개

| 기능 | tool 이름 |
|------|-----------|
| 공고 검색 | `search_job_postings` |
| 직군 통계 | `get_posting_count_by_category` |
| 스킬 트렌드 | `get_skill_trend` |
| 급여 통계 | `get_salary_summary` |
| 회사별 공고 조회 | `get_company_hiring_activity` |

파라미터·응답 예시는 [mcp_server.md](mcp_server.md)에 있습니다.

---

## 5. 연결 테스트

두 경로 모두 tool 호출까지 확인했습니다.

| 경로 | 방식 | 상태 |
|------|------|------|
| Claude Desktop | 로컬 stdio | 정상 (2026-08-11) |
| Claude 웹 커스텀 커넥터 | Streamable HTTP + ngrok | 정상 |

설치·등록 절차는 [mcp_connection_guide.md](mcp_connection_guide.md)를 따르세요.
