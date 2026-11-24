from src.db.renormalize import renormalize_doc
from src.normalization.skill_noise_filter import is_skill_noise


def test_drops_noise_and_recanonicalizes_skills():
    noise = next(s for s in ["우대사항", "경력", "신입", "etc", "compliance", "intern"] if is_skill_noise(s))
    d = {"skills": [{"raw_text": noise, "canonical_name": noise},
                    {"raw_text": "python", "canonical_name": "python"},
                    {"raw_text": "zz-unknown", "canonical_name": "Keep Me"}],
         "job_function_name": "Backend Engineer", "job_category_name": "Engineering & Technology"}
    out = renormalize_doc(d)
    assert [s["canonical_name"] for s in out["skills"]] == ["Python", "Keep Me"]
    assert len(d["skills"]) == 3  # 입력은 그대로


def test_invalid_function_becomes_uncategorized():
    out = renormalize_doc({"skills": [], "job_function_name": "Retired Role",
                           "job_category_name": "Engineering & Technology"})
    assert (out["job_function_name"], out["job_category_name"]) == ("", "")
