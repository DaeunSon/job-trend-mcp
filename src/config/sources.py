"""
crawl_sources 시딩 데이터.
실제 DB가 도입되면 이 딕셔너리를 INSERT 스크립트로 변환한다.
"""
from src.models.schemas import CrawlSource

JOBKOREA_SOURCE = CrawlSource(
    source_name="jobkorea",
    base_url="https://www.jobkorea.co.kr",
    source_type="WEB_CRAWLING",
    robots_txt_url="https://www.jobkorea.co.kr/robots.txt",
    legal_risk_level="HIGH",
    rate_limit_policy=(
        "요청 간 2~3초 랜덤 간격, 동시 요청 1개 — "
        "robots.txt가 /Search/ 경로의 자동화된 접근을 차단하고 있으므로 "
        "특히 보수적으로 운영할 것. 상업적 용도 사용 전 법무 검토 필요."
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

SARAMIN_SOURCE = CrawlSource(
    source_name="saramin",
    base_url="https://www.saramin.co.kr",
    source_type="WEB_CRAWLING",
    robots_txt_url="https://www.saramin.co.kr/robots.txt",
    legal_risk_level="LOW",
    rate_limit_policy=(
        "요청 간 1~2초 랜덤 간격, 동시 요청 1개, 페이지당 40건 — "
        "robots.txt 차단 없음 확인. 차단 징후 감지 시 즉시 중단 후 로그 남길 것."
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

WANTED_SOURCE = CrawlSource(
    source_name="wanted",
    base_url="https://www.wanted.co.kr",
    source_type="WEB_CRAWLING",
    robots_txt_url="https://www.wanted.co.kr/robots.txt",
    legal_risk_level="LOW",
    rate_limit_policy=(
        "요청 간 0.5~1.5초 랜덤 간격, 동시 요청 1개 — "
        "내부 JSON API 직접 호출 방식(인증 불필요 확인, 2026-07-27). "
        "Selenium 미사용. 직무 전환 간 2~4초 추가 대기. "
        "차단 감지(4xx 연속) 시 지수 백오프 후 중단."
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

# Remotive는 크롤링이 아닌 공식 공개 API를 사용하므로 source_type="API".
# 이용약관: https://remotive.com/api-documentation
#   - 분당 2회 초과 금지, 하루 4회 권장
#   - Jooble·Google Jobs·LinkedIn Jobs 등 제3자 채용 사이트 재게시 금지
#   - Remotive 출처 표기 및 원문 URL 링크 의무 (source_name·original_url 필드로 자동 충족)
REMOTIVE_SOURCE = CrawlSource(
    source_name="remotive",
    base_url="https://remotive.com",
    source_type="API",
    robots_txt_url=None,
    legal_risk_level="LOW",
    rate_limit_policy=(
        "분당 2회 초과 금지, 하루 최대 4회 권장 — 공식 공개 API 이용약관 명시. "
        "호출 간 최소 35초 간격 유지. "
        "Jooble·Google Jobs·LinkedIn Jobs 등 제3자 채용 사이트 재게시 금지. "
        "인증 불필요(API 키·회원가입 없음). "
        "공고 데이터는 24시간 지연 노출되므로 더 자주 호출해도 실익 없음."
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

# 점핏은 사람인의 개발자 특화 채용 플랫폼(saramin.co.kr 계열).
# 목록 페이지(/positions)는 CSR이지만 별도 백엔드 서버
# https://jumpit-api.saramin.co.kr 에서 인증 없이 JSON API 제공 확인 (2026-07-28).
# robots.txt: /positions, /position/ 경로 허용 확인.
JUMPIT_SOURCE = CrawlSource(
    source_name="jumpit",
    base_url="https://jumpit.saramin.co.kr",
    source_type="WEB_CRAWLING",
    robots_txt_url="https://jumpit.saramin.co.kr/robots.txt",
    legal_risk_level="LOW",
    rate_limit_policy=(
        "요청 간 1~2초 랜덤 간격, 동시 요청 1개 — "
        "내부 JSON API 직접 호출 방식 (https://jumpit-api.saramin.co.kr). "
        "인증 불필요 확인(2026-07-28). Selenium 미사용. "
        "카테고리 전환 간 2~4초 추가 대기. "
        "robots.txt: /positions, /position/ 경로 허용, GPTBot은 전체 차단."
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

# 랠릿은 Next.js SSR 사이트이나, 내부 JSON API(https://www.rallit.com/client/api/v1/position)가
# 인증 없이 공개 접근 가능함을 확인 (2026-07-29).
# 목록/상세 모두 API로 수집 — Selenium 미사용.
# robots.txt: /positions 경로 허용 확인.
# 총 공고 수 ~501건(소규모 플랫폼) — keyword 파라미터로 필터링.
RALLIT_SOURCE = CrawlSource(
    source_name="rallit",
    base_url="https://www.rallit.com",
    source_type="WEB_CRAWLING",
    robots_txt_url="https://www.rallit.com/robots.txt",
    legal_risk_level="LOW",
    rate_limit_policy=(
        "요청 간 1~2초 랜덤 간격, 동시 요청 1개 — "
        "내부 JSON API 직접 호출 방식 (https://www.rallit.com/client/api/v1/position). "
        "인증 불필요 확인(2026-07-29). Selenium 미사용. "
        "직무 전환 간 2~4초 추가 대기. "
        "job 파라미터 미작동 확인, keyword 파라미터가 실질적 필터 역할."
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

# The Muse는 공식 공개 API를 사용하므로 source_type="API".
# 이용약관: https://www.themuse.com/developers/api/v2/terms
#   - 미등록 기준 시간당 500건, 등록 시 시간당 3600건
#   - X-Ratelimit-Remaining 헤더로 잔여 호출 한도 실시간 확인 가능
#   - 상업적 재배포 및 제3자 채용 플랫폼 재게시 금지
#   - 출처 표기 및 원문 URL 링크 권장 (source_name·original_url 필드로 자동 충족)
THEMUSE_SOURCE = CrawlSource(
    source_name="themuse",
    base_url="https://www.themuse.com",
    source_type="API",
    robots_txt_url=None,
    legal_risk_level="LOW",
    rate_limit_policy=(
        "미등록 기준 시간당 500건, 등록 시 시간당 3600건 — 공식 공개 API 이용약관 명시. "
        "응답 헤더 X-Ratelimit-Remaining으로 잔여 한도 실시간 확인. "
        "잔여 한도 50건 미만 시 자동 대기(X-Ratelimit-Reset 기준). "
        "호출 간 최소 1초 간격 유지 (시간당 500건 이내 준수). "
        "상업적 재배포 및 제3자 채용 플랫폼 재게시 금지 (내부 트렌드 분석 전용). "
        "이용약관 전문: https://www.themuse.com/developers/api/v2/terms"
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

# Arbeitnow는 공식 공개 API를 사용하므로 source_type="API".
# 이용약관 (응답 meta.terms / https://www.arbeitnow.com/blog/job-board-api):
#   - 남용 금지, 분당 수 회 수준으로 보수적으로 호출
#   - arbeitnow.com 백링크 제공 의무 (source_name·original_url 필드로 자동 충족)
#   - Jooble·Neuvoo·Google Jobs·LinkedIn Jobs 등 제3자 사이트로 재게시 금지
#   - API는 as-is 제공 — 가용성·정확성 보장 없음, 사전 통지 없이 접근 권한 회수 가능
#   - 인증 불필요(API 키·회원가입 없음)
ARBEITNOW_SOURCE = CrawlSource(
    source_name="arbeitnow",
    base_url="https://www.arbeitnow.com",
    source_type="API",
    robots_txt_url=None,
    legal_risk_level="LOW",
    rate_limit_policy=(
        "분당 수 회 수준으로 보수적으로 호출 (호출 간 최소 20초 간격) — "
        "공식 API as-is 제공, 남용 금지. "
        "arbeitnow.com 백링크 제공 의무 (source_name·original_url로 충족). "
        "Jooble·Neuvoo·Google Jobs·LinkedIn Jobs 등 제3자 채용 사이트 재게시 금지. "
        "인증 불필요(API 키·회원가입 없음). "
        "참고: https://www.arbeitnow.com/blog/job-board-api"
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

# USAJobs는 웹 크롤링(내부 JSON API) 방식.
# 0단계 조사 (2026-07-30):
#   - /search?k=... 초기 HTML에는 공고가 없고, searchmain.js가
#     POST /Search/ExecuteSearch 로 결과를 채움 (인증/API 키 불필요).
#   - GET /Search/Results 로 세션 쿠키(akavpau_usajobs)를 시드한 뒤
#     동일 requests.Session 으로 POST 해야 함. 세션 분리 시 실패 가능.
#   - Akamai가 봇성 UA에 403을 줄 수 있음 → 아래 user_agent 문자열은
#     2026-07-30 실측 성공값. 임의 변경 금지 (크롤러도 이 값을 그대로 사용).
USAJOBS_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

USAJOBS_SOURCE = CrawlSource(
    source_name="usajobs",
    base_url="https://www.usajobs.gov",
    source_type="WEB_CRAWLING",
    robots_txt_url="https://www.usajobs.gov/robots.txt",
    legal_risk_level="LOW",
    rate_limit_policy=(
        "요청 간 1~2초 랜덤 간격, 동시 요청 1개 — "
        "내부 JSON API 직접 호출 (POST /Search/ExecuteSearch). "
        "동일 Session으로 GET /Search/Results 쿠키 시드 후 POST 필수. "
        "인증/API 키 불필요 확인(2026-07-30). Selenium 미사용. "
        "직무·키워드 전환 간 2~4초 추가 대기. "
        "User-Agent는 USAJOBS_USER_AGENT 고정값 사용 (Akamai 봇 UA 403 대비)."
    ),
    user_agent=USAJOBS_USER_AGENT,
    is_active=True,
)

# 고용24(work24.go.kr) — 고용노동부 공공 취업 포털.
# 웹 크롤링(HTML) 방식. 검색 POST + 상세 GET.
# robots.txt: 채용검색/상세 경로 허용 확인(2026-07-30).
# 사람인·잡코리아·원티드 재게시분은 infoTypeCd/siteClcd 로 제외한다.
WORK24_SOURCE = CrawlSource(
    source_name="work24",
    base_url="https://www.work24.go.kr",
    source_type="WEB_CRAWLING",
    robots_txt_url="https://www.work24.go.kr/robots.txt",
    legal_risk_level="LOW",
    rate_limit_policy=(
        "요청 간 1.5~3초 랜덤 간격, 동시 요청 1개 — "
        "공공 포털 HTML 크롤링(검색 POST /wk/a/b/1200/retriveDtlEmpSrchList.do, "
        "상세 GET /wk/a/b/1500/empDetailAuthView.do). "
        "검색어는 srcKeyword 필드 사용(keyword 단독 시 필터 미적용). "
        "사람인·잡코리아·원티드 재게시분은 infoTypeCd 제외 필터로 스킵. "
        "차단 징후 감지 시 즉시 중단 후 로그 남길 것."
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

# Adzuna — 공식 API 미사용. 국가별 공개 HTML(SERP + /jobs/details) 크롤.
# www.adzuna.com(US) 는 Human Verification — gb(.co.uk)·au(.com.au) 위주.
ADZUNA_SOURCE = CrawlSource(
    source_name="adzuna",
    base_url="https://www.adzuna.co.uk",
    source_type="WEB_CRAWLING",
    robots_txt_url="https://www.adzuna.co.uk/robots.txt",
    legal_risk_level="MEDIUM",
    rate_limit_policy=(
        "HTML 크롤 — SERP/상세 요청 간 0.8~2.5초 랜덤 딜레이. "
        "429·CAPTCHA(405) 감지 시 배치 즉시 중단. "
        "US(www.adzuna.com) 는 수집 대상에서 제외."
    ),
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    is_active=True,
)

# 잡플래닛 / LinkedIn / 로켓펀치 — 프로젝트 범위에서 제외 (2026-08-03).
#   - 잡플래닛: AI 학습·무단 수집 금지 고지
#   - LinkedIn: robots·파트너 승인제
#   - 로켓펀치: 이용약관상 고위험
# ALL_SOURCES 에 등록하지 않으며 크롤러도 추가하지 않는다.

# 사이트가 추가될 때 이 목록에 append한다.
ALL_SOURCES: list[CrawlSource] = [
    JOBKOREA_SOURCE,
    SARAMIN_SOURCE,
    WANTED_SOURCE,
    REMOTIVE_SOURCE,
    JUMPIT_SOURCE,
    RALLIT_SOURCE,
    THEMUSE_SOURCE,
    ARBEITNOW_SOURCE,
    USAJOBS_SOURCE,
    WORK24_SOURCE,
    ADZUNA_SOURCE,
]
