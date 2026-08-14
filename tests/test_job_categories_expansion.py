"""
직군/직무 범위 확장 유닛 테스트.
"""
from __future__ import annotations

from src.normalization.job_taxonomy import (
    extract_title_function_raw,
    normalize_job_taxonomy,
)
from src.normalization.alias_resolver import resolve
from src.taxonomy.job_categories import JOB_CATEGORIES, is_valid_category
from src.taxonomy.job_functions import get_category_for_function, is_valid_function


class TestExpandedCategories:
    def test_new_categories_registered(self):
        for cat in (
            "Education & Training",
            "Supply Chain & Logistics",
            "Healthcare",
        ):
            assert cat in JOB_CATEGORIES
            assert is_valid_category(cat)

    def test_new_functions_link_to_categories(self):
        assert get_category_for_function("Teacher / Instructor") == "Education & Training"
        assert get_category_for_function("Supply Chain Manager") == "Supply Chain & Logistics"
        assert get_category_for_function("Nurse") == "Healthcare"
        assert is_valid_function("Logistics Coordinator")
        assert is_valid_function("Healthcare Specialist")


class TestExpandedSeeds:
    def test_remotive_teaching_maps_to_education(self):
        assert resolve("JOB_CATEGORY", "Teaching") == "Education & Training"

    def test_remotive_supply_chain_maps(self):
        assert resolve("JOB_CATEGORY", "Supply Chain") == "Supply Chain & Logistics"

    def test_medical_maps_to_healthcare(self):
        assert resolve("JOB_CATEGORY", "Medical") == "Healthcare"

    def test_steuerberater_title_maps_to_accountant(self):
        raw = extract_title_function_raw("Steuerberater (m/w/d) in Berlin")
        fn, cat = normalize_job_taxonomy(raw, "")
        assert fn == "Accountant"
        assert cat == "Finance & Accounting"

    def test_nurse_title_maps_to_healthcare(self):
        raw = extract_title_function_raw("Registered Nurse - ICU")
        fn, cat = normalize_job_taxonomy(raw, "")
        assert fn == "Nurse"
        assert cat == "Healthcare"

    def test_fachinformatiker_maps_to_engineering(self):
        raw = extract_title_function_raw("Fachinformatiker (m/w/d)")
        fn, cat = normalize_job_taxonomy(raw, "")
        assert fn == "Software Engineer"
        assert cat == "Engineering & Technology"

    def test_account_executive_maps(self):
        raw = extract_title_function_raw("Strategic Account Executive Enterprise - DACH")
        fn, cat = normalize_job_taxonomy(raw, "")
        assert fn == "Account Executive"
        assert cat == "Sales & Business Development"
