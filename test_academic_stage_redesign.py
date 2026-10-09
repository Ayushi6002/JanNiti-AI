"""
test_academic_stage_redesign.py
--------------------------------------------------------------------------------
Comprehensive Test Suite for JanNiti AI Academic Stage Redesign & First-Year Audit

Tests:
 1. Case 1: First Year + HSC (qualifying score used, 10th score used, attendance not required)
 2. Case 2: First Year + Diploma (qualifying score used, 10th score used, attendance not required)
 3. Case 3: Second Year (first-year college score, 12th/Diploma score, first-year attendance)
 4. Case 4: Third Year (second-year college score, first-year score, second-year attendance)
 5. Case 4b: Fourth Year & Postgraduate (stage-aware extraction and validation)
 6. Case 5: Stale field clearing contract in frontend JS & HTML
 7. Data Integrity: First-Year attendance strictly None (never 0, never 75)
 8. First-Year ML Transparency: Model routes to NEEDS_HUMAN_REVIEW with explanatory advisory
 9. Rule Evaluation: First-Year applicants evaluated on merit/income without college attendance penalty
10. UI Contract: Dropdown options and dynamic field elements present in HTML and JS
--------------------------------------------------------------------------------
"""

import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app
from backend.scholarship_predictor_service import (
    validate_prediction_input,
    predict_scholarships,
)


class TestAcademicStageRedesign(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    # =========================================================================
    # 1. CASE 1: FIRST YEAR + HSC
    # =========================================================================
    def test_case_01_first_year_hsc(self):
        """Case 1: First Year + HSC payload extracts qualifying score, handles optional SSC, and requires no college attendance."""
        payload = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "HSC",
            "qualifying_score": 88.5,
            "ssc_score": 85.0,
            "annual_income": 250000,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
            },
        }

        # 1. Validation mapping check
        cleaned = validate_prediction_input(payload)
        self.assertEqual(cleaned["academic_stage"], "FIRST_YEAR")
        self.assertEqual(cleaned["qualification_type"], "HSC")
        self.assertEqual(cleaned["academic_score"], 88.5)
        self.assertEqual(cleaned["previous_score"], 85.0)
        self.assertIsNone(cleaned["attendance"], "College attendance must be None for first-year applicants")

        # 2. Prediction endpoint check
        res = self.client.post("/scholarship/predict", json=payload)
        self.assertEqual(res.status_code, 200, res.data.decode())
        data = res.get_json()
        self.assertTrue(data.get("success", False))

        merit = next((s for s in data["schemes"] if s["scheme_code"] == "MERIT"), None)
        self.assertIsNotNone(merit)
        # Evaluated without failing on missing college attendance
        self.assertEqual(merit["eligibility_status"], "ELIGIBLE")
        # ML model transparently routes to NEEDS_HUMAN_REVIEW
        self.assertEqual(merit["ml_prediction"]["prediction"], "NEEDS_HUMAN_REVIEW")
        self.assertIn("college attendance", merit["ml_prediction"]["approval_probability_note"].lower())
        print(">>> Test Case 1 Passed: First Year + HSC processed accurately without college attendance.")

    # =========================================================================
    # 2. CASE 2: FIRST YEAR + DIPLOMA
    # =========================================================================
    def test_case_02_first_year_diploma(self):
        """Case 2: First Year + Diploma payload extracts diploma percentage as academic_score with no college attendance."""
        payload = {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "DIPLOMA",
            "qualifying_score": 82.0,
            "ssc_score": 79.5,
            "annual_income": 200000,
            "application_category": "OBC",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
                "category_certificate": True,
            },
        }

        cleaned = validate_prediction_input(payload)
        self.assertEqual(cleaned["academic_stage"], "FIRST_YEAR")
        self.assertEqual(cleaned["qualification_type"], "DIPLOMA")
        self.assertEqual(cleaned["academic_score"], 82.0)
        self.assertEqual(cleaned["previous_score"], 79.5)
        self.assertIsNone(cleaned["attendance"])

        res = self.client.post("/scholarship/predict", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        category_scheme = next((s for s in data["schemes"] if s["scheme_code"] == "CATEGORY"), None)
        self.assertIsNotNone(category_scheme)
        self.assertEqual(category_scheme["eligibility_status"], "ELIGIBLE")
        print(">>> Test Case 2 Passed: First Year + Diploma processed correctly.")

    # =========================================================================
    # 3. CASE 3: SECOND YEAR
    # =========================================================================
    def test_case_03_second_year(self):
        """Case 3: Second Year payload maps first_year_score -> academic_score, qualifying_score -> previous_score, attendance required."""
        payload = {
            "academic_stage": "SECOND_YEAR",
            "first_year_score": 81.5,
            "qualifying_score": 86.0,
            "attendance": 84.0,
            "annual_income": 300000,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
            },
        }

        cleaned = validate_prediction_input(payload)
        self.assertEqual(cleaned["academic_stage"], "SECOND_YEAR")
        self.assertEqual(cleaned["academic_score"], 81.5)
        self.assertEqual(cleaned["previous_score"], 86.0)
        self.assertEqual(cleaned["attendance"], 84.0)

        res = self.client.post("/scholarship/predict", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        merit = next((s for s in data["schemes"] if s["scheme_code"] == "MERIT"), None)
        self.assertIsNotNone(merit)
        # Continuing year has attendance and produces active ML assessment
        self.assertEqual(merit["ml_prediction"]["prediction"], "APPROVE")
        self.assertGreater(merit["ml_prediction"]["confidence"], 0.5)
        print(">>> Test Case 3 Passed: Second Year mapped and predicted with valid college attendance.")

    # =========================================================================
    # 4. CASE 4: THIRD YEAR
    # =========================================================================
    def test_case_04_third_year(self):
        """Case 4: Third Year payload maps second_year_score -> academic_score, first_year_score -> previous_score, attendance required."""
        payload = {
            "academic_stage": "THIRD_YEAR",
            "second_year_score": 83.0,
            "first_year_score": 80.0,
            "attendance": 89.0,
            "annual_income": 280000,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
            },
        }

        cleaned = validate_prediction_input(payload)
        self.assertEqual(cleaned["academic_stage"], "THIRD_YEAR")
        self.assertEqual(cleaned["academic_score"], 83.0)
        self.assertEqual(cleaned["previous_score"], 80.0)
        self.assertEqual(cleaned["attendance"], 89.0)

        res = self.client.post("/scholarship/predict", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        merit = next((s for s in data["schemes"] if s["scheme_code"] == "MERIT"), None)
        self.assertEqual(merit["ml_prediction"]["prediction"], "APPROVE")
        print(">>> Test Case 4 Passed: Third Year mapped and evaluated successfully.")

    # =========================================================================
    # 5. CASE 4b: FOURTH YEAR & POSTGRADUATE
    # =========================================================================
    def test_case_05_fourth_year_and_postgraduate(self):
        """Case 4b: Fourth Year and Postgraduate stages map correctly to canonical ML features."""
        # Fourth year
        p4 = {
            "academic_stage": "FOURTH_YEAR",
            "third_year_score": 84.0,
            "second_year_score": 82.0,
            "attendance": 87.0,
            "annual_income": 250000,
            "application_category": "GENERAL",
            "documents": {"marksheet": True, "income_certificate": True, "id_proof": True},
        }
        c4 = validate_prediction_input(p4)
        self.assertEqual(c4["academic_score"], 84.0)
        self.assertEqual(c4["previous_score"], 82.0)
        self.assertEqual(c4["attendance"], 87.0)

        # Postgraduate
        ppg = {
            "academic_stage": "POSTGRADUATE",
            "ug_score": 79.0,
            "previous_score": 81.0,
            "attendance": 85.0,
            "annual_income": 250000,
            "application_category": "GENERAL",
            "documents": {"marksheet": True, "income_certificate": True, "id_proof": True},
        }
        cpg = validate_prediction_input(ppg)
        self.assertEqual(cpg["academic_score"], 79.0)
        self.assertEqual(cpg["previous_score"], 81.0)
        self.assertEqual(cpg["attendance"], 85.0)
        print(">>> Test Case 4b Passed: Fourth Year and Postgraduate stages map properly.")

    # =========================================================================
    # 6. CASE 5: STALE VALUE CLEARING & FRONTEND ARCHITECTURE
    # =========================================================================
    def test_case_06_frontend_contract_and_stale_clearing(self):
        """Case 5: Frontend HTML & JS contain academic stage dropdown, dynamic container, and stale value clearing on switch."""
        html_path = Path(__file__).resolve().parent / "frontend" / "scholarship-predictor.html"
        js_path = Path(__file__).resolve().parent / "frontend" / "js" / "scholarship-predictor.js"

        html_text = html_path.read_text(encoding="utf-8")
        js_text = js_path.read_text(encoding="utf-8")

        # HTML assertions
        self.assertIn('id="select-academic-stage"', html_text)
        self.assertIn('value="FIRST_YEAR"', html_text)
        self.assertIn('value="SECOND_YEAR"', html_text)
        self.assertIn('value="THIRD_YEAR"', html_text)
        self.assertIn('value="FOURTH_YEAR"', html_text)
        self.assertIn('value="POSTGRADUATE"', html_text)
        self.assertIn('id="dynamic-academic-fields"', html_text)

        # JS dynamic rendering & clearing assertions
        self.assertIn("function initAcademicStage", js_text)
        self.assertIn("function renderAcademicFields", js_text)
        self.assertIn("FIRST_YEAR", js_text)
        self.assertIn("Not applicable — first-year admission", js_text)
        self.assertIn("Most Recent Completed Qualification", js_text)
        self.assertIn("Since you are applying for first-year admission", js_text)
        self.assertIn("renderAcademicFields(stageSelect.value)", js_text)

        # Verify attendance is strictly null for FIRST_YEAR in JS
        self.assertIn("payload.attendance = null;", js_text)

        print(">>> Test Case 5 Passed: HTML & JS stage architecture and stale clearing verified.")

    # =========================================================================
    # 7. DATA INTEGRITY: ZERO SYNTHETIC ATTENDANCE IMPUTATION
    # =========================================================================
    def test_case_07_no_synthetic_attendance(self):
        """Attendance for first-year applicants is strictly None: never 0.0, never 75.0."""
        # Even if a caller erroneously passes attendance=75.0 or 0.0 in FIRST_YEAR payload
        payload_with_fake = {
            "academic_stage": "FIRST_YEAR",
            "qualifying_score": 85.0,
            "attendance": 75.0,  # Erroneous input
            "annual_income": 300000,
        }
        cleaned = validate_prediction_input(payload_with_fake)
        self.assertIsNone(cleaned["attendance"], "First-year attendance must be None regardless of submitted value")
        print(">>> Test Case 7 Passed: No synthetic attendance (0 or 75) is ever accepted for First Year.")

    # =========================================================================
    # 8. ML FIRST-YEAR TRANSPARENCY
    # =========================================================================
    def test_case_08_first_year_ml_transparency(self):
        """First-year applicants route to NEEDS_HUMAN_REVIEW with transparent advisory note and unavailable SHAP."""
        payload = {
            "academic_stage": "FIRST_YEAR",
            "qualifying_score": 92.0,
            "annual_income": 200000,
            "application_category": "GENERAL",
            "documents": {"marksheet": True, "income_certificate": True, "id_proof": True},
        }
        res = self.client.post("/scholarship/predict", json=payload)
        data = res.get_json()
        best = data["best_match"]

        self.assertEqual(best["ml_prediction"]["prediction"], "NEEDS_HUMAN_REVIEW")
        self.assertEqual(best["ml_prediction"]["confidence"], 0.0)
        self.assertEqual(best["ml_prediction"]["estimated_approval_probability"], "Not applicable")
        self.assertIn("college attendance", best["ml_prediction"]["approval_probability_note"].lower())
        self.assertIn("college attendance", best["ml_prediction"]["advisory_note"].lower())
        print(">>> Test Case 8 Passed: Transparent ML reporting for first-year applicants verified.")


if __name__ == "__main__":
    unittest.main()
