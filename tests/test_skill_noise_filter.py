"""skill_noise_filter 유닛 테스트."""
from __future__ import annotations

from src.normalization.skill_noise_filter import (
    filter_skill_candidates,
    is_skill_noise,
)


class TestIsSkillNoise:
    def test_korean_soft_skills(self):
        assert is_skill_noise("계획성")
        assert is_skill_noise("성실성")
        assert is_skill_noise("협동심")
        assert is_skill_noise("스트레스관리")

    def test_hangul_tech_not_filtered(self):
        """한글 기술 표현은 명시 목록에 없으면 통과."""
        assert not is_skill_noise("임베디드리눅스")
        assert not is_skill_noise("영어")

    def test_place_names(self):
        assert is_skill_noise("Hamburg")
        assert is_skill_noise("berlin")
        assert is_skill_noise("München")

    def test_german_role_noise(self):
        assert is_skill_noise("Werkstudent")
        assert is_skill_noise("Werkstudium")
        assert is_skill_noise("Vertrieb")

    def test_generic_role_words(self):
        assert is_skill_noise("backend")
        assert is_skill_noise("Frontend")
        assert is_skill_noise("documentation")
        assert is_skill_noise("Engineering")
        assert is_skill_noise("Sales")
        assert is_skill_noise("marketplace")
        assert is_skill_noise("security")

    def test_english_soft_skills(self):
        assert is_skill_noise("people management")
        assert is_skill_noise("prototyping")
        assert is_skill_noise("engineering management")

    def test_real_tech_skills_pass(self):
        for name in (
            "Terraform",
            "Kubernetes",
            "Python",
            "Docker",
            "AWS",
            "React",
            "excel",  # 실제 도구 — 노이즈 아님 (A/C 잔여 처리)
        ):
            assert not is_skill_noise(name), name


class TestFilterSkillCandidates:
    def test_filters_noise_keeps_tech(self):
        result = filter_skill_candidates(
            ["Engineering", "Terraform", "Hamburg", "Kubernetes", "계획성", "Python"]
        )
        assert result == ["Terraform", "Kubernetes", "Python"]

    def test_dedupes(self):
        assert filter_skill_candidates(["Python", "Python", "Go"]) == ["Python", "Go"]

    def test_empty_and_whitespace(self):
        assert filter_skill_candidates(["", "  ", "Java"]) == ["Java"]
