"""normalization/company_utils.py 유닛 테스트."""
from __future__ import annotations

from src.normalization.company_utils import normalize_job_title


class TestNormalizeJobTitle:
    def test_particle_promo_tail_removed(self):
        assert normalize_job_title("개발 전문가를 모집합니다.") == "개발 전문가"

    def test_particle_promo_tail_semiconductor_title(self):
        title = "반도체 검사기 시스템 개발 전문가를 모집합니다."
        assert normalize_job_title(title) == "반도체 검사기 시스템 개발 전문가"

    def test_removes_company_name_in_title(self):
        title = "[일자리매칭플랫폼] 제일일렉트릭주식회사 조명스위치 H/W 제품 개발자 채용공고(경력)"
        result = normalize_job_title(title)
        assert "제일일렉트릭주식회사" not in result
        assert "조명스위치" in result

    def test_preserves_chae_yong_in_title(self):
        assert normalize_job_title("백엔드 개발자 채용") == "백엔드 개발자 채용"
