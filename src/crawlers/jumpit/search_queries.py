"""
점핏 전용 직무 카테고리 매핑.

구조
----
JUMPIT_SEARCH_QUERIES: dict[str, list[int]]
  키 : taxonomy/job_functions.py 의 표준 job_function_name 값
  값 : 점핏 내부 API jobCategory ID 목록

점핏 API 방식 (0단계 조사 결과 — 2026-07-28 확인)
-------------------------------------------------
점핏 /positions 목록 페이지는 CSR 렌더링이지만,
별도 백엔드 서버 https://jumpit-api.saramin.co.kr 에서
인증 없이 JSON API가 공개 접근 가능함을 확인.

  목록 API : GET https://jumpit-api.saramin.co.kr/api/positions
              파라미터: sort=createdAt|popular, page=N, jobCategory=ID, size=N
              → 인증 없이 JSON 응답 확인

  카테고리 : GET https://jumpit-api.saramin.co.kr/api/common/code-initialize
              result.jobCategory 배열 내 {id, name} 구조로 반환

jobCategory ID 목록 (2026-07-28 /api/common/code-initialize 기준)
------------------------------------------------------------------
  1  : 서버/백엔드 개발자
  2  : 프론트엔드 개발자
  3  : 웹 풀스택 개발자
  4  : 안드로이드 개발자
  5  : 게임 클라이언트 개발자
  6  : 게임 서버 개발자
  7  : DBA
  8  : 인공지능/머신러닝
  9  : devops/시스템 엔지니어
  10 : 정보보안 담당자
  11 : QA 엔지니어
  12 : 개발 PM
  13 : HW/임베디드
  15 : SW/솔루션
  16 : iOS 개발자
  17 : 웹퍼블리셔
  18 : 크로스플랫폼 앱개발자
  19 : 빅데이터 엔지니어
  20 : VR/AR/3D
  21 : 기술지원
  22 : 블록체인
"""
from __future__ import annotations

# ── 점핏 jobCategory ID 상수 (가독성용) ───────────────────────────────────────
_BACKEND          = 1     # 서버/백엔드 개발자
_FRONTEND         = 2     # 프론트엔드 개발자
_FULLSTACK        = 3     # 웹 풀스택 개발자
_ANDROID          = 4     # 안드로이드 개발자
_GAME_CLIENT      = 5     # 게임 클라이언트 개발자
_GAME_SERVER      = 6     # 게임 서버 개발자
_DBA              = 7     # DBA
_AI_ML            = 8     # 인공지능/머신러닝
_DEVOPS           = 9     # devops/시스템 엔지니어
_SECURITY         = 10    # 정보보안 담당자
_QA               = 11    # QA 엔지니어
_DEV_PM           = 12    # 개발 PM
_HW_EMBEDDED      = 13    # HW/임베디드
_SW_SOLUTION      = 15    # SW/솔루션
_IOS              = 16    # iOS 개발자
_WEB_PUBLISHER    = 17    # 웹퍼블리셔
_CROSSPLATFORM    = 18    # 크로스플랫폼 앱개발자
_BIGDATA          = 19    # 빅데이터 엔지니어
_VR_AR_3D         = 20    # VR/AR/3D
_TECH_SUPPORT     = 21    # 기술지원
_BLOCKCHAIN       = 22    # 블록체인


# ── 메인 매핑 ─────────────────────────────────────────────────────────────────

JUMPIT_SEARCH_QUERIES: dict[str, list[int]] = {
    # ── Engineering & Technology ─────────────────────────────────────────────
    "Software Engineer":            [_BACKEND, _FULLSTACK, _SW_SOLUTION],
    "Backend Engineer":             [_BACKEND],
    "Frontend Engineer":            [_FRONTEND],
    "Full Stack Engineer":          [_FULLSTACK],
    "Mobile Engineer":              [_ANDROID, _IOS, _CROSSPLATFORM],
    "DevOps / Platform Engineer":   [_DEVOPS],
    "Site Reliability Engineer":    [_DEVOPS],
    "Security Engineer":            [_SECURITY],
    "QA / Test Engineer":           [_QA],
    "Embedded / Hardware Engineer": [_HW_EMBEDDED],
    # ── Data & Analytics ─────────────────────────────────────────────────────
    "Machine Learning Engineer":    [_AI_ML],
    "Data Engineer":                [_BIGDATA],
    "Data Scientist":               [_AI_ML, _BIGDATA],
    "Data Analyst":                 [_BIGDATA],
    "AI Researcher":                [_AI_ML],
    "Business Intelligence Analyst":[_BIGDATA, _DBA],
    # 데이터 라벨링 전용 카테고리 없음 → AI/ML 카테고리로 근접 수집
    "Data Labeling / Annotation Specialist": [_AI_ML],
    # ── Product & Design ─────────────────────────────────────────────────────
    # 점핏에 디자인 카테고리가 없어 빈 리스트 (키만 등록해 taxonomy 정렬 유지)
    "Product Manager":              [_DEV_PM],
    "UX Designer":                  [],
    "UI Designer":                  [],
    "Product Designer":             [],
    "UX Researcher":                [],
    # ── Technical Support ────────────────────────────────────────────────────
    "Technical Support Engineer":   [_TECH_SUPPORT],
    # ── 비표준 키 (taxonomy 외, 점핏 전용 카테고리) ───────────────────────────
    "Game Developer":               [_GAME_CLIENT, _GAME_SERVER],
    "Blockchain Developer":         [_BLOCKCHAIN],
    # 교육·물류·헬스케어 등은 점핏 IT 전용 카탈로그에 카테고리가 없어 미매핑.
}


# ── 한글 직무명 → taxonomy 직무명 별칭 ─────────────────────────────────────────
KOREAN_ALIASES: dict[str, str] = {
    "소프트웨어 엔지니어":      "Software Engineer",
    "소프트웨어 개발자":        "Software Engineer",
    "백엔드 개발자":            "Backend Engineer",
    "백엔드 엔지니어":          "Backend Engineer",
    "서버 개발자":              "Backend Engineer",
    "서버/백엔드 개발자":       "Backend Engineer",
    "프론트엔드 개발자":        "Frontend Engineer",
    "프론트엔드 엔지니어":      "Frontend Engineer",
    "풀스택 개발자":            "Full Stack Engineer",
    "웹 풀스택 개발자":         "Full Stack Engineer",
    "모바일 개발자":            "Mobile Engineer",
    "ios 개발자":               "Mobile Engineer",
    "안드로이드 개발자":        "Mobile Engineer",
    "크로스플랫폼 앱개발자":    "Mobile Engineer",
    "devops 엔지니어":          "DevOps / Platform Engineer",
    "devops/시스템 엔지니어":   "DevOps / Platform Engineer",
    "클라우드 엔지니어":        "DevOps / Platform Engineer",
    "인프라 엔지니어":          "DevOps / Platform Engineer",
    "sre":                      "Site Reliability Engineer",
    "보안 엔지니어":            "Security Engineer",
    "정보보안 담당자":          "Security Engineer",
    "qa 엔지니어":              "QA / Test Engineer",
    "테스트 엔지니어":          "QA / Test Engineer",
    "임베디드 개발자":          "Embedded / Hardware Engineer",
    "hw/임베디드":              "Embedded / Hardware Engineer",
    "하드웨어 엔지니어":        "Embedded / Hardware Engineer",
    "머신러닝 엔지니어":        "Machine Learning Engineer",
    "인공지능/머신러닝":        "Machine Learning Engineer",
    "ml 엔지니어":              "Machine Learning Engineer",
    "데이터 엔지니어":          "Data Engineer",
    "빅데이터 엔지니어":        "Data Engineer",
    "데이터 사이언티스트":      "Data Scientist",
    "데이터 분석가":            "Data Analyst",
    "ai 연구원":                "AI Researcher",
    "프로덕트 매니저":          "Product Manager",
    "개발 pm":                  "Product Manager",
    "pm":                       "Product Manager",
    "서비스 기획자":            "Product Manager",
    "ux 디자이너":              "UX Designer",
    "ui 디자이너":              "UI Designer",
    "게임 개발자":              "Game Developer",
    "게임 클라이언트 개발자":   "Game Developer",
    "게임 서버 개발자":         "Game Developer",
    "기술지원":                 "Technical Support Engineer",
    "블록체인":                 "Blockchain Developer",
}


# ── 점핏 카테고리명 → taxonomy 직무명 역매핑 ──────────────────────────────────
JUMPIT_CATEGORY_TO_FUNCTION: dict[str, str] = {
    "서버/백엔드 개발자":       "Backend Engineer",
    "프론트엔드 개발자":        "Frontend Engineer",
    "웹 풀스택 개발자":         "Full Stack Engineer",
    "안드로이드 개발자":        "Mobile Engineer",
    "iOS 개발자":               "Mobile Engineer",
    "크로스플랫폼 앱개발자":    "Mobile Engineer",
    "게임 클라이언트 개발자":   "Game Developer",
    "게임 서버 개발자":         "Game Developer",
    "DBA":                      "Business Intelligence Analyst",
    "인공지능/머신러닝":        "Machine Learning Engineer",
    "devops/시스템 엔지니어":   "DevOps / Platform Engineer",
    "정보보안 담당자":          "Security Engineer",
    "QA 엔지니어":              "QA / Test Engineer",
    "개발 PM":                  "Product Manager",
    "HW/임베디드":              "Embedded / Hardware Engineer",
    "SW/솔루션":                "Software Engineer",
    "웹퍼블리셔":               "Frontend Engineer",
    "빅데이터 엔지니어":        "Data Engineer",
    "VR/AR/3D":                 "Software Engineer",
    "기술지원":                 "Technical Support Engineer",
    "블록체인":                 "Blockchain Developer",
}


# ── 점핏 카테고리명 → job_category_name 매핑 ──────────────────────────────────
JUMPIT_CATEGORY_TO_JOB_CATEGORY: dict[str, str] = {
    "서버/백엔드 개발자":       "Engineering & Technology",
    "프론트엔드 개발자":        "Engineering & Technology",
    "웹 풀스택 개발자":         "Engineering & Technology",
    "안드로이드 개발자":        "Engineering & Technology",
    "iOS 개발자":               "Engineering & Technology",
    "크로스플랫폼 앱개발자":    "Engineering & Technology",
    "게임 클라이언트 개발자":   "Engineering & Technology",
    "게임 서버 개발자":         "Engineering & Technology",
    "DBA":                      "Data & Analytics",
    "인공지능/머신러닝":        "Data & Analytics",
    "devops/시스템 엔지니어":   "Engineering & Technology",
    "정보보안 담당자":          "Engineering & Technology",
    "QA 엔지니어":              "Engineering & Technology",
    "개발 PM":                  "Product & Design",
    "HW/임베디드":              "Engineering & Technology",
    "SW/솔루션":                "Engineering & Technology",
    "웹퍼블리셔":               "Engineering & Technology",
    "빅데이터 엔지니어":        "Data & Analytics",
    "VR/AR/3D":                 "Engineering & Technology",
    "기술지원":                 "Engineering & Technology",
    "블록체인":                 "Engineering & Technology",
}


# ── 공개 유틸 ─────────────────────────────────────────────────────────────────

def get_category_ids_for_function(function_name: str) -> list[int]:
    """
    taxonomy 직무명(영문) 또는 한글 별칭에 매핑된 점핏 jobCategory ID 목록을 반환한다.
    """
    ids = JUMPIT_SEARCH_QUERIES.get(function_name)
    if ids is not None:
        return ids

    canonical = KOREAN_ALIASES.get(function_name.lower())
    if canonical:
        return JUMPIT_SEARCH_QUERIES.get(canonical, [])

    return []


def get_all_function_names() -> list[str]:
    """매핑 테이블에 등록된 모든 taxonomy 직무명 목록을 반환한다."""
    return list(JUMPIT_SEARCH_QUERIES.keys())


def get_all_category_ids() -> list[int]:
    """매핑 테이블의 모든 jobCategory ID를 중복 없이 반환한다."""
    seen: set[int] = set()
    result: list[int] = []
    for ids in JUMPIT_SEARCH_QUERIES.values():
        for cid in ids:
            if cid not in seen:
                seen.add(cid)
                result.append(cid)
    return result


def get_jumpit_category_name(category_id: int) -> str | None:
    """jobCategory ID → 점핏 카테고리명 반환. 없으면 None."""
    _ID_TO_NAME: dict[int, str] = {
        1: "서버/백엔드 개발자",
        2: "프론트엔드 개발자",
        3: "웹 풀스택 개발자",
        4: "안드로이드 개발자",
        5: "게임 클라이언트 개발자",
        6: "게임 서버 개발자",
        7: "DBA",
        8: "인공지능/머신러닝",
        9: "devops/시스템 엔지니어",
        10: "정보보안 담당자",
        11: "QA 엔지니어",
        12: "개발 PM",
        13: "HW/임베디드",
        15: "SW/솔루션",
        16: "iOS 개발자",
        17: "웹퍼블리셔",
        18: "크로스플랫폼 앱개발자",
        19: "빅데이터 엔지니어",
        20: "VR/AR/3D",
        21: "기술지원",
        22: "블록체인",
    }
    return _ID_TO_NAME.get(category_id)
