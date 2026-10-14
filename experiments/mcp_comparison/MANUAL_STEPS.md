# MCP 비교 실험 v3 — 수동 수집 안내서 (1부)

웹 검색만(Before)과 웹 검색 + MCP 연결(After)의 **정보량·구체성**을 비교합니다.  
**질문 문장은 Before/After가 같습니다.** After 지시문은 **연결된 도구와 웹 검색을 모두** 쓰라고 명시합니다. 응답시간은 답 마지막 줄에 쓰도록 지시합니다.

채점·리포트는 `before_after_template.json`을 다 채운 뒤 **별도 요청**으로 진행합니다.

작업 폴더: `experiments/mcp_comparison/`

| 파일 | 역할 |
|------|------|
| `questions.json` | 질문 18개 설계·표본·tool 매핑 |
| `ground_truth.json` | 우리 데이터셋 정답 (**수집이 끝날 때까지 열지 마세요**) |
| `before_after_template.json` | Before/After 답변 기록 |

데이터 스냅샷: `data/job_postings` ACTIVE **1,155건** (정답 계산 시점). After 직전에 데이터를 다시 크롤하지 마세요.

---

## 0. 시작 전 확인

1. After를 할 PC에는 `data/job_postings/`가 있고, MCP가 그 폴더를 로드해야 합니다.
2. **수동 타이머는 쓰지 않습니다.** 지시문에 응답시간을 마지막 줄에 쓰라고 넣었습니다. 답의 `응답시간: N초`에서 N만 `before_response_time_sec` / `after_response_time_sec`에 옮기면 됩니다. `(추정)`이면 숫자만 넣고, 리포트에서 자기보고임을 밝히면 됩니다.
3. **질문마다, Before/After마다 새 대화**를 권장합니다.
4. `ground_truth.json`은 수집이 끝날 때까지 보지 않습니다.

MCP 연결: `docs/mcp_connection_guide.md`.

---

## 1. Before — MCP 커넥터 없음, 웹 검색만

목적: 실제 사용자처럼 웹 검색으로 숫자·출처를 받게 합니다.  
프로젝트명·도구명(`job-trend-mcp`)은 지시문에 넣지 않습니다.

### 1-1. 준비

- Claude Desktop에서 `job-trend-mcp`를 끄거나 설정에서 제거한 뒤 **Quit 후 재실행**합니다.
- 웹 검색은 **켜 둡니다.**
- 새 대화에 MCP tool이 보이면 대화를 버리고 설정을 다시 확인합니다.

### 1-2. 질문 하나

`before_after_template.json`의 `items`를 q01 → q18 순으로 합니다.

1. 새 대화를 엽니다.
2. **`prompt_to_paste_before`** 전체를 붙여넣습니다.  
   (웹 검색 지시 + 응답시간 지시 + 빈 줄 + 질문)
3. **거절이면 기록하지 말고**, 같은 대화에서 **한 번만** 아래를 그대로 보냅니다.

```
정확한 실시간 수치가 없다면, 지금 웹 검색으로 확인 가능한 가장 최근 자료 기준으로 답해주세요. 출처마다 숫자가 다르면 그 점도 같이 알려주세요.
```

이 재요청까지는 **정상 절차**입니다. 재요청 후 받은 답을 `before_answer`에 넣습니다. 응답시간은 **최종 답의 마지막 줄**을 씁니다.

4. 재요청 후에도 “실시간 데이터를 모른다 / 도구를 켜 달라”만 반복하면  
   `before_answer`에 **`Before 응답 불가`** 라고 적고 다음 질문으로 갑니다. 시간은 비워 둡니다.
5. 웹에서 가져온 숫자·출처가 있으면 답변 전문을 `"before_answer"`에 넣습니다.
6. 마지막 줄 `응답시간: N초`의 N을 `"before_response_time_sec"`에 넣고 저장합니다. 마지막 줄이 없으면 화면의 생성 시간을 쓰고, 그것도 없으면 `null`로 둡니다.

---

## 2. After — MCP 커넥터 있음 + 웹 검색 (둘 다 사용하라고 지시)

목적: 같은 질문을, 도구가 연결된 상태에서 **도구와 웹 검색을 모두 쓰라고 지시**하고 물어 봅니다.  
웹 검색도 After에서 **켜 둡니다.**

### 2-1. 준비

1. `job-trend-mcp`를 넣고 Desktop을 **Quit 후 재실행**합니다.
2. `env.PYTHONPATH`와 `cwd`가 프로젝트 루트인지 확인합니다.
3. 웹 검색이 켜져 있는지 확인합니다.
4. 스모크는 수집용 대화와 분리합니다. 수집은 질문당 새 대화.

### 2-2. 질문 하나

1. 새 대화를 엽니다.
2. **`prompt_to_paste_after`** 전체를 붙여넣습니다.  
   (연결된 도구 + 웹 검색 지시 + 응답시간 지시 + 빈 줄 + 질문)
3. 답변 전문을 `"after_answer"`에 넣습니다. tool을 호출했으면 화면에 보이는 tool 결과도 같이 복사합니다.
4. **도구만 쓰거나 웹만 써도 고치지 말고 그대로 기록**합니다. 2부 채점에서 구분합니다.
5. 마지막 줄 `응답시간: N초`의 N을 `"after_response_time_sec"`에 넣고 저장합니다. 없으면 Before와 같이 화면 시간 또는 `null`.

`matches_ground_truth`는 비워 둡니다.

---

## 3. 저장과 2부에서 볼 항목 (지금은 기록만)

채점 때 질문별로 아래를 봅니다.

- **출처의 구체성:** Before는 원티드/리포트 등 대략치, After는 수집분 기준 정확한 건수인지
- **건수의 정확성:** `ground_truth.json`과 일치하는가
- **세부 통계:** 집계형에서 Before가 일반론에 머무는지
- **q18 broad_control:** 스냅샷 Full-time 건수와 일치하는지가 채점 정답이지만, 해석은 “MCP가 있어도 잡보드 전수와는 다른 모집단”이다. 나머지 17개와 같은 설득력으로 묶지 말 것.

채점 요청 예:

```
before_after_template.json을 다 채웠어. ground_truth.json과 대조해서 채점해줘.
정확도는 '객관적으로 맞았는가'가 아니라 '우리 데이터셋 수치와 정확히 일치하는가'로 판단해줘.
카테고리별 정확도, 응답 시간 Before/After 비교표를 experiments/mcp_comparison/report.md에 만들고,
오답 사례는 왜 틀렸는지(예: 일반론적 답변이라 우리 데이터와 안 맞음, After에서 도구를 안 씀) 한 줄씩 적어줘.
n이 15~20개인 소규모 실험이라는 점도 명시하고, 포트폴리오에 바로 쓸 1~2문장 요약도 맨 위에 추가해줘.
```

---

## 4. 질문 구성 (참고)

실험 v3: **직무(또는 직군) × 조건**. 직무 없이 조건만 묻는 질문은 **q18 `broad_control` 1개**만 둔다.

| 구간 | id | 유형 | 표본 n |
|------|-----|------|--------|
| 단순 검색 | q01 | Backend × Full-time | 73 |
| | q02 | Backend × 서울 | 102 |
| | q03 | Software Engineer × Full-time | 81 |
| | q04 | Software Engineer × Berlin | 35 |
| | q05 | Engineering 직군 × REMOTE | 45 |
| 집계 | q06–q11 | 직무별 스킬 top 5 | 26–209 |
| | q12–q13 | 직무 × 급여 통계 | 209 / 189 |
| 조합 | q14 | Backend × 서울 × Full-time | 42 |
| | q15 | Software Engineer × London × Full-time | 22 |
| | q16 | Software Engineer × Germany × Full-time | 20 |
| | q17 | Engineering 직군 × 서울 | 111 |
| 대조군 | q18 | **정규직 전체** (직무 무관) | 440 |

q18은 MCP가 있어도 웹(잡보드 전수)과 모집단이 다르다는 점을 보여 주는 대조군입니다. 나머지 17개는 직무×조건입니다.

구 q01 Before 답변(Backend 직무만 건수)은 질문이 바뀌어 **폐기**했습니다. 처음부터 다시 수집하세요.

표본 20건 미만 조합은 제외했습니다. q16이 하한(20)입니다.

정답 **재계산**은 데이터나 tool이 바뀌었을 때만:

```bash
PYTHONPATH=. python experiments/mcp_comparison/compute_ground_truth.py
```

수집 중에 실행하지 마세요. 답변이 있으면 템플릿은 `--force-templates` 없이 덮어쓰지 않습니다.

기존 18문항 수집이 끝난 뒤, 사이트 지정형 6문항은 `SITE_SPECIFIC_STEPS.md`와 `site_specific_template.json`을 사용합니다. 기존 템플릿·답변은 건드리지 않습니다.
