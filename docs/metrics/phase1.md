# 1단계 수치

값마다 잰 날짜와 방법을 적습니다. 못 잰 칸은 "아직 안 잼"입니다. 서버는 2026-11-26에 배포했습니다.

| 항목 | 값 | 잰 날짜 · 방법 |
|------|-----|----------------|
| 수동 배포 소요 시간 | 약 41분 (두 번에 나눠 작업) | 2026-11-26, 불편 기록([manual-pain-log.md](../deploy/manual-pain-log.md))의 작업 시각 06:29~06:50, 10:20~10:40. 도메인 구매와 예산 알림 생성 시간은 뺀 값 |
| 수동 배포 단계별 시간 | 네트워크 · 서버 생성 약 21분 / 설치 · 적재 · 서비스 등록 · HTTPS 약 20분 | 위와 같음. 단계별로 더 잘게 재지는 않았다 |
| API p50 · p95 (공개 도메인) | p50 39.8ms · p95 51.6ms · max 621.8ms (요청 200 · 오류 0) | 2026-11-26, 개발 PC(서울, 가정용 회선)에서 `scripts/measure_api_latency.py --base-url https://jobtrend.daeunson.dev`. HTTPS · Nginx 경유 |
| API p50 · p95 (서버 내부, 네트워크 제외) | p50 7.5ms · p95 11.4ms · max 43.3ms (요청 200 · 오류 0) | 2026-11-26, EC2 t4g.small 안에서 `--base-url http://127.0.0.1:8001` (공고 659건) |
| API p50 · p95 (로컬, 개발 PC · Docker PostgreSQL) | p50 13.9ms · p95 23.4ms · max 132.4ms (요청 200 · 오류 0) | 2026-11-24, 개발 DB(공고 659건)에 uvicorn 127.0.0.1:8001, 질의 5종 순환, 요청 간격 250ms. 서버 내부 값이 아니다 |
| 월 비용 추정 | 약 $21, 부가세 포함 약 $23 (약 3만 원, 환율 1,400원) | 2026-11-26, 실제 구성 기준. EC2 t4g.small ≈ $15.2, EBS gp3 20GB ≈ $1.8, 탄력적 IP ≈ $3.65. DNS는 도메인 등록업체 것을 써서 Route53 비용 없음. 단가는 요금표 기억 기준이라 청구서로 확인 필요 |
| 실제 월 비용 | 아직 안 잼 | 배포 뒤 청구서로 확인 |
| 예산 알림 | 월 예산 $10, 알림 50%($5) · 100%($10) | 2026-11-26, AWS Budgets에 `job-trend-monthly`로 만듦. 실제 비용 기준, 이메일 수신. 상시 운영 때 $21.4(3만 원)로 올릴 예정 |
| 요청 제한 | 100건 동시 요청 중 21건 통과 · 79건 429 | 2026-11-26, 개발 PC에서 `/api/v1/postings?limit=1` 을 한꺼번에 100건. Nginx 설정은 IP당 초당 5건 · burst 20 |
| 재부팅 후 복구 | API · MCP · Nginx · PostgreSQL 모두 자동 실행, `/healthz` 659 | 2026-11-26, `sudo reboot` 뒤 확인 |
| 공개 MCP | 도구 5개 목록 · `get_skill_trend` 호출 정상, 호출 기록 JSONL 생성. Claude 웹 커스텀 커넥터(인증 없음)에서 도구 호출 7건 모두 정상 응답(2.4 ~ 22.9ms) | 2026-11-26, `https://jobtrend.daeunson.dev/mcp` 에 초기화 → 도구 목록 → 도구 호출을 직접 보내 확인. 이어 Claude 웹에서 "백엔드 공고에서 많이 요구하는 스킬"을 묻고 서버의 호출 기록으로 확인(`get_posting_count_by_category` 1건, `get_skill_trend` 6건). 원티드 조건 1건은 결과 0건(`empty`)이었다 |
| 적재 결과 | 공고 659 · 관측 1,155 | 2026-11-24, `scripts/backfill_snapshot.py` (다시 돌려도 같음: inserted=0 updated=659) |
| 수집일 범위 | 2026-07-29 ~ 2026-08-04 | 위 적재의 `observed_on` min / max |
| 적재 소요 시간 | 2.8초 | 2026-11-24, `time` 으로 잰 재실행 값(개발 PC, 로컬 Docker PostgreSQL) |
| 테스트 수 | N0 1181 → 1278 passed (failed 0, skipped 0) | 2026-11-24, `pytest tests -q` (`TEST_DATABASE_URL` 지정) |
| SQL parity | parity OK: 204 queries | 2026-11-24, `scripts/check_sql_parity.py --archive data/data-archive/data_snapshot_20260803.tar.gz` |
