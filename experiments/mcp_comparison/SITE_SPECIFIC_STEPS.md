# 사이트 지정형 비교 (기존 18문항과 별도)

기존 `questions.json` / `before_after_template.json` **Before 18개는 그대로** 두고, 이 세트만 추가로 수집합니다.

`search_job_postings`에 **`source_name` 필터가 있습니다.** After가 이 파라미터를 쓰면 지정 사이트 수집분 건수, 안 쓰면 직무×조건 **통합** 건수가 나옵니다. 재수집으로 같은 `id`가 여러 파일에 있으면 최신 1건만 셉니다.

| 파일 | 역할 |
|------|------|
| `site_specific_questions.json` | 질문 6개 |
| `site_specific_ground_truth.json` | 사이트 필터 GT + MCP 통합 건수 (**수집 중 열지 마세요**) |
| `site_specific_template.json` | Before/After 기록 |

수집 절차는 기존 18문항과 같습니다. After도 **연결된 도구와 웹 검색을 모두** 쓰라고 `prompt_to_paste_after`에 들어 있습니다.

정답 재계산:

```bash
PYTHONPATH=. python experiments/mcp_comparison/compute_site_specific_gt.py
```

답변이 있으면 템플릿은 `--force-templates` 없이 덮어쓰지 않습니다.
