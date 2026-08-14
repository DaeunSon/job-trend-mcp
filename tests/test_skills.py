"""
taxonomy/skills.py · alias_resolver SKILL 정규화 유닛 테스트.
"""
from __future__ import annotations

from src.normalization.alias_resolver import resolve
from src.taxonomy.skills import (
    SKILLS,
    find_skills_in_text,
    is_valid_skill,
    lookup_skill_canonical,
)


class TestLookupSkillCanonical:
    def test_case_insensitive_canonical(self):
        assert lookup_skill_canonical("python") == "Python"
        assert lookup_skill_canonical("AZURE") == "Azure"
        assert lookup_skill_canonical("Github") == "GitHub"

    def test_common_aliases(self):
        assert lookup_skill_canonical("golang") == "Go"
        assert lookup_skill_canonical("k8s") == "Kubernetes"
        assert lookup_skill_canonical("postgres") == "PostgreSQL"
        assert lookup_skill_canonical("sklearn") == "Scikit-learn"
        assert lookup_skill_canonical("NodeJS") == "Node.js"
        assert lookup_skill_canonical("스프링 부트") == "Spring Boot"

    def test_unknown_returns_none(self):
        assert lookup_skill_canonical("성실성") is None
        assert lookup_skill_canonical("") is None


class TestResolveSkill:
    def test_seed_maps_variant(self):
        assert resolve("SKILL", "golang") == "Go"
        assert resolve("SKILL", "azure") == "Azure"
        assert resolve("SKILL", "k8s") == "Kubernetes"

    def test_invalid_json_alias_falls_back_to_seed(self):
        # normalization_aliases.json 에 azure→azure MANUAL 이 있어도 seed 로 교정
        assert resolve("SKILL", "azure") == "Azure"

    def test_unknown_keeps_raw(self):
        assert resolve("SKILL", "성실성") == "성실성"


class TestSkillsCatalog:
    def test_all_seed_targets_are_valid(self):
        from src.taxonomy.skills import SKILL_SEEDS

        for raw, canonical in SKILL_SEEDS.items():
            assert is_valid_skill(canonical), f"{raw!r} → {canonical!r}"

    def test_expanded_skills_present(self):
        names = {s["canonical_name"] for s in SKILLS}
        for expected in (
            "SQL", "Android", "iOS", "Nginx", "Hadoop", "Flutter", ".NET", "MSSQL",
            "Excel", "RDBMS",
        ):
            assert expected in names

    def test_excel_and_rdbms_resolve(self):
        assert lookup_skill_canonical("excel") == "Excel"
        assert lookup_skill_canonical("RDBMS") == "RDBMS"
        assert lookup_skill_canonical("rdbms") == "RDBMS"

    def test_css_is_language_not_framework(self):
        from src.taxonomy.skills import get_category

        assert get_category("CSS") == "Language"

    def test_find_skills_in_text_sql(self):
        assert "SQL" in find_skills_in_text("Requires strong SQL and Python skills")

    def test_spring_street_not_skill(self):
        text = "Address\n85 Spring Street, 10th Floor, New York, New York, 10012"
        assert "Spring" not in find_skills_in_text(text)

    def test_spring_framework_still_matched(self):
        assert "Spring" in find_skills_in_text("Experience with Spring and Hibernate")

    def test_go_not_matched_inside_google(self):
        """예전 'Go' ⊂ 'Google' 오탐이 재발하지 않아야 한다."""
        assert "Go" not in find_skills_in_text(
            "Worked at Google on search infrastructure"
        )
        assert "Go" in find_skills_in_text(
            "Backend services written in Go and Python"
        )

    def test_r_single_char_word_boundary(self):
        assert "R" not in find_skills_in_text("Required experience with React")
        assert "R" in find_skills_in_text("Statistical analysis with R and Python")

    def test_nodejs_dot_boundary(self):
        assert "Node.js" in find_skills_in_text("Experience with Node.js and Express")

    def test_case_variants_resolve_to_canonical(self):
        """저장된 passthrough(소문자 등)도 resolve 시 표준명으로 교정되어야 한다."""
        cases = {
            "terraform": "Terraform",
            "azure": "Azure",
            "AZURE": "Azure",
            "linux": "Linux",
            "spark": "Spark",
            "laravel": "Laravel",
            "c++": "C++",
            "c#": "C#",
            "rust": "Rust",
            "ruby": "Ruby",
            "swift": "Swift",
            "NGINX": "Nginx",
            "angular": "Angular",
            "scala": "Scala",
        }
        for raw, expected in cases.items():
            assert resolve("SKILL", raw) == expected, raw

    def test_c_stage_new_skills_resolve(self):
        assert resolve("SKILL", "AI/ML") == "Machine Learning"
        assert resolve("SKILL", "datadog") == "Datadog"
        assert resolve("SKILL", "UI/UX") == "UI/UX"
        assert resolve("SKILL", "wordpress") == "WordPress"
        assert resolve("SKILL", "MSA") == "MSA"
        assert resolve("SKILL", "CRM") == "CRM"
        assert resolve("SKILL", "Unity") == "Unity"
        assert resolve("SKILL", "unreal engine") == "Unreal Engine"
        assert resolve("SKILL", "Confluence") == "Confluence"
        assert resolve("SKILL", "css") == "CSS"
        assert resolve("SKILL", "ruby/rails") == "Rails"

    def test_c_language_not_matched_inside_cpp_or_csharp(self):
        assert "C" not in find_skills_in_text("Expert in C++ and templates")
        assert "C" not in find_skills_in_text("Built APIs with C# and .NET")
        assert "C++" in find_skills_in_text("Expert in C++ and templates")
        assert "C#" in find_skills_in_text("Built APIs with C# and .NET")
        assert "C" in find_skills_in_text("Low-level systems programming in C and assembly")

    def test_machine_learning_matched_in_text(self):
        found = find_skills_in_text("Experience with Machine Learning and PyTorch")
        assert "Machine Learning" in found
        assert "PyTorch" in found
