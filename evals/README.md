# MCP 도구 호출 평가

같은 문항을 모델별로 Claude API 에 보내고, 모델이 MCP 도구를 의도대로 썼는지와
응답시간 · 토큰 · 비용을 함께 잽니다. 도구 설명이나 시스템 프롬프트를 바꿨을 때
전후를 같은 기준으로 비교하는 회귀 테스트로 씁니다.

## 무엇을 재나

| 항목 | 뜻 |
|---|---|
| 도구 선택 (`tool_ok`) | 기준 도구를 한 번이라도 호출했는가 |
| 파라미터 (`call_ok`) | 그 도구 호출 중 하나가 정답과 같은 값을 받았는가 |
| 최종 답 (`answer_ok`) | 답 마지막 줄 `정답: <값>` 이 정답과 같은가 |
| 함정 (`trap_hit`) | 흔한 실수 값으로 답했는가 (예: 사이트 필터를 빼먹은 통합 건수) |
| 지연 · 토큰 · 비용 | 문항 하나의 전체 왕복 시간, 입력 · 출력 토큰, 정가 기준 비용 |

정답은 문항마다 정한 **기준 호출**을 현재 데이터에 실행한 값입니다. 시장 전체의 정답이
아니라 "모델이 도구로 그 값에 도달하는가"를 보는 기준이라, 데이터를 다시 수집해도
문항 파일은 그대로 쓰고 정답만 새로 계산합니다.

채점은 코드로 합니다. 시스템 프롬프트가 답 마지막 줄을 `정답:` 형식으로 쓰게 하므로
LLM 채점이 필요 없습니다.

## 문항 (`cases.json`, 25개)

| 카테고리 | 개수 | 보는 것 |
|---|---|---|
| `simple_search` | 5 | 직무 × 지역 / 고용형태 / 근무형태 필터 |
| `field_trap` | 1 | 목록 길이 `count` 와 전체 건수 `total_matched` 구분 |
| `alias` | 5 | 한글 · 오타 · 약칭 직무명, `FULL_TIME` 표기 |
| `site_specific` | 5 | `source_name` 사용. 빼먹으면 통합 건수(함정 값)가 나온다 |
| `skills` | 3 | 스킬 상위 3개 |
| `salary` | 2 | 전체 급여 표본 수 `salary_data_count` |
| `category` | 2 | 한글 직군명 → 표준 직군 |
| `abstain` | 2 | 데이터에 없는 회사 — 숫자를 지어내지 않는가 |

## 실행

```bash
# 1) API 호출 없이 정답만 계산 · 점검 (재수집 뒤 먼저 실행)
PYTHONPATH=. python scripts/run_eval.py --dry-run

# 2) 모델 비교
PYTHONPATH=. python scripts/run_eval.py \
    --models claude-haiku-5-5 claude-sonnet-5-5 claude-opus-5-5 --repeats 2

# 일부만
PYTHONPATH=. python scripts/run_eval.py --only site_specific a02
```

인증은 `ANTHROPIC_API_KEY` 또는 `ant auth login` 프로필을 씁니다.
결과는 `evals/results/<run_id>/` 에 `report.md`, `results.jsonl`, `ground_truth.json`, `meta.json` 으로 남습니다.

## 버전 관리

- 시스템 프롬프트는 `prompts/system_<버전>.md` 로 두고 `--prompt v2` 처럼 고릅니다.
- 결과의 `meta.json` 에 프롬프트 해시(`prompt_hash`)와 도구 설명 · 스키마 해시(`tools_hash`)가
  남아, 어느 버전의 프롬프트 · 도구 설명으로 낸 점수인지 구분됩니다.
- 도구 이름 · 파라미터 · 응답 필드는 `tests/test_mcp_tool_contract.py` 가 고정합니다.
  의도한 변경이면 계약 테스트를 고치고 이 평가를 다시 돌려 비교합니다.

## 모델 설정

- 기본 effort 는 `medium` (`--effort` 로 변경). thinking 은 각 모델 기본값(adaptive)입니다.
- 서버 측 refusal fallback 은 켜지 않습니다. 켜면 다른 모델이 대신 답해 모델 비교가 흐려지므로,
  거절은 실패로 셉니다.
- 비용은 입력 · 출력 토큰 × 정가로만 계산합니다(프롬프트 캐시 미사용).

## 한계

- 문항 25개, 한 데이터 스냅샷 기준입니다. 반복(`--repeats`)으로 흔들림은 보지만 일반화하지 않습니다.
- 정답이 기준 호출 결과이므로, 도구 자체의 집계가 틀렸다면 이 평가로는 잡히지 않습니다.
  도구 집계의 정확성은 단위 테스트와 `experiments/mcp_comparison/compute_ground_truth.py`
  (pandas 독립 계산과 교차 검증)가 맡습니다.
