"""크롤 결과 파일명 조립."""
from __future__ import annotations


def build_crawl_filename(source_name: str, query: str) -> str:
    """저장 파일명 조립. 예: saramin_백엔드_개발자, wanted_Backend_Engineer"""
    slug = query.strip().replace(" ", "_").replace("/", "_")
    return f"{source_name}_{slug}"
