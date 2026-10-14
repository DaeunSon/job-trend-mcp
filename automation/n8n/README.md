# n8n 일일 수집 워크플로

n8n Cloud 는 로컬 명령을 실행할 수 없어서, 수집은 GitHub Actions 가 하고 n8n 은 일정과 알림을 맡습니다.

```
[n8n] 매일 06:00 ──POST workflow_dispatch──▶ [GitHub Actions] collect.yml
                                               수집(collect_all.py) → 품질 게이트 → 평가 정답 재계산
                                               → 스냅샷 · collect_runs 아티팩트 보관
[n8n] 수집 결과 수신 (Webhook) ◀──POST 결과── 마지막 단계
      └ 실패 · 품질 게이트 실패면 알림 메일, 정상이면 기록만
```

## 설정 순서

1. **가져오기** — n8n 에서 Workflows → Import from File → `collect_workflow.json`.
2. **GitHub 자격 증명** — GitHub 에서 fine-grained token 을 만듭니다
   (Repository access: `DaeunSon/job-trend-mcp`, Permissions: Actions **Read and write**).
   n8n 의 `GitHub 수집 워크플로 실행` 노드에서 Credential → GitHub API 를 새로 만들고 토큰을 넣습니다.
3. **메일 자격 증명** — `알림 메일` 노드에서 Gmail 계정을 연결하고, 받는 주소(`sendTo`)를 바꿉니다.
4. **웹훅 주소를 GitHub Secret 으로** — 워크플로를 저장 · 활성화한 뒤 `수집 결과 수신` 노드의
   **Production URL** 을 복사해 저장소 Secret 에 넣습니다.

   ```bash
   gh secret set N8N_WEBHOOK_URL -R DaeunSon/job-trend-mcp
   ```

5. **시험** — `GitHub 수집 워크플로 실행` 노드를 수동 실행하면 Actions 에 Collect 실행이 생깁니다.
   끝나면 n8n Executions 에 `수집 결과 수신` 실행이 남습니다.

## 웹훅으로 받는 값

```json
{
  "run_url": "https://github.com/.../actions/runs/...",
  "overall": "ok | partial | failed",
  "total_postings": 2282,
  "quality_passed": true,
  "retry": ["saramin"],
  "sites": [{"source": "wanted", "status": "warning", "added": 360, "total": 360, "error_lines": 4}],
  "failed_checks": {"wanted": ["수집 로그 ERROR 4줄"]}
}
```

## 한계

- GitHub Actions 러너는 해외 IP 라, 국내 사이트 일부가 막힐 수 있습니다. 막히는 사이트는 품질 게이트에서
  건수 급감으로 잡힙니다.
- 데이터는 아티팩트로 30일 보관합니다. MCP 서버가 이 스냅샷을 자동으로 받아 쓰는 단계는 아직 없습니다.
