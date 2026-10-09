"""
test_stage2d1_category_semantics.py
-------------------------------------
Regression Test Suite for Stage 2D.1: Category Semantics Remediation.

Verifies:
1. General remains General.
2. OBC remains OBC.
3. SC remains SC.
4. ST remains ST.
5. EWS remains EWS.
6. Unsupported categories are validated explicitly.
7. Category normalization does not merge distinct supported categories.
8. Certificate category mismatches remain correctly detected.
9. Scholarship eligibility rules remain authoritative.
10. All five academic stages still map to the correct model features.
11. First-year attendance remains missing, not fabricated.
12. P(APPROVE) is extracted from the correct model class.
13. SHAP explanations work with the regenerated candidate.
14. The production model remains legacy_v2.
"""

import unittest
import numpy as np
import joblib
from pathlib import Path

from backend.validation import (
    CANONICAL_CATEGORIES,
    VALID_CATEGORIES,
    validate_application_category,
    canonicalize_social_category,
)
from backend.document_cross_checker import (
    compare_category_certificate_with_application,
)
from backend.document_extractor import normalize_category
from backend.eligibility_service import evaluate_rules_for_data
from backend.stage_aware_candidate_service import candidate_service
from backend.ml_service import (
    ml_service,
    ACTIVE_MODEL_VERSION,
    CANONICAL_CATEGORY_MAP,
    LEGACY_CATEGORY_NORMALIZATION_MAP,
)


class TestStage2D1CategorySemantics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.remediated_model_path = Path("model/model_stage_aware_candidate_remediated.pkl")
        cls.remediated_encoders_path = Path("model/encoders_stage_aware_candidate_remediated.pkl")
        cls.legacy_model_path = Path("model/model_v2.pkl")
        cls.legacy_encoders_path = Path("model/encoders_v2.pkl")

        assert cls.remediated_model_path.exists(), "Remediated model artifact missing."
        assert cls.remediated_encoders_path.exists(), "Remediated encoders artifact missing."
        assert cls.legacy_model_path.exists(), "Legacy model artifact missing."
        assert cls.legacy_encoders_path.exists(), "Legacy encoders artifact missing."

        cls.remediated_encoders = joblib.load(str(cls.remediated_encoders_path))

    def test_01_general_remains_general(self):
        """1. General remains General."""
        norm_val = canonicalize_social_category("GENERAL")
        self.assertEqual(norm_val, "General")
        self.assertEqual(CANONICAL_CATEGORY_MAP["GENERAL"], "General")

        cat_encoder = self.remediated_encoders["application_category"]
        self.assertIn("General", cat_encoder.classes_)
        encoded_idx = cat_encoder.transform(["General"])[0]
        self.assertEqual(cat_encoder.inverse_transform([encoded_idx])[0], "General")

    def test_02_obc_remains_obc(self):
        """2. OBC remains OBC (never merged into Special Circumstance)."""
        norm_val = canonicalize_social_category("OBC")
        self.assertEqual(norm_val, "OBC")
        self.assertEqual(CANONICAL_CATEGORY_MAP["OBC"], "OBC")

        cat_encoder = self.remediated_encoders["application_category"]
        self.assertIn("OBC", cat_encoder.classes_)
        encoded_idx = cat_encoder.transform(["OBC"])[0]
        self.assertEqual(cat_encoder.inverse_transform([encoded_idx])[0], "OBC")
        self.assertNotEqual(cat_encoder.inverse_transform([encoded_idx])[0], "Special Circumstance")

    def test_03_sc_remains_sc(self):
        """3. SC remains SC (never merged into Special Circumstance)."""
        norm_val = canonicalize_social_category("SC")
        self.assertEqual(norm_val, "SC")
        self.assertEqual(CANONICAL_CATEGORY_MAP["SC"], "SC")

        cat_encoder = self.remediated_encoders["application_category"]
        self.assertIn("SC", cat_encoder.classes_)
        encoded_idx = cat_encoder.transform(["SC"])[0]
        self.assertEqual(cat_encoder.inverse_transform([encoded_idx])[0], "SC")
        self.assertNotEqual(cat_encoder.inverse_transform([encoded_idx])[0], "Special Circumstance")

    def test_04_st_remains_st(self):
        """4. ST remains ST (never merged into Special Circumstance)."""
        norm_val = canonicalize_social_category("ST")
        self.assertEqual(norm_val, "ST")
        self.assertEqual(CANONICAL_CATEGORY_MAP["ST"], "ST")

        cat_encoder = self.remediated_encoders["application_category"]
        self.assertIn("ST", cat_encoder.classes_)
        encoded_idx = cat_encoder.transform(["ST"])[0]
        self.assertEqual(cat_encoder.inverse_transform([encoded_idx])[0], "ST")
        self.assertNotEqual(cat_encoder.inverse_transform([encoded_idx])[0], "Special Circumstance")

    def test_05_ews_remains_ews(self):
        """5. EWS remains EWS."""
        norm_val = canonicalize_social_category("EWS")
        self.assertEqual(norm_val, "EWS")
        self.assertEqual(CANONICAL_CATEGORY_MAP["EWS"], "EWS")

        cat_encoder = self.remediated_encoders["application_category"]
        self.assertIn("EWS", cat_encoder.classes_)
        encoded_idx = cat_encoder.transform(["EWS"])[0]
        self.assertEqual(cat_encoder.inverse_transform([encoded_idx])[0], "EWS")

    def test_06_unsupported_categories_validated_explicitly(self):
        """6. Unsupported categories and non-social tokens are rejected on new submissions."""
        invalid_inputs = [
            "INVALID_CATEGORY",
            "MILITARY",
            "INTERNATIONAL",
            "Special Circumstance",
            "SPECIAL CIRCUMSTANCE",
            "Merit",
            "MERIT",
            "",
            None,
        ]
        for inv in invalid_inputs:
            ok, val, err = validate_application_category(inv)
            self.assertFalse(ok, f"Expected invalid for '{inv}'")
            self.assertIsNotNone(err)

    def test_07_category_normalization_does_not_merge_distinct_categories(self):
        """7. Category normalization does not merge distinct supported categories."""
        canonical_five = ["General", "OBC", "SC", "ST", "EWS"]
        normalized_results = [canonicalize_social_category(c) for c in canonical_five]
        self.assertEqual(len(set(normalized_results)), 5, "Distinct categories were merged!")

        cat_encoder = self.remediated_encoders["application_category"]
        encoded_values = [cat_encoder.transform([c])[0] for c in canonical_five]
        self.assertEqual(len(set(encoded_values)), 5, "Encoders mapped distinct categories to the same code!")

    def test_08_certificate_category_mismatches_detected(self):
        """8. Certificate category mismatches remain correctly detected."""
        # Scenario A: Mismatch between application SC and certificate OBC
        extracted_doc = {
            "category": "Other Backward Class",
            "normalized_category": "OBC",
            "student_name": "Test Student",
        }
        app_data = {
            "application_category": "SC",
            "applicant_name": "Test Student",
        }
        res = compare_category_certificate_with_application(extracted_doc, app_data)
        self.assertEqual(res["overall_status"], "MISMATCH")
        self.assertEqual(res["category_check"]["status"], "MISMATCH")

        # Scenario B: Matching OBC certificate
        app_data_obc = {
            "application_category": "OBC",
            "applicant_name": "Test Student",
        }
        res_match = compare_category_certificate_with_application(extracted_doc, app_data_obc)
        self.assertEqual(res_match["overall_status"], "MATCH")
        self.assertEqual(res_match["category_check"]["status"], "MATCH")

    def test_09_scholarship_eligibility_rules_authoritative(self):
        """9. Scholarship eligibility rules remain authoritative."""
        rules = [
            {
                "rule_code": "MIN_ACAD",
                "rule_name": "Minimum Academic Score",
                "rule_type": "MIN_VALUE",
                "rule_config": {"field": "academic_score", "minimum": 75.0},
            },
            {
                "rule_code": "MAX_INC",
                "rule_name": "Maximum Income",
                "rule_type": "MAX_VALUE",
                "rule_config": {"field": "annual_income", "maximum": 500000.0},
            },
        ]
        # Failing student
        app_data = {"academic_score": 60.0, "annual_income": 300000.0}
        verification_summary = {"required_documents": [], "documents": {}}
        eval_res = evaluate_rules_for_data(rules, app_data, verification_summary)
        self.assertFalse(eval_res["eligible"])
        self.assertEqual(eval_res["failed_count"], 1)

        # Passing student
        app_data_pass = {"academic_score": 85.0, "annual_income": 300000.0}
        eval_res_pass = evaluate_rules_for_data(rules, app_data_pass, verification_summary)
        self.assertTrue(eval_res_pass["eligible"])
        self.assertEqual(eval_res_pass["failed_count"], 0)

    def test_10_all_five_academic_stages_map_correctly(self):
        """10. All five academic stages still map to the correct model features."""
        stages = [
            ("FIRST_YEAR", {"qualification_type": "HSC_12TH", "qualifying_score": 88.0, "ssc_score": 84.0}),
            ("SECOND_YEAR", {"academic_score": 80.0, "previous_score": 82.0, "attendance": 85.0}),
            ("THIRD_YEAR", {"academic_score": 81.0, "previous_score": 80.0, "attendance": 86.0}),
            ("FOURTH_YEAR", {"academic_score": 83.0, "previous_score": 81.0, "attendance": 87.0}),
            ("POSTGRADUATE", {"academic_score": 84.0, "previous_score": 82.0, "attendance": 88.0}),
        ]

        for stage_name, fields in stages:
            payload = {
                "academic_stage": stage_name,
                "annual_income": 300000.0,
                "application_category": "OBC",
                "scholarship_scheme": "Need-Based Scholarship",
                "documents_verified": "VERIFIED",
                **fields
            }
            norm = candidate_service.normalize_input(payload)
            self.assertEqual(norm["academic_stage"], stage_name)
            self.assertEqual(norm["application_category"], "OBC")
            self.assertIsNotNone(norm["academic_score"])
            self.assertIsNotNone(norm["previous_score"])

    def test_11_first_year_attendance_remains_missing_not_fabricated(self):
        """11. First-year attendance remains missing, not fabricated."""
        fy_payload = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "HSC_12TH",
            "qualifying_score": 90.0,
            "ssc_score": 88.0,
            "attendance": None,
            "annual_income": 250000.0,
            "application_category": "SC",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        norm = candidate_service.normalize_input(fy_payload)
        self.assertTrue(np.isnan(norm["attendance"]))
        self.assertEqual(norm["is_attendance_applicable"], 0)

    def test_12_p_approve_extracted_from_correct_class(self):
        """12. P(APPROVE) is extracted from the correct model class."""
        target_encoder = self.remediated_encoders["target"]
        classes = list(target_encoder.classes_)
        approve_idx = classes.index("APPROVE")

        # Verify candidate service extracted index
        self.assertEqual(candidate_service.approve_idx, approve_idx)
        self.assertEqual(classes[candidate_service.approve_idx], "APPROVE")

        # Test prediction returns probability matching proba[approve_idx]
        test_payload = {
            "academic_stage": "SECOND_YEAR",
            "academic_score": 90.0,
            "previous_score": 88.0,
            "attendance": 92.0,
            "annual_income": 200000.0,
            "application_category": "OBC",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(test_payload)
        self.assertIn("class_probabilities", res)
        self.assertEqual(
            res["estimated_approval_probability"],
            res["class_probabilities"]["APPROVE"]
        )

    def test_13_shap_explanations_work_with_regenerated_candidate(self):
        """13. SHAP explanations work with the regenerated candidate."""
        categories_to_test = ["General", "OBC", "SC", "ST", "EWS"]
        for cat in categories_to_test:
            payload = {
                "academic_stage": "FIRST_YEAR",
                "qualification_type": "HSC_12TH",
                "qualifying_score": 89.0,
                "ssc_score": 86.0,
                "annual_income": 250000.0,
                "application_category": cat,
                "scholarship_scheme": "Merit Scholarship",
                "documents_verified": "VERIFIED",
            }
            res = candidate_service.predict_and_explain(payload)
            self.assertIn("tree_shap", res)
            self.assertEqual(len(res["tree_shap"]["features"]), 10)

            # Check waived attendance neutral explanation
            att_feat = next(f for f in res["tree_shap"]["features"] if f["feature"] == "attendance")
            self.assertEqual(att_feat["direction"], "neutral")
            self.assertTrue(
                "not available" in att_feat["human_explanation"].lower() or
                "waived" in att_feat["human_explanation"].lower()
            )

    def test_14_production_model_remains_legacy_v2(self):
        """14. The production model remains legacy_v2."""
        self.assertEqual(ACTIVE_MODEL_VERSION, "legacy_v2")
        self.assertEqual(ml_service.active_version, "legacy_v2")

        # Ensure legacy model artifacts are untouched and loaded
        self.assertIn("model_v2.pkl", str(self.legacy_model_path))
        self.assertEqual(len(ml_service.feature_cols), 7)
        self.assertEqual(
            list(ml_service.encoders["application_category"].classes_),
            ["Economically Weaker", "General", "Merit", "Special Circumstance"]
        )


if __name__ == "__main__":
    unittest.main()
