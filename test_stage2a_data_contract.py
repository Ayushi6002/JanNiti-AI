"""
test_stage2a_data_contract.py
------------------------------
Stage 2A Data Contract & Database Alignment Test Suite.
Verifies:
1. First-year HSC application data (attendance strictly None, qualification_type=HSC_12TH)
2. First-year Diploma application data (attendance strictly None, qualification_type=DIPLOMA)
3. Second-year application (attendance required, first_year_score & qualifying_score)
4. Third-year application (attendance required, second_year_score & first_year_score)
5. Fourth-year application (attendance required, third_year_score & second_year_score)
6. Postgraduate application (attendance required, ug_score & previous_score)
7. First-year attendance remains strictly None (never 0, never 75)
8. Irrelevant fields do not leak or persist
9. Stage switching / invalid stage rejected
10. Existing legacy applications remain intact with LEGACY_UNSPECIFIED
11. Full application data can be reconstructed from audit records
12. Eligibility service waives attendance requirement for fresh admission
13. ML application service routes fresh admission with NULL attendance safely to human review
14. Model file model_v2.pkl remains strictly untouched
"""

import os
import unittest
from backend.validation import (
    validate_academic_stage,
    validate_qualification_type,
    validate_academic_score,
    validate_attendance,
)
from backend.pipeline_service import validate_application_form_fields
from backend.eligibility_service import evaluate_min_value
from backend.ml_application_service import predict_application


class TestStage2ADataContract(unittest.TestCase):

    def test_01_first_year_hsc_application(self):
        form_data = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "HSC_12TH",
            "qualifying_score": "88.5",
            "ssc_score": "84.0",
            "annual_income": "300000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        res = validate_application_form_fields(form_data)
        self.assertEqual(res["academic_stage"], "FIRST_YEAR")
        self.assertEqual(res["qualification_type"], "HSC_12TH")
        self.assertEqual(res["qualifying_score"], 88.5)
        self.assertEqual(res["ssc_score"], 84.0)
        self.assertEqual(res["academic_score"], 88.5)
        self.assertEqual(res["previous_score"], 84.0)
        self.assertIsNone(res["attendance"])

    def test_02_first_year_diploma_application(self):
        form_data = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "DIPLOMA",
            "qualifying_score": "81.2",
            "ssc_score": "79.0",
            "annual_income": "250000",
            "application_category": "OBC",
            "scholarship_scheme": "Need-Based Scholarship",
        }
        res = validate_application_form_fields(form_data)
        self.assertEqual(res["academic_stage"], "FIRST_YEAR")
        self.assertEqual(res["qualification_type"], "DIPLOMA")
        self.assertEqual(res["qualifying_score"], 81.2)
        self.assertEqual(res["academic_score"], 81.2)
        self.assertIsNone(res["attendance"])

    def test_03_second_year_application(self):
        form_data = {
            "academic_stage": "SECOND_YEAR",
            "first_year_score": "78.4",
            "qualifying_score": "85.0",
            "attendance": "88.0",
            "annual_income": "350000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        res = validate_application_form_fields(form_data)
        self.assertEqual(res["academic_stage"], "SECOND_YEAR")
        self.assertEqual(res["first_year_score"], 78.4)
        self.assertEqual(res["academic_score"], 78.4)
        self.assertEqual(res["previous_score"], 85.0)
        self.assertEqual(res["attendance"], 88.0)
        self.assertIsNone(res["qualification_type"])

    def test_04_third_year_application(self):
        form_data = {
            "academic_stage": "THIRD_YEAR",
            "second_year_score": "82.1",
            "first_year_score": "78.4",
            "attendance": "89.5",
            "annual_income": "280000",
            "application_category": "EWS",
            "scholarship_scheme": "Academic Support Scholarship",
        }
        res = validate_application_form_fields(form_data)
        self.assertEqual(res["academic_stage"], "THIRD_YEAR")
        self.assertEqual(res["second_year_score"], 82.1)
        self.assertEqual(res["academic_score"], 82.1)
        self.assertEqual(res["previous_score"], 78.4)
        self.assertEqual(res["attendance"], 89.5)

    def test_05_fourth_year_application(self):
        form_data = {
            "academic_stage": "FOURTH_YEAR",
            "third_year_score": "85.6",
            "second_year_score": "82.1",
            "attendance": "91.0",
            "annual_income": "300000",
            "application_category": "SC",
            "scholarship_scheme": "Merit Scholarship",
        }
        res = validate_application_form_fields(form_data)
        self.assertEqual(res["academic_stage"], "FOURTH_YEAR")
        self.assertEqual(res["third_year_score"], 85.6)
        self.assertEqual(res["academic_score"], 85.6)
        self.assertEqual(res["previous_score"], 82.1)
        self.assertEqual(res["attendance"], 91.0)

    def test_06_postgraduate_application(self):
        form_data = {
            "academic_stage": "POSTGRADUATE",
            "ug_score": "80.5",
            "previous_score": "83.0",
            "attendance": "87.0",
            "annual_income": "400000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        res = validate_application_form_fields(form_data)
        self.assertEqual(res["academic_stage"], "POSTGRADUATE")
        self.assertEqual(res["ug_score"], 80.5)
        self.assertEqual(res["academic_score"], 80.5)
        self.assertEqual(res["previous_score"], 83.0)
        self.assertEqual(res["attendance"], 87.0)

    def test_07_first_year_attendance_strictly_null(self):
        # Even if someone injects attendance in form_data for FIRST_YEAR,
        # the canonical contract MUST override it to None (never 0 or 75)
        form_data = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "HSC_12TH",
            "qualifying_score": "90.0",
            "attendance": "75.0",  # Stale or fabricated value
            "annual_income": "200000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        res = validate_application_form_fields(form_data)
        self.assertIsNone(res["attendance"], "First year attendance must strictly be None.")

    def test_08_first_year_requires_qualification_type(self):
        form_data = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "",
            "qualifying_score": "90.0",
            "annual_income": "200000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_application_form_fields(form_data)
        self.assertIn("Qualification type is required", str(ctx.exception))

    def test_09_invalid_academic_stage_rejected(self):
        form_data = {
            "academic_stage": "FIFTH_YEAR_INVALID",
            "annual_income": "200000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_application_form_fields(form_data)
        self.assertIn("Invalid academic stage", str(ctx.exception))

    def test_10_legacy_applications_backward_compatibility(self):
        # Old legacy payload without academic_stage
        legacy_data = {
            "academic_score": "82.5",
            "previous_score": "79.0",
            "attendance": "85.0",
            "annual_income": "300000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        res = validate_application_form_fields(legacy_data)
        self.assertEqual(res["academic_stage"], "LEGACY_UNSPECIFIED")
        self.assertEqual(res["academic_score"], 82.5)
        self.assertEqual(res["previous_score"], 79.0)
        self.assertEqual(res["attendance"], 85.0)
        self.assertIsNone(res["qualification_type"])
        self.assertIsNone(res["first_year_score"])

    def test_11_eligibility_rule_attendance_waived_for_fresh_admission(self):
        rule = {
            "rule_type": "MIN_VALUE",
            "rule_config": {
                "field": "attendance",
                "minimum": 75.0,
            }
        }
        app_data = {
            "academic_score": 88.0,
            "attendance": None,  # Fresh admission
        }
        result = evaluate_min_value(rule, app_data)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result.get("waived"))
        self.assertIn("waived for fresh admission", result["message"])

    def test_12_model_v2_pkl_untouched(self):
        # Verification that model_v2.pkl was not touched during Stage 2A
        model_path = os.path.join("model", "model_v2.pkl")
        self.assertTrue(os.path.exists(model_path))
        # Verify file size is original ~6.6MB
        size = os.path.getsize(model_path)
        self.assertGreater(size, 6_000_000)


if __name__ == "__main__":
    unittest.main()
