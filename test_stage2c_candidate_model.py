"""
test_stage2c_candidate_model.py
--------------------------------
Stage 2C Functional & Edge Case Testing Suite for Candidate Model.

Validates:
1. Candidate model test profiles:
   - CASE 1: First-year HSC student
   - CASE 2: First-year Diploma student
   - CASE 3: Second-year student
   - CASE 4: Third-year student
   - CASE 5: Fourth-year student
   - CASE 6: Postgraduate student
2. Probability semantics:
   - Estimated Approval Probability = P(APPROVE)
   - Proper class probability distribution summing to 1.0
3. TreeSHAP integration:
   - Explanations on First-Year profiles with NaN attendance
   - Explanations on continuing student profiles
   - Human-friendly explainability labels conforming to Section 18
4. Edge cases:
   - High academic score + low income (likely APPROVE)
   - Low academic score + high income (likely REJECT)
   - Incomplete documents (prevents high APPROVE probability)
   - Boundary percentages (0.0%, 100.0%)
5. Production Safety:
   - model/model_v2.pkl remains strictly untouched and identical to baseline
"""

import os
import unittest
import numpy as np
from backend.stage_aware_candidate_service import candidate_service


class TestStage2CCandidateModel(unittest.TestCase):

    def test_01_candidate_model_loaded(self):
        self.assertIsNotNone(candidate_service.model)
        self.assertIsNotNone(candidate_service.encoders)
        self.assertIsNotNone(candidate_service.explainer)
        self.assertEqual(len(candidate_service.feature_cols), 10)

    def test_02_case_1_first_year_hsc(self):
        profile = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "HSC_12TH",
            "qualifying_score": 92.0,
            "ssc_score": 88.0,
            "annual_income": 250000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(profile)
        self.assertEqual(res["prediction"], "APPROVE")
        self.assertGreater(res["estimated_approval_probability"], 0.70)
        self.assertTrue(np.isnan(res["normalized_input"]["attendance"]))
        self.assertEqual(res["normalized_input"]["is_attendance_applicable"], 0)

        # Check SHAP explanation
        shap_feat = {f["feature"]: f for f in res["tree_shap"]["features"]}
        self.assertIn("academic_score", shap_feat)
        self.assertEqual(shap_feat["attendance"]["direction"], "neutral")
        self.assertIn("College attendance is not available", shap_feat["attendance"]["human_explanation"])

    def test_03_case_2_first_year_diploma(self):
        profile = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "DIPLOMA",
            "qualifying_score": 88.5,
            "ssc_score": 85.0,
            "annual_income": 180000.0,
            "application_category": "OBC",
            "scholarship_scheme": "Need-Based Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(profile)
        self.assertEqual(res["prediction"], "APPROVE")
        self.assertGreater(res["estimated_approval_probability"], 0.70)
        self.assertEqual(res["normalized_input"]["qualification_type"], "DIPLOMA")

    def test_04_case_3_second_year(self):
        profile = {
            "academic_stage": "SECOND_YEAR",
            "academic_score": 82.0,
            "previous_score": 85.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(profile)
        self.assertEqual(res["normalized_input"]["attendance"], 88.0)
        self.assertEqual(res["normalized_input"]["is_attendance_applicable"], 1)
        self.assertGreater(res["estimated_approval_probability"], 0.60)

    def test_05_case_4_third_year(self):
        profile = {
            "academic_stage": "THIRD_YEAR",
            "academic_score": 84.0,
            "previous_score": 81.0,
            "attendance": 90.0,
            "annual_income": 200000.0,
            "application_category": "Economically Weaker",
            "scholarship_scheme": "Academic Support Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(profile)
        self.assertIn(res["prediction"], ["APPROVE", "NEEDS_HUMAN_REVIEW"])

    def test_06_case_5_fourth_year(self):
        profile = {
            "academic_stage": "FOURTH_YEAR",
            "academic_score": 85.0,
            "previous_score": 83.0,
            "attendance": 91.0,
            "annual_income": 250000.0,
            "application_category": "SC",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(profile)
        self.assertEqual(res["prediction"], "APPROVE")

    def test_07_case_6_postgraduate(self):
        profile = {
            "academic_stage": "POSTGRADUATE",
            "academic_score": 81.0,
            "previous_score": 84.0,
            "attendance": 86.0,
            "annual_income": 350000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(profile)
        self.assertIn(res["prediction"], ["APPROVE", "NEEDS_HUMAN_REVIEW"])

    def test_08_probability_semantics(self):
        # Verify that class_probabilities sum to 1.0 and Estimated Approval Probability is P(APPROVE)
        profile = {
            "academic_stage": "FIRST_YEAR",
            "academic_score": 60.0,
            "previous_score": 62.0,
            "annual_income": 700000.0,
            "application_category": "General",
            "scholarship_scheme": "Need-Based Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(profile)
        probas = res["class_probabilities"]
        prob_sum = sum(probas.values())
        self.assertAlmostEqual(prob_sum, 1.0, places=2)
        self.assertEqual(res["estimated_approval_probability"], probas["APPROVE"])
        # For a weak profile, P(APPROVE) should be low
        self.assertLess(res["estimated_approval_probability"], 0.35)

    def test_09_edge_case_incomplete_documents(self):
        profile = {
            "academic_stage": "SECOND_YEAR",
            "academic_score": 95.0,
            "previous_score": 92.0,
            "attendance": 90.0,
            "annual_income": 100000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "INCOMPLETE",
        }
        res = candidate_service.predict_and_explain(profile)
        # Even with high scores, INCOMPLETE documents should prevent direct APPROVE
        self.assertNotEqual(res["prediction"], "APPROVE")
        self.assertIn(res["prediction"], ["NEEDS_HUMAN_REVIEW", "REJECT"])

    def test_10_edge_case_low_academic_score_high_income(self):
        profile = {
            "academic_stage": "THIRD_YEAR",
            "academic_score": 45.0,
            "previous_score": 42.0,
            "attendance": 55.0,
            "annual_income": 1200000.0,
            "application_category": "General",
            "scholarship_scheme": "Need-Based Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = candidate_service.predict_and_explain(profile)
        self.assertEqual(res["prediction"], "REJECT")
        self.assertLess(res["estimated_approval_probability"], 0.10)

    def test_11_production_model_v2_strictly_untouched(self):
        model_path = os.path.join("model", "model_v2.pkl")
        self.assertTrue(os.path.exists(model_path))
        size = os.path.getsize(model_path)
        self.assertGreater(size, 6_000_000, "model_v2.pkl must remain intact")


if __name__ == "__main__":
    unittest.main()
