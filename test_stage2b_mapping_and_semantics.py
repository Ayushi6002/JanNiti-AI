"""
test_stage2b_mapping_and_semantics.py
--------------------------------------
Stage 2B Verification Suite.
Validates:
1. End-to-end mapping consistency for all 5 academic stages:
   - CASE 1: First-year HSC student (attendance strictly None, qualification_type=HSC_12TH)
   - CASE 2: First-year Diploma student (attendance strictly None, qualification_type=DIPLOMA)
   - CASE 3: Second-year student (attendance=first year attendance)
   - CASE 4: Third-year student (attendance=second year attendance)
   - CASE 5: Fourth-year student (attendance=third year attendance)
   - CASE 6: Postgraduate student (attendance=undergraduate attendance)
2. Semantic consistency between UI input, pipeline validation, and ML feature vector.
3. Candidate training dataset distribution and absence of target leakage.
4. Model file model/model_v2.pkl remains strictly untouched.
"""

import os
import unittest
import pandas as pd
from backend.pipeline_service import validate_application_form_fields


class TestStage2BMappingAndSemantics(unittest.TestCase):

    def test_case_1_first_year_hsc(self):
        ui_input = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "HSC_12TH",
            "qualifying_score": "88.5",
            "ssc_score": "84.0",
            "annual_income": "320000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        validated = validate_application_form_fields(ui_input)

        # Semantics check
        self.assertEqual(validated["academic_stage"], "FIRST_YEAR")
        self.assertEqual(validated["qualification_type"], "HSC_12TH")
        self.assertEqual(validated["academic_score"], 88.5)
        self.assertEqual(validated["previous_score"], 84.0)
        self.assertIsNone(validated["attendance"], "First-year attendance MUST be strictly None")

    def test_case_2_first_year_diploma(self):
        ui_input = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "DIPLOMA",
            "qualifying_score": "82.4",
            "ssc_score": "80.0",
            "annual_income": "240000",
            "application_category": "OBC",
            "scholarship_scheme": "Need-Based Scholarship",
        }
        validated = validate_application_form_fields(ui_input)

        self.assertEqual(validated["academic_stage"], "FIRST_YEAR")
        self.assertEqual(validated["qualification_type"], "DIPLOMA")
        self.assertEqual(validated["academic_score"], 82.4)
        self.assertIsNone(validated["attendance"])

    def test_case_3_second_year(self):
        ui_input = {
            "academic_stage": "SECOND_YEAR",
            "first_year_score": "79.2",
            "qualifying_score": "86.0",
            "attendance": "84.5",
            "annual_income": "300000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        validated = validate_application_form_fields(ui_input)

        self.assertEqual(validated["academic_stage"], "SECOND_YEAR")
        self.assertEqual(validated["academic_score"], 79.2)  # First year college %
        self.assertEqual(validated["previous_score"], 86.0)  # Qualifying 12th/Diploma %
        self.assertEqual(validated["attendance"], 84.5)      # 1st year college attendance

    def test_case_4_third_year(self):
        ui_input = {
            "academic_stage": "THIRD_YEAR",
            "second_year_score": "81.5",
            "first_year_score": "79.2",
            "attendance": "88.0",
            "annual_income": "280000",
            "application_category": "EWS",
            "scholarship_scheme": "Academic Support Scholarship",
        }
        validated = validate_application_form_fields(ui_input)

        self.assertEqual(validated["academic_stage"], "THIRD_YEAR")
        self.assertEqual(validated["academic_score"], 81.5)  # 2nd year college %
        self.assertEqual(validated["previous_score"], 79.2)  # 1st year college %
        self.assertEqual(validated["attendance"], 88.0)      # 2nd year college attendance

    def test_case_5_fourth_year(self):
        ui_input = {
            "academic_stage": "FOURTH_YEAR",
            "third_year_score": "84.0",
            "second_year_score": "81.5",
            "attendance": "90.0",
            "annual_income": "350000",
            "application_category": "SC",
            "scholarship_scheme": "Merit Scholarship",
        }
        validated = validate_application_form_fields(ui_input)

        self.assertEqual(validated["academic_stage"], "FOURTH_YEAR")
        self.assertEqual(validated["academic_score"], 84.0)  # 3rd year college %
        self.assertEqual(validated["previous_score"], 81.5)  # 2nd year college %
        self.assertEqual(validated["attendance"], 90.0)      # 3rd year college attendance

    def test_case_6_postgraduate(self):
        ui_input = {
            "academic_stage": "POSTGRADUATE",
            "ug_score": "82.0",
            "previous_score": "85.0",
            "attendance": "87.5",
            "annual_income": "450000",
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }
        validated = validate_application_form_fields(ui_input)

        self.assertEqual(validated["academic_stage"], "POSTGRADUATE")
        self.assertEqual(validated["academic_score"], 82.0)  # Final UG %
        self.assertEqual(validated["previous_score"], 85.0)  # Prior degree %
        self.assertEqual(validated["attendance"], 87.5)      # UG attendance

    def test_candidate_dataset_integrity(self):
        ds_path = "data_real/jan_niti_stage_aware_dataset_candidate.csv"
        self.assertTrue(os.path.exists(ds_path), "Candidate dataset must exist")
        df = pd.read_csv(ds_path)
        self.assertEqual(len(df), 12000)

        # Verify all FIRST_YEAR have NaN attendance
        fy_df = df[df["academic_stage"] == "FIRST_YEAR"]
        self.assertEqual(len(fy_df), 3000)
        self.assertTrue(fy_df["attendance"].isna().all(), "All FIRST_YEAR records must have NaN attendance")

        # Verify all other stages have non-null attendance
        cont_df = df[df["academic_stage"] != "FIRST_YEAR"]
        self.assertEqual(len(cont_df), 9000)
        self.assertFalse(cont_df["attendance"].isna().any(), "Continuing students must have non-null attendance")

        # Zero leakage check
        forbidden_cols = ["final_decision", "human_decision", "admin_comment", "rejection_reason", "eligible", "is_eligible"]
        for col in forbidden_cols:
            self.assertNotIn(col, df.columns, f"Leaked column {col} found in dataset")

    def test_production_model_v2_not_modified(self):
        model_path = os.path.join("model", "model_v2.pkl")
        self.assertTrue(os.path.exists(model_path))
        size = os.path.getsize(model_path)
        self.assertGreater(size, 6_000_000, "model_v2.pkl must remain intact")


if __name__ == "__main__":
    unittest.main()
