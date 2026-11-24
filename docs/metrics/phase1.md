# 1단계 수치

값마다 잰 날짜와 방법을 적습니다. 못 잰 칸은 "아직 안 잼"입니다(서버를 아직 배포하지 않았습니다).

| 항목 | 값 | 잰 날짜 · 방법 |
|------|-----|----------------|
| 수동 배포 소요 시간 | 아직 안 잼 | 배포 때 불편 기록([manual-pain-log.md](../deploy/manual-pain-log.md))의 시작 ~ 끝으로 잰다 |
| 수동 배포 단계별 시간 | 아직 안 잼 | 위와 같음 |
| API p50 · p95 (공개 도메인) | 아직 안 잼 | 배포 뒤 `scripts/measure_api_latency.py --base-url https://<도메인>` |
| API p95 (서버 내부, 네트워크 제외) | 아직 안 잼 | 서버 안에서 `--base-url http://127.0.0.1:8001` |
| API p50 · p95 (로컬, 개발 PC · Docker PostgreSQL) | p50 13.9ms · p95 23.4ms · max 132.4ms (요청 200 · 오류 0) | 2026-11-24, 개발 DB(공고 659건)에 uvicorn 127.0.0.1:8001, 질의 5종 순환, 요청 간격 250ms. 서버 내부 값이 아니다 |
| 월 비용 추정 | 약 $22 (약 3만 원, 환율 1,400원) | 2026-11-24, 설계 표 기준. EC2 t4g.small ≈ $15, EBS gp3 20GB ≈ $2, 탄력적 IP ≈ $3.6, S3 · Route53 ≈ $1. AWS 요금 계산기로 다시 확인 필요 |
| 실제 월 비용 | 아직 안 잼 | 배포 뒤 청구서로 확인 |
| 예산 알림 (2만 원 · 3만 원) | 설정 예정 | 배포 절차 2단계에서 만든다 |
| 적재 결과 | 공고 659 · 관측 1,155 | 2026-11-24, `scripts/backfill_snapshot.py` (다시 돌려도 같음: inserted=0 updated=659) |
| 수집일 범위 | 2026-07-29 ~ 2026-08-04 | 위 적재의 `observed_on` min / max |
| 적재 소요 시간 | 2.8초 | 2026-11-24, `time` 으로 잰 재실행 값(개발 PC, 로컬 Docker PostgreSQL) |
| 테스트 수 | N0 1181 → 1278 passed (failed 0, skipped 0) | 2026-11-24, `pytest tests -q` (`TEST_DATABASE_URL` 지정) |
| SQL parity | parity OK: 204 queries | 2026-11-24, `scripts/check_sql_parity.py --archive data/data-archive/data_snapshot_20260803.tar.gz` |
