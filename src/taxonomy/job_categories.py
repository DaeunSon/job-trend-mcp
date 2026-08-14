"""
모든 사이트가 공유하는 표준 직군(Job Category) 분류.
job_postings.job_category_name 필드의 허용값 기준.

이 파일은 사람이 직접 관리한다 — discovery 스크립트가 덮어쓰지 않는다.
"""
from __future__ import annotations

JOB_CATEGORIES: list[str] = [
    "Engineering & Technology",
    "Data & Analytics",
    "Product & Design",
    "Marketing & Growth",
    "Finance & Accounting",
    "Operations & Strategy",
    "Human Resources",
    "Sales & Business Development",
    "Legal & Compliance",
    "Research & Science",
    "Customer Success",
    # 제품 범위 확정: IT·사무 12개 + Education / Supply Chain / Healthcare / Other
    "Education & Training",
    "Supply Chain & Logistics",
    "Healthcare",
    "Other",
]

_CATEGORY_SET: frozenset[str] = frozenset(JOB_CATEGORIES)


def is_valid_category(name: str) -> bool:
    return name in _CATEGORY_SET
