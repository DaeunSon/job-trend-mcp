"""
표준 스킬(Skill) 분류 — saramin / jobkorea / wanted 등 파서의
KNOWN_SKILLS 합집합을 단일 진실 공급원으로 통합.

각 스킬 항목
  canonical_name : find_skills_in_text() 매칭 및 SkillTag.canonical_name 기준값
  category       : Language | Framework | Data/ML | Database | Infra/Tool | Other

규칙
  - canonical_name은 공식 표기(대소문자)를 따른다.
  - find_skills_in_text()의 매칭 키워드 = canonical_name 그대로 사용하되,
    별칭("golang" → "Go")은 SKILL_SEEDS / normalization_aliases.json 에서 관리한다.
  - 이 파일을 직접 편집해서 스킬을 추가/제거한다.

실제 데이터 기반 보강 기준 (스킬 alias / 신규 표준)
-------------------------------------------------
  - A단계 (기존 표준으로의 alias): 미매칭 빈도 ≥5 이고, 소프트스킬·노이즈·일반어는 제외.
  - C단계 (taxonomy 신규 표준): 명확한 기술/제품명이고 미매칭 빈도 ≥3 이면 추가 가능.
    (≥5만 쓰면 Unity·CSS 등 실제 도구가 계속 미매칭으로 남아서, C만 ≥3으로 둔다.
     D단계 이후에도 이 구분을 유지할 것 — alias는 ≥5, 신규 표준은 ≥3.)
  - D단계 (추출 노이즈 필터): alias가 아니라 skill_noise_filter 로 비-스킬 태그를
    skills[] 후보에서 제외. 스킬 정규화 라운드는 D에서 종료.
"""
from __future__ import annotations

import re

SKILLS: list[dict[str, str]] = [
    # ── 언어 ──────────────────────────────────────────────────
    {"canonical_name": "Python",        "category": "Language"},
    {"canonical_name": "Java",          "category": "Language"},
    {"canonical_name": "JavaScript",    "category": "Language"},
    {"canonical_name": "TypeScript",    "category": "Language"},
    {"canonical_name": "Go",            "category": "Language"},
    {"canonical_name": "Rust",          "category": "Language"},
    # C++ / C# 를 C 보다 앞에 두어 텍스트 매칭 시 더 긴 표기를 우선한다.
    {"canonical_name": "C++",           "category": "Language"},
    {"canonical_name": "C#",            "category": "Language"},
    {"canonical_name": "C",             "category": "Language"},
    {"canonical_name": "Ruby",          "category": "Language"},
    {"canonical_name": "PHP",           "category": "Language"},
    {"canonical_name": "Swift",         "category": "Language"},
    {"canonical_name": "Kotlin",        "category": "Language"},
    {"canonical_name": "Scala",         "category": "Language"},
    {"canonical_name": "R",             "category": "Language"},
    {"canonical_name": "SQL",           "category": "Language"},
    {"canonical_name": ".NET",          "category": "Language"},
    {"canonical_name": "CSS",           "category": "Language"},
    # ── 프레임워크 / 라이브러리 ──────────────────────────────
    {"canonical_name": "React",         "category": "Framework"},
    {"canonical_name": "React Native",  "category": "Framework"},
    {"canonical_name": "Vue",           "category": "Framework"},
    {"canonical_name": "Angular",       "category": "Framework"},
    {"canonical_name": "Next.js",       "category": "Framework"},
    {"canonical_name": "Nuxt.js",       "category": "Framework"},
    {"canonical_name": "Node.js",       "category": "Framework"},
    {"canonical_name": "Express",       "category": "Framework"},
    {"canonical_name": "NestJS",        "category": "Framework"},
    {"canonical_name": "Django",        "category": "Framework"},
    {"canonical_name": "FastAPI",       "category": "Framework"},
    {"canonical_name": "Flask",         "category": "Framework"},
    {"canonical_name": "Spring",        "category": "Framework"},
    {"canonical_name": "Spring Boot",   "category": "Framework"},
    {"canonical_name": "Laravel",       "category": "Framework"},
    {"canonical_name": "Rails",         "category": "Framework"},
    {"canonical_name": "Flutter",       "category": "Framework"},
    {"canonical_name": "Firebase",      "category": "Framework"},
    {"canonical_name": "WordPress",     "category": "Framework"},
    {"canonical_name": "Shopify",       "category": "Framework"},
    {"canonical_name": "Unity",         "category": "Framework"},
    {"canonical_name": "Unreal Engine", "category": "Framework"},
    # ── 데이터 / ML ──────────────────────────────────────────
    {"canonical_name": "TensorFlow",    "category": "Data/ML"},
    {"canonical_name": "PyTorch",       "category": "Data/ML"},
    {"canonical_name": "Scikit-learn",  "category": "Data/ML"},
    {"canonical_name": "Pandas",        "category": "Data/ML"},
    {"canonical_name": "NumPy",         "category": "Data/ML"},
    {"canonical_name": "Spark",         "category": "Data/ML"},
    {"canonical_name": "Kafka",         "category": "Data/ML"},
    {"canonical_name": "Airflow",       "category": "Data/ML"},
    {"canonical_name": "dbt",           "category": "Data/ML"},
    {"canonical_name": "Machine Learning", "category": "Data/ML"},
    {"canonical_name": "LLM",          "category": "Data/ML"},
    {"canonical_name": "MLOps",        "category": "Data/ML"},
    {"canonical_name": "Hadoop",        "category": "Data/ML"},
    # ── 데이터베이스 ─────────────────────────────────────────
    {"canonical_name": "MySQL",         "category": "Database"},
    {"canonical_name": "PostgreSQL",    "category": "Database"},
    {"canonical_name": "MongoDB",       "category": "Database"},
    {"canonical_name": "Redis",         "category": "Database"},
    {"canonical_name": "Elasticsearch", "category": "Database"},
    {"canonical_name": "MariaDB",       "category": "Database"},
    {"canonical_name": "Oracle",        "category": "Database"},
    {"canonical_name": "RabbitMQ",      "category": "Database"},
    {"canonical_name": "MSSQL",         "category": "Database"},
    {"canonical_name": "RDBMS",         "category": "Database"},
    # ── 인프라 / 도구 ─────────────────────────────────────────
    {"canonical_name": "AWS",           "category": "Infra/Tool"},
    {"canonical_name": "GCP",           "category": "Infra/Tool"},
    {"canonical_name": "Azure",         "category": "Infra/Tool"},
    {"canonical_name": "Docker",        "category": "Infra/Tool"},
    {"canonical_name": "Kubernetes",    "category": "Infra/Tool"},
    {"canonical_name": "Terraform",     "category": "Infra/Tool"},
    {"canonical_name": "Linux",         "category": "Infra/Tool"},
    {"canonical_name": "Jenkins",       "category": "Infra/Tool"},
    {"canonical_name": "GitHub",        "category": "Infra/Tool"},
    {"canonical_name": "GitLab",        "category": "Infra/Tool"},
    {"canonical_name": "Git",           "category": "Infra/Tool"},
    {"canonical_name": "Jira",          "category": "Infra/Tool"},
    {"canonical_name": "Confluence",    "category": "Infra/Tool"},
    {"canonical_name": "Nginx",         "category": "Infra/Tool"},
    {"canonical_name": "Datadog",       "category": "Infra/Tool"},
    {"canonical_name": "Excel",         "category": "Infra/Tool"},
    # ── 모바일 / 플랫폼 ──────────────────────────────────────
    {"canonical_name": "Android",       "category": "Other"},
    {"canonical_name": "iOS",           "category": "Other"},
    # ── 기타 ─────────────────────────────────────────────────
    {"canonical_name": "CI/CD",         "category": "Other"},
    {"canonical_name": "REST API",      "category": "Other"},
    {"canonical_name": "GraphQL",       "category": "Other"},
    {"canonical_name": "Agile",         "category": "Other"},
    {"canonical_name": "Scrum",         "category": "Other"},
    {"canonical_name": "DevOps",        "category": "Other"},
    {"canonical_name": "JPA",           "category": "Other"},
    {"canonical_name": "UI/UX",         "category": "Other"},
    {"canonical_name": "MSA",           "category": "Other"},
    {"canonical_name": "CRM",           "category": "Other"},
]

# raw_text → canonical_name. 키는 원문 표기 그대로(대소문자 구분).
# resolve() 는 정확 일치 후 소문자 키도 조회한다.
SKILL_SEEDS: dict[str, str] = {
    # 언어 별칭
    "golang": "Go",
    "Golang": "Go",
    "GoLang": "Go",
    "GO": "Go",
    "js": "JavaScript",
    "JS": "JavaScript",
    "Javascript": "JavaScript",
    "ts": "TypeScript",
    "TS": "TypeScript",
    "Typescript": "TypeScript",
    "C / C++": "C++",
    "c/c++": "C++",
    "cpp": "C++",
    "Csharp": "C#",
    "csharp": "C#",
    "CSharp": "C#",
    "dotnet": ".NET",
    "DotNet": ".NET",
    "dot net": ".NET",
    "ASP.NET": ".NET",
    "asp.net": ".NET",
    # 프레임워크 별칭
    "nodejs": "Node.js",
    "NodeJS": "Node.js",
    "Nodejs": "Node.js",
    "node": "Node.js",
    "react.js": "React",
    "React.js": "React",
    "reactjs": "React",
    "ReactJS": "React",
    "vue.js": "Vue",
    "Vue.js": "Vue",
    "vuejs": "Vue",
    "VueJS": "Vue",
    "nextjs": "Next.js",
    "NextJS": "Next.js",
    "next": "Next.js",
    "nuxt": "Nuxt.js",
    "nuxtjs": "Nuxt.js",
    "NuxtJS": "Nuxt.js",
    "nestjs": "NestJS",
    "Nest.js": "NestJS",
    "express.js": "Express",
    "Express.js": "Express",
    "expressjs": "Express",
    "spring framework": "Spring",
    "Spring Framework": "Spring",
    "springboot": "Spring Boot",
    "SpringBoot": "Spring Boot",
    "spring boot": "Spring Boot",
    "ruby on rails": "Rails",
    "Ruby on Rails": "Rails",
    "RoR": "Rails",
    # 데이터 / ML 별칭
    "sklearn": "Scikit-learn",
    "scikit-learn": "Scikit-learn",
    "Scikit Learn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "Tensorflow": "TensorFlow",
    "tensorflow": "TensorFlow",
    "Pytorch": "PyTorch",
    "pytorch": "PyTorch",
    "numpy": "NumPy",
    "Numpy": "NumPy",
    "pandas": "Pandas",
    "Apache Spark": "Spark",
    "apache spark": "Spark",
    "Apache Kafka": "Kafka",
    "apache kafka": "Kafka",
    "Apache Airflow": "Airflow",
    "apache airflow": "Airflow",
    "Apache Hadoop": "Hadoop",
    "apache hadoop": "Hadoop",
    "hadoop": "Hadoop",
    # DB 별칭
    "postgres": "PostgreSQL",
    "Postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "Postgresql": "PostgreSQL",
    "psql": "PostgreSQL",
    "mongo": "MongoDB",
    "Mongo": "MongoDB",
    "mongodb": "MongoDB",
    "mysql": "MySQL",
    "Maria DB": "MariaDB",
    "ms sql": "MSSQL",
    "MS SQL": "MSSQL",
    "SQL Server": "MSSQL",
    "sql server": "MSSQL",
    "Microsoft SQL Server": "MSSQL",
    "elastic search": "Elasticsearch",
    "Elastic Search": "Elasticsearch",
    "Rabbit MQ": "RabbitMQ",
    "rabbit mq": "RabbitMQ",
    "rabbitmq": "RabbitMQ",
    "rdbms": "RDBMS",
    # 인프라 별칭
    "excel": "Excel",
    "Microsoft Excel": "Excel",
    "microsoft excel": "Excel",
    "k8s": "Kubernetes",
    "K8s": "Kubernetes",
    "K8S": "Kubernetes",
    "kube": "Kubernetes",
    "amazon web services": "AWS",
    "Amazon Web Services": "AWS",
    "google cloud": "GCP",
    "Google Cloud": "GCP",
    "Google Cloud Platform": "GCP",
    "gcp": "GCP",
    "microsoft azure": "Azure",
    "Microsoft Azure": "Azure",
    "AZURE": "Azure",
    "TerraForm": "Terraform",
    "nginx": "Nginx",
    "NGINX": "Nginx",
    "Github": "GitHub",
    "github": "GitHub",
    "gitlab": "GitLab",
    "ci/cd": "CI/CD",
    "CICD": "CI/CD",
    "ci-cd": "CI/CD",
    # API 별칭
    "REST": "REST API",
    "RestAPI": "REST API",
    "Restful API": "REST API",
    "RESTful API": "REST API",
    "rest api": "REST API",
    "restful": "REST API",
    "graphql": "GraphQL",
    # 모바일
    "android": "Android",
    "ANDROID": "Android",
    "ios": "iOS",
    "IOS": "iOS",
    "iOS/Swift": "iOS",
    # C단계 신규 표준 스킬 별칭 (실제 수집 빈도 근거)
    "AI/ML": "Machine Learning",
    "ai/ml": "Machine Learning",
    "AI / ML": "Machine Learning",
    "ML": "Machine Learning",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "Machine learning": "Machine Learning",
    "UI/UX": "UI/UX",
    "ui/ux": "UI/UX",
    "UX/UI": "UI/UX",
    "ux/ui": "UI/UX",
    "datadog": "Datadog",
    "DataDog": "Datadog",
    "DATADOG": "Datadog",
    "wordpress": "WordPress",
    "Wordpress": "WordPress",
    "WORDPRESS": "WordPress",
    "shopify": "Shopify",
    "Shopify": "Shopify",
    "unity": "Unity",
    "UNITY": "Unity",
    "unreal": "Unreal Engine",
    "Unreal": "Unreal Engine",
    "unreal engine": "Unreal Engine",
    "Unreal engine": "Unreal Engine",
    "css": "CSS",
    "Css": "CSS",
    "confluence": "Confluence",
    "CONFLUENCE": "Confluence",
    "msa": "MSA",
    "MSA": "MSA",
    "microservice": "MSA",
    "microservices": "MSA",
    "Microservices": "MSA",
    "crm": "CRM",
    "Crm": "CRM",
    "ruby/rails": "Rails",
    "Ruby/Rails": "Rails",
    # 한글 별칭
    "파이썬": "Python",
    "자바": "Java",
    "자바스크립트": "JavaScript",
    "타입스크립트": "TypeScript",
    "스프링": "Spring",
    "스프링부트": "Spring Boot",
    "스프링 부트": "Spring Boot",
    "리액트": "React",
    "뷰": "Vue",
    "앵귤러": "Angular",
    "노드": "Node.js",
    "도커": "Docker",
    "쿠버네티스": "Kubernetes",
    "깃": "Git",
    "깃헙": "GitHub",
    "깃허브": "GitHub",
    "리눅스": "Linux",
    "장고": "Django",
    "플라스크": "Flask",
    "레디스": "Redis",
    "젠킨스": "Jenkins",
    "테라폼": "Terraform",
    "플러터": "Flutter",
    "안드로이드": "Android",
}

_SKILL_NAMES: list[str] = [s["canonical_name"] for s in SKILLS]
_SKILL_SET: frozenset[str] = frozenset(_SKILL_NAMES)
_CANONICAL_MAP: dict[str, str] = {s["canonical_name"].lower(): s["canonical_name"] for s in SKILLS}
_SKILL_SEED_LOWER: dict[str, str] = {k.lower(): v for k, v in SKILL_SEEDS.items()}


def get_skill_names() -> list[str]:
    """정규식 키워드 매칭에 사용할 canonical_name 목록을 반환한다."""
    return _SKILL_NAMES


def get_category(canonical_name: str) -> str | None:
    """스킬명에 해당하는 카테고리를 반환한다. 없으면 None."""
    for s in SKILLS:
        if s["canonical_name"] == canonical_name:
            return s["category"]
    return None


def is_valid_skill(name: str) -> bool:
    return name in _SKILL_SET


def lookup_skill_canonical(raw_text: str) -> str | None:
    """
    raw_text 를 표준 스킬명으로 변환한다.

    조회 순서: SKILL_SEEDS 정확 일치 → 소문자 seed → canonical 대소문자 무시.
    매칭 실패 시 None.
    """
    text = raw_text.strip()
    if not text:
        return None
    if text in SKILL_SEEDS:
        return SKILL_SEEDS[text]
    lower = text.lower()
    if lower in _SKILL_SEED_LOWER:
        return _SKILL_SEED_LOWER[lower]
    return _CANONICAL_MAP.get(lower)


def find_skills_in_text(text: str) -> list[str]:
    """
    텍스트에서 SKILLS 목록에 있는 스킬 키워드를 추출해 canonical_name 리스트로 반환한다.

    매칭 규칙
    ---------
    - 대소문자 무시.
    - 앞뒤로 ASCII 영숫자·점이 없는 위치에서만 매칭
      (예: "Google"에서 "Go" 오탐 방지, "Node.js" 정상 매칭).
    - 'R' 같은 단일 문자 스킬은 앞뒤 공백·구두점·한글 경계에서만 매칭.
    - 'Spring' 은 "Spring Street/Ave/Road..." 주소 문맥에서는 제외.
    - 매칭 순서는 SKILLS 리스트 순서를 따른다.
    """
    found: list[str] = []
    text_lower = text.lower()

    for skill in _SKILL_NAMES:
        escaped = re.escape(skill.lower())

        if skill == "C":
            # C++ / C# 와 겹치지 않도록 +, # 앞에서는 매칭하지 않음
            pattern = r"(?<![a-zA-Z0-9_])c(?![a-zA-Z0-9_+#])"
        elif len(skill) == 1:
            # 단일 문자 스킬("R")은 엄격한 단어 경계 적용
            pattern = r"(?<![a-zA-Z0-9_])" + escaped + r"(?![a-zA-Z0-9_])"
        elif skill.lower() == "spring":
            # 주소(Spring Street 등) 오탐 제외
            pattern = (
                r"(?<![a-z0-9.])spring(?![a-z0-9])"
                r"(?!\s+(?:street|st\.?|avenue|ave\.?|road|rd\.?|blvd\.?|boulevard|lane|ln\.?|drive|dr\.?))"
            )
        else:
            # 일반 스킬: ASCII 영숫자·점 경계 (한글 조사가 붙는 경우도 허용)
            pattern = r"(?<![a-z0-9.])" + escaped + r"(?![a-z0-9])"

        if re.search(pattern, text_lower):
            found.append(skill)

    return found
