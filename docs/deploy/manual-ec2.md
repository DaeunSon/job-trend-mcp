# EC2 수동 구축과 공개 배포

AWS 콘솔과 SSH로 손으로 서버를 세우고 REST API · MCP를 공개하는 절차입니다. 시작할 때 시각을 적고, 하면서 불편한 점을 [manual-pain-log.md](manual-pain-log.md)에 남깁니다.

문서의 `<도메인>`은 실제 도메인으로, `<탄력적 IP>`는 할당받은 IP로, `<비밀번호>`는 직접 정한 DB 비밀번호로 바꿉니다. 비밀번호는 저장소 어디에도 적지 않습니다.

## 정한 값

- 리전 `ap-northeast-2`. VPC `10.0.0.0/16`, 퍼블릭 서브넷 `10.0.1.0/24`, 인터넷 게이트웨이, 라우팅 `0.0.0.0/0 → IGW`.
- 보안 그룹: 22는 내 IP만, 80 · 443은 전체. 그 밖은 닫습니다(5432 포함).
- EC2: Ubuntu Server 24.04 LTS (arm64), t4g.small, gp3 20GB, 탄력적 IP 1개.
- 서버 배치: 사용자 `jobtrend`, 코드 `/opt/job-trend-mcp`, 가상환경 `/opt/job-trend-mcp/.venv`, 환경 파일 `/etc/job-trend/env`(root 소유 · 600), 로그는 journald.
- PostgreSQL 16(apt), DB · 역할 이름 `jobtrend`, `listen_addresses`는 기본값(`localhost`) 그대로.

## 2. 예산 알림부터 만든다

콘솔 Billing and Cost Management → Budgets → 비용 예산(Cost budget)을 만듭니다.

- 월 예산 `$21.4`(3만 원, 환율 1,400원)
- 알림 두 개, 둘 다 실제(Actual) 비용 기준, 이메일 수신
  - 67% (약 2만 원)
  - 100% (3만 원)

확인: Budgets 화면에 알림 2개가 보인다.

## 3. 네트워크와 서버 생성

1. VPC `10.0.0.0/16`, 퍼블릭 서브넷 `10.0.1.0/24`, 인터넷 게이트웨이를 만들어 VPC에 붙입니다.
2. 라우트 테이블에 `0.0.0.0/0 → 인터넷 게이트웨이`를 넣고 서브넷에 연결합니다.
3. 보안 그룹을 만듭니다. 인바운드는 22(내 IP만), 80 · 443(전체)뿐입니다. 5432는 열지 않습니다.
4. EC2를 띄웁니다. Ubuntu Server 24.04 LTS (arm64), t4g.small, gp3 20GB, 위 서브넷과 보안 그룹, 키 페어 지정.
5. 탄력적 IP를 하나 받아 인스턴스에 연결합니다.

확인:

```bash
ssh ubuntu@<탄력적 IP>          # 접속된다
nc -vz <탄력적 IP> 5432         # 다른 네트워크에서 실행. 실패해야 한다
```

## 4. 서버 설치

서버에 접속한 상태에서 합니다.

```bash
sudo apt update
sudo apt install -y postgresql nginx python3-venv git certbot python3-certbot-nginx
```

기본 Nginx 사이트는 80 포트를 먼저 차지하므로 지웁니다.

```bash
sudo rm -f /etc/nginx/sites-enabled/default
```

DB와 역할을 만듭니다. 비밀번호 자리에 직접 정한 값을 넣습니다.

```bash
sudo -u postgres psql -c "CREATE ROLE jobtrend LOGIN PASSWORD '<비밀번호>';"
sudo -u postgres psql -c "CREATE DATABASE jobtrend OWNER jobtrend;"
```

실행 사용자와 코드를 준비합니다. `<저장소 URL>`은 이 저장소의 clone 주소이고, 브랜치는 배포할 것(예: `mvp-db-api` 또는 `main`)입니다.

```bash
sudo useradd --system --home /opt/job-trend-mcp --shell /usr/sbin/nologin jobtrend
sudo git clone <저장소 URL> /opt/job-trend-mcp
sudo chown -R jobtrend:jobtrend /opt/job-trend-mcp
sudo -u jobtrend python3 -m venv /opt/job-trend-mcp/.venv
sudo -u jobtrend /opt/job-trend-mcp/.venv/bin/pip install -e /opt/job-trend-mcp
```

환경 파일을 만듭니다. `deploy/env.example`을 복사해 `<비밀번호>`와 `<도메인>`을 채웁니다.

```bash
sudo mkdir -p /etc/job-trend
sudo cp /opt/job-trend-mcp/deploy/env.example /etc/job-trend/env
sudo nano /etc/job-trend/env
sudo chown root:root /etc/job-trend/env
sudo chmod 600 /etc/job-trend/env
```

마이그레이션을 돌립니다. 환경 파일은 root만 읽으므로 변수를 불러서 실행합니다.

```bash
sudo bash -c 'set -a; . /etc/job-trend/env; set +a; cd /opt/job-trend-mcp && sudo -E -u jobtrend .venv/bin/python -m src.db.migrate'
```

확인:

```bash
sudo -u postgres psql -d jobtrend -c '\dt'    # 테이블 4개
```

## 5. 데이터 적재

내 컴퓨터에서 스냅샷 tar를 올립니다. `<스냅샷.tar.gz>`는 8월 스냅샷 아카이브 파일입니다.

```bash
scp <스냅샷.tar.gz> ubuntu@<탄력적 IP>:/tmp/snapshot.tar.gz
```

서버에서 적재합니다.

```bash
sudo bash -c 'set -a; . /etc/job-trend/env; set +a; cd /opt/job-trend-mcp && sudo -E -u jobtrend .venv/bin/python scripts/backfill_snapshot.py --archive /tmp/snapshot.tar.gz'
```

확인: 마지막 줄이 `postings=659 observations=1155`. 다시 돌려도 같다.

## 6. 서비스 등록

```bash
sudo cp /opt/job-trend-mcp/deploy/systemd/job-trend-api.service /etc/systemd/system/
sudo cp /opt/job-trend-mcp/deploy/systemd/job-trend-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now job-trend-api job-trend-mcp
```

로그는 `journalctl -u job-trend-api -u job-trend-mcp -f`로 봅니다.

확인:

```bash
curl -s 127.0.0.1:8001/healthz                          # "postings": 659
systemctl is-active job-trend-api job-trend-mcp         # 둘 다 active
sudo reboot                                             # 재접속 뒤 위 두 명령이 같은 결과
```

## 7. 도메인 · HTTPS

1. 도메인 DNS에 A 레코드를 만들어 `<도메인>`이 `<탄력적 IP>`를 가리키게 합니다. 전파를 기다립니다.
2. Nginx 설정을 복사하고 `example.com`을 `<도메인>`으로 바꿉니다.

```bash
sudo cp /opt/job-trend-mcp/deploy/nginx/job-trend.conf /etc/nginx/conf.d/job-trend.conf
sudo sed -i 's/example\.com/<도메인>/' /etc/nginx/conf.d/job-trend.conf
sudo nginx -t
sudo systemctl reload nginx
```

이 파일은 80 포트 설정과 IP별 요청 제한(`limit_req_zone`)만 갖고 있습니다. 443 · TLS 블록은 다음 명령이 파일에 붙입니다.

```bash
sudo certbot --nginx -d <도메인>
```

확인(내 컴퓨터에서):

```bash
curl -s https://<도메인>/healthz                                                   # 200
curl -s "https://<도메인>/api/v1/postings?job_function=Backend%20Engineer&limit=1"  # items 1개
curl -s -o /dev/null -w '%{http_code}' https://<도메인>/                            # 404
for i in $(seq 100); do curl -s -o /dev/null -w '%{http_code}\n' "https://<도메인>/api/v1/postings?limit=1"; done | sort | uniq -c   # 429가 섞여 나온다
```

## 8. 공개 MCP 확인 (ngrok 없이)

Claude 웹 커스텀 커넥터의 URL을 `https://<도메인>/mcp`로 바꿉니다. 지금 등록된 것은 옛 ngrok 주소라 404가 나옵니다. "백엔드 공고에서 많이 요구하는 스킬"을 물어 `get_skill_trend`가 호출되는지 봅니다.

421이 나오면 `/etc/job-trend/env`의 `MCP_ALLOWED_HOSTS`가 `<도메인>`과 같은지 확인하고 `sudo systemctl restart job-trend-mcp` 합니다. 자세한 내용은 [HANDOFF.md](../HANDOFF.md)의 421 절을 봅니다.

## 9. 마무리

[manual-pain-log.md](manual-pain-log.md)에 시작 · 끝 시각과 불편했던 점을 정리하고 커밋합니다(`EC2 수동 구축 기록을 남긴다`).
