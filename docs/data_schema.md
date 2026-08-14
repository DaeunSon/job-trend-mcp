# 데이터 스키마

작성 기준: `src/models/schemas.py`, `src/storage/json_writer.py`, `src/taxonomy/*.py` (2026-08-10).

> **이 문서가 스키마의 최신 기준입니다.**  
> `docs/crawling_sprint_summary.md` 등 예전 기록에 직군 12개·직무 47개·레거시 경로만
> 언급된 부분이 있어도, **지금 코드와 다르면 이 문서를 따르세요.** 

DB는 미확정입니다. 현재는 로컬 JSON으로 저장하며, DB 전환 시 `json_writer.py` /
`alias_resolver.py`의 저장·로드 구현만 교체하도록 분리되어 있습니다.

---

## 컬렉션 개요

| 컬렉션 | 코드 모델 | 실제 저장 |
|--------|-----------|-----------|
| `raw_job_postings` | `RawJobPosting` | `data/raw_job_postings/...` |
| `job_postings` | `JobPosting` (+ 중첩 dataclass) | `data/job_postings/...` |
| `crawl_sources` | `CrawlSource` | 시딩 데이터 `src/config/sources.py`의 `ALL_SOURCES` (JSON 컬렉션 파일 아님) |
| `normalization_aliases` | `NormalizationAlias` | `data/normalization_aliases.json` (리스트) |

아래 **필수**는 dataclass에서 기본값이 없는 필드입니다.  
`field(default_factory=...)` / `= None` / `= "ACTIVE"` 등은 선택(또는 자동 채움)입니다.

---

## 1. `raw_job_postings` (`RawJobPosting`)

원문 보존용. 파서를 고쳐도 raw를 다시 파싱할 수 있습니다.

| 필드 | 타입 | 필수 | 의미 |
|------|------|------|------|
| `source_name` | `str` | 예 | 출처 사이트 키 (예: `wanted`) |
| `source_job_id` | `str` | 예 | 사이트 측 공고 ID |
| `original_url` | `str` | 예 | 원문 URL |
| `raw_html` | `str` | 예 | HTML 원문 (JSON API면 빈 문자열일 수 있음) |
| `raw_text` | `str` | 예 | 텍스트/JSON 원문 |
| `id` | `str` | 자동 | UUID |
| `collected_at` | `str` | 자동 | 수집 시각 (ISO UTC) |
| `parse_status` | `str` | 기본 `PENDING` | `PENDING` / `PARSED` / `FAILED` |
| `parsed_job_posting_id` | `str \| None` | 아니오 | 파싱 결과 job_posting id |

---

## 2. `job_postings` (`JobPosting`)

표준화된 채용공고. MCP가 조회하는 주 데이터입니다.

### 최상위 필드

| 필드 | 타입 | 필수 | 의미 |
|------|------|------|------|
| `source_name` | `str` | 예 | 출처 |
| `source_job_id` | `str` | 예 | 출처 공고 ID |
| `original_url` | `str` | 예 | 원문 URL |
| `title` | `str` | 예 | 원문 제목 |
| `normalized_title` | `str` | 예 | 정규화 제목 |
| `description` | `str` | 예 | 본문 |
| `company` | `CompanyInfo` | 예 | 회사 정보 |
| `job_category_name` | `str` | 예 | 표준 직군 |
| `job_function_name` | `str` | 예 | 표준 직무 |
| `career_level` | `CareerLevel` | 예 | 경력 수준 |
| `employment_type_name` | `str` | 예 | 고용 형태 |
| `location` | `LocationInfo` | 예 | 근무지 |
| `skills` | `list[SkillTag]` | 예 | 스킬 태그 목록 |
| `salary` | `SalaryInfo` | 예 | 급여 |
| `source_refs` | `list[SourceRef]` | 예 | 출처 참조 |
| `posted_at` | `str` | 예 | 게시일 (ISO date 문자열) |
| `first_collected_at` | `str` | 예 | 최초 수집 |
| `last_seen_at` | `str` | 예 | 마지막 확인 |
| `created_at` | `str` | 예 | 문서 생성 |
| `updated_at` | `str` | 예 | 문서 갱신 |
| `id` | `str` | 자동 | UUID |
| `education_level` | `str \| None` | 아니오 | 학력 |
| `work_arrangement` | `str \| None` | 아니오 | `ONSITE` / `REMOTE` / `HYBRID` |
| `expires_at` | `str \| None` | 아니오 | 마감일 |
| `crawl_status` | `str` | 기본 `ACTIVE` | `ACTIVE` / `EXPIRED` / `DELETED` / `BLOCKED` |

### 중첩: `CompanyInfo`

| 필드 | 타입 | 필수 |
|------|------|------|
| `name` | `str` | 예 |
| `raw_name` | `str` | 예 |
| `registered_name` | `str \| None` | 아니오 |
| `industry_name` | `str \| None` | 아니오 |
| `size_category` | `str \| None` | 아니오 |
| `headquarters_country` | `str \| None` | 아니오 |
| `headquarters_region` | `str \| None` | 아니오 |
| `headquarters_city` | `str \| None` | 아니오 |
| `website_url` | `str \| None` | 아니오 |

### 중첩: `CareerLevel`

| 필드 | 타입 | 필수 |
|------|------|------|
| `label` | `str` | 예 |
| `min_years` | `int \| None` | 아니오 |
| `max_years` | `int \| None` | 아니오 |

### 중첩: `LocationInfo`

| 필드 | 타입 | 필수 |
|------|------|------|
| `country_name` | `str` | 예 |
| `city_name` | `str` | 예 |
| `raw_text` | `str` | 예 |
| `region_name` | `str \| None` | 아니오 |

### 중첩: `SkillTag`

| 필드 | 타입 | 필수 |
|------|------|------|
| `raw_text` | `str` | 예 |
| `canonical_name` | `str` | 예 |
| `category_name` | `str \| None` | 아니오 |

### 중첩: `SalaryInfo`

| 필드 | 타입 | 필수 | 비고 |
|------|------|------|------|
| `raw_text` | `str \| None` | 아니오 | |
| `min_amount` | `str \| None` | 아니오 | Decimal을 문자열로 보관 |
| `max_amount` | `str \| None` | 아니오 | |
| `currency_code` | `str \| None` | 아니오 | |
| `pay_period` | `str \| None` | 아니오 | `HOURLY` / `MONTHLY` / `ANNUAL` |

### 중첩: `SourceRef`

| 필드 | 타입 | 필수 |
|------|------|------|
| `source_name` | `str` | 예 |
| `source_job_id` | `str` | 예 |
| `original_url` | `str` | 예 |
| `collected_at` | `str` | 예 |

정규화 진입점: `src/normalization/posting_normalizer.py`의 `build_job_posting()`.

---

## 3. `crawl_sources` (`CrawlSource`)

| 필드 | 타입 | 필수 | 의미 |
|------|------|------|------|
| `source_name` | `str` | 예 | 사이트 키 |
| `base_url` | `str` | 예 | 기본 URL |
| `id` | `str` | 자동 | UUID |
| `source_type` | `str` | 기본 `WEB_CRAWLING` | `WEB_CRAWLING` / `API` |
| `robots_txt_url` | `str \| None` | 아니오 | |
| `legal_risk_level` | `str` | 기본 `MEDIUM` | `LOW` / `MEDIUM` / `HIGH` |
| `rate_limit_policy` | `str` | 기본 `""` | 운영 정책 설명 |
| `user_agent` | `str` | 기본 `""` | |
| `last_crawled_at` | `str \| None` | 아니오 | |
| `is_active` | `bool` | 기본 `True` | 자동 수집 대상 여부 |

시딩 목록: `src/config/sources.py` → `ALL_SOURCES` (11개, 전부 active).

---

## 4. `normalization_aliases` (`NormalizationAlias`)

| 필드 | 타입 | 필수 | 의미 |
|------|------|------|------|
| `alias_type` | `str` | 예 | `COMPANY` / `SKILL` / `LOCATION` 등 |
| `raw_text` | `str` | 예 | 원문 표기 |
| `canonical_name` | `str` | 예 | 표준값 |
| `id` | `str` | 자동 | UUID |
| `source_name` | `str \| None` | 아니오 | 출처 한정 alias |
| `match_method` | `str` | 기본 `MANUAL` | `EXACT` / `FUZZY` / `MANUAL` / `EMBEDDING` |

파일: `data/normalization_aliases.json`.  
조회: `src/normalization/alias_resolver.py` (JSON → 내장 seed → MANUAL 후보).

---

## 저장 경로 규칙

### 현재(신규) 레이아웃

```
data/{collection}/{job_function_name}/{source_name}/{crawl_date}_{source_job_id}.json
```

예:

```
data/job_postings/Backend Engineer/jumpit/2026-08-01_54645855.json
```

- 직무명에 `/`가 있으면 폴더명에서 `.`으로 치환  
  (`sanitize_job_function_dirname`, 예: `QA / Test Engineer` → `QA . Test Engineer`)
- 날짜는 **폴더가 아니라 파일명 접두사**

### 레거시 레이아웃 (공존)

```
data/{collection}/{crawl_date}/{filename}.json
```

마이그레이션하지 않습니다. `load_all_documents_in_collection` / `iter_collection_json_files`는
`rglob("*.json")`으로 **양쪽을 모두** 읽습니다.

`crawl_sources`는 파일 컬렉션이 아니라 `sources.py` 시딩입니다.  
`normalization_aliases`는 단일 JSON 파일입니다.

---

## Taxonomy 현황 (코드 실측)

| 항목 | 파일 | 개수 |
|------|------|------|
| 표준 직군 (`JOB_CATEGORIES`) | `taxonomy/job_categories.py` | **15** |
| 표준 직무 (`JOB_FUNCTIONS`) | `taxonomy/job_functions.py` | **53** |
| 표준 스킬 (`SKILLS` / `get_skill_names()`) | `taxonomy/skills.py` | **91** |

부가:

- `SKILL_SEEDS` (skills.py 내장 seed 맵): **192**
- `data/normalization_aliases.json` 항목 수(로컬 실측): **3222** (환경에 따라 달라질 수 있음)

직군 목록:

1. Engineering & Technology  
2. Data & Analytics  
3. Product & Design  
4. Marketing & Growth  
5. Finance & Accounting  
6. Operations & Strategy  
7. Human Resources  
8. Sales & Business Development  
9. Legal & Compliance  
10. Research & Science  
11. Customer Success  
12. Education & Training  
13. Supply Chain & Logistics  
14. Healthcare  
15. Other  

고용형태·경력 표준값은 각각 `taxonomy/employment_types.py`, `taxonomy/career_levels.py`에 있습니다.
