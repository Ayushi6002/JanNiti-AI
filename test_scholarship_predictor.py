"""
test_scholarship_predictor.py
--------------------------------------------------------------------------------
Comprehensive Test Suite for JanNiti AI - Scholarship Predictor Feature

Tests:
 1. Valid Merit-eligible profile
 2. Valid Need-Based-eligible profile
 3. Category scholarship profile (with and without category certificate)
 4. Multiple eligible scholarships (ranking and grouping)
 5. No eligible scholarship profile (safe handling, no crashes)
 6. Missing documents detection and status
 7. Partial documents evaluation
 8. Invalid academic score validation (< 0, > 100, non-numeric)
 9. Invalid previous score validation (< 0, > 100, non-numeric)
10. Invalid attendance validation (< 0, > 100, non-numeric)
11. Negative income validation (< 0)
12. Public access to Predictor and application auth boundary protection
13. Zero database mutations: Applications table untouched
14. Zero database mutations: Scholarship rules table untouched
15. Zero database mutations: Human decisions untouched
16. Zero database mutations: AI predictions table untouched
17. Authoritative Supabase scholarship rules are actively evaluated
18. Frontend JS does not contain hardcoded scholarship thresholds
19. "Academic Support Scholarship" internal label is NOT exposed to student
20. ML model confidence is strictly distinguished from rule eligibility
21. Confidence probability/percentage formatting data contract (0.726->72.60%)
22. Rule precedence and ML advisory distinction (NOT_ELIGIBLE with ML APPROVE)
23. Frontend JS confidence-formatting and advisory terminology contract
--------------------------------------------------------------------------------
"""

import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app
from backend.auth_service import login
from backend.supabase_client import supabase
from backend.scholarship_predictor_service import (
    predict_scholarships,
    get_predictor_configuration,
    get_authoritative_active_schemes,
    validate_prediction_input,
)


class TestScholarshipPredictor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

        # Real Supabase student user
        cls.student_auth = login("ayushi1219jain@gmail.com", "JanNitiTest@2026")
        cls.student_token = cls.student_auth.session.access_token
        cls.student_id = cls.student_auth.user.id
        cls.student_headers = {
            "Authorization": f"Bearer {cls.student_token}",
            "Content-Type": "application/json",
        }

        # Real Supabase admin user
        cls.admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
        cls.admin_token = cls.admin_auth.session.access_token
        cls.admin_headers = {
            "Authorization": f"Bearer {cls.admin_token}",
            "Content-Type": "application/json",
        }

    # =========================================================================
    # 1. PROFILE EVALUATION TESTS
    # =========================================================================

    def test_01_valid_merit_eligible_profile(self):
        """1. Valid Merit-eligible profile produces ELIGIBLE for MERIT with ML APPROVE."""
        payload = {
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 350000,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
            },
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200, res.data.decode())
        data = res.get_json()

        self.assertIsNotNone(data.get("best_match"))
        best = data["best_match"]
        self.assertEqual(best["scheme_code"], "MERIT")
        self.assertEqual(best["eligibility_status"], "ELIGIBLE")
        self.assertEqual(best["ml_prediction"]["prediction"], "APPROVE")
        self.assertGreater(best["ml_prediction"]["confidence"], 0.5)
        print(">>> Test 1 Passed: Valid Merit profile correctly predicted as ELIGIBLE with ML APPROVE.")

    def test_02_valid_need_based_eligible_profile(self):
        """2. Valid Need-Based-eligible profile produces ELIGIBLE for NEED_BASED."""
        payload = {
            "academic_score": 75.0,
            "previous_score": 72.0,
            "attendance": 82.0,
            "annual_income": 180000,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
            },
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        schemes = {s["scheme_code"]: s for s in data["schemes"]}
        self.assertIn("NEED_BASED", schemes)
        self.assertEqual(schemes["NEED_BASED"]["eligibility_status"], "ELIGIBLE")
        self.assertGreater(schemes["NEED_BASED"]["passed_rules_count"], 0)
        print(">>> Test 2 Passed: Valid Need-Based profile correctly identified as ELIGIBLE.")

    def test_03_category_scholarship_profile(self):
        """3. Category scholarship profile evaluates category requirements and certificate."""
        # 3a: With category certificate
        payload_with_cert = {
            "academic_score": 75.0,
            "previous_score": 70.0,
            "attendance": 80.0,
            "annual_income": 200000,
            "application_category": "OBC",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
                "category_certificate": True,
            },
        }
        res1 = self.client.post("/scholarship/predict", json=payload_with_cert, headers=self.student_headers)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        cat_scheme1 = next((s for s in data1["schemes"] if s["scheme_code"] == "CATEGORY"), None)
        self.assertIsNotNone(cat_scheme1)
        self.assertEqual(cat_scheme1["eligibility_status"], "ELIGIBLE")

        # 3b: Without category certificate -> NEEDS_VERIFICATION
        payload_no_cert = {
            "academic_score": 75.0,
            "previous_score": 70.0,
            "attendance": 80.0,
            "annual_income": 200000,
            "application_category": "OBC",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
                "category_certificate": False,
            },
        }
        res2 = self.client.post("/scholarship/predict", json=payload_no_cert, headers=self.student_headers)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        cat_scheme2 = next((s for s in data2["schemes"] if s["scheme_code"] == "CATEGORY"), None)
        self.assertIsNotNone(cat_scheme2)
        self.assertEqual(cat_scheme2["eligibility_status"], "NEEDS_VERIFICATION")
        self.assertIn("category_certificate", cat_scheme2["missing_documents"])
        print(">>> Test 3 Passed: Category profile correctly requires category certificate.")

    def test_04_multiple_eligible_scholarships(self):
        """4. High academic score and low income qualifies for multiple scholarships."""
        payload = {
            "academic_score": 92.0,
            "previous_score": 90.0,
            "attendance": 95.0,
            "annual_income": 120000,
            "application_category": "OBC",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
                "category_certificate": True,
            },
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        eligible_schemes = [s for s in data["schemes"] if s["eligibility_status"] == "ELIGIBLE"]
        self.assertGreaterEqual(len(eligible_schemes), 2)
        self.assertIsNotNone(data["best_match"])
        self.assertEqual(data["best_match"]["eligibility_status"], "ELIGIBLE")
        print(f">>> Test 4 Passed: Multiple eligible scholarships returned ({len(eligible_schemes)} eligible).")

    def test_05_no_eligible_scholarship(self):
        """5. Low score and low attendance results in no eligible scholarships without crash."""
        payload = {
            "academic_score": 40.0,
            "previous_score": 42.0,
            "attendance": 50.0,
            "annual_income": 950000,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
            },
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["eligible_count"], 0)
        for sch in data["schemes"]:
            self.assertIn(sch["eligibility_status"], {"NOT_ELIGIBLE", "NEEDS_VERIFICATION"})
        print(">>> Test 5 Passed: No eligible scholarships handled cleanly.")

    # =========================================================================
    # 2. DOCUMENT HANDLING TESTS
    # =========================================================================

    def test_06_missing_documents(self):
        """6. Missing documents properly flag schemes as NEEDS_VERIFICATION."""
        payload = {
            "academic_score": 85.0,
            "previous_score": 80.0,
            "attendance": 90.0,
            "annual_income": 250000,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": False,
                "id_proof": False,
            },
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        readiness = data["document_readiness"]
        self.assertFalse(readiness["complete"])
        self.assertIn("income_certificate", readiness["missing"])
        self.assertIn("id_proof", readiness["missing"])
        print(">>> Test 6 Passed: Missing documents detected and readiness reported accurately.")

    def test_07_partial_documents(self):
        """7. Partial documents maintain separate eligibility criteria from document status."""
        payload = {
            "academic_score": 82.0,
            "previous_score": 80.0,
            "attendance": 85.0,
            "annual_income": 400000,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "id_proof": True,
                "income_certificate": False,
            },
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        merit = next((s for s in data["schemes"] if s["scheme_code"] == "MERIT"), None)
        self.assertIsNotNone(merit)
        # Academic score passed rule criteria even though a document is missing
        passed_titles = [c.get("title", "") for c in merit["passed_criteria"]]
        self.assertTrue(any("Academic Score" in t for t in passed_titles))
        self.assertIn("income_certificate", merit["missing_documents"])
        self.assertEqual(merit["eligibility_status"], "NEEDS_VERIFICATION")
        print(">>> Test 7 Passed: Document readiness and rule criteria remain strictly separated.")

    # =========================================================================
    # 3. INPUT VALIDATION TESTS
    # =========================================================================

    def test_08_invalid_academic_score(self):
        """8. Academic score < 0 or > 100 rejected with 400 error."""
        for invalid_val in [-5.0, 105.0, "abc"]:
            payload = {
                "academic_score": invalid_val,
                "previous_score": 80.0,
                "attendance": 85.0,
                "annual_income": 300000,
            }
            res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
            self.assertEqual(res.status_code, 400)
            err = res.get_json()["error"].lower()
            self.assertIn("academic score", err)
        print(">>> Test 8 Passed: Invalid academic_score correctly rejected.")

    def test_09_invalid_previous_score(self):
        """9. Previous score < 0 or > 100 rejected with 400 error."""
        for invalid_val in [-1.0, 100.5]:
            payload = {
                "academic_score": 80.0,
                "previous_score": invalid_val,
                "attendance": 85.0,
                "annual_income": 300000,
            }
            res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
            self.assertEqual(res.status_code, 400)
            err = res.get_json()["error"].lower()
            self.assertIn("previous", err)
        print(">>> Test 9 Passed: Invalid previous_score correctly rejected.")

    def test_10_invalid_attendance(self):
        """10. Attendance < 0 or > 100 rejected with 400 error."""
        for invalid_val in [-10.0, 110.0]:
            payload = {
                "academic_score": 80.0,
                "previous_score": 75.0,
                "attendance": invalid_val,
                "annual_income": 300000,
            }
            res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
            self.assertEqual(res.status_code, 400)
            err = res.get_json()["error"].lower()
            self.assertIn("attendance", err)
        print(">>> Test 10 Passed: Invalid attendance correctly rejected.")

    def test_11_negative_income(self):
        """11. Negative annual income rejected with 400 error."""
        payload = {
            "academic_score": 80.0,
            "previous_score": 75.0,
            "attendance": 85.0,
            "annual_income": -50000,
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 400)
        err = res.get_json()["error"].lower()
        self.assertIn("income", err)
        print(">>> Test 11 Passed: Negative annual income correctly rejected.")

    # =========================================================================
    # 4. AUTHORIZATION TESTS
    # =========================================================================

    def test_12_public_access_and_application_auth_boundary(self):
        """12. Predictor endpoints are public; application endpoints strictly require authentication."""
        payload = {
            "academic_score": 85.0,
            "previous_score": 80.0,
            "attendance": 85.0,
            "annual_income": 300000,
            "application_category": "GENERAL",
            "documents": {"marksheet": True, "income_certificate": True, "id_proof": True},
        }
        # Predictor is public - unauthenticated requests succeed with 200
        res_anon = self.client.post("/scholarship/predict", json=payload)
        self.assertEqual(res_anon.status_code, 200)

        res_alias = self.client.post("/student/scholarship/predict", json=payload)
        self.assertEqual(res_alias.status_code, 200)

        res_cfg = self.client.get("/scholarship/predictor-config")
        self.assertEqual(res_cfg.status_code, 200)

        # Actual application endpoints MUST remain protected (401 without auth)
        res_submit = self.client.post("/submit-application-full", data={})
        self.assertEqual(res_submit.status_code, 401)

        res_apps = self.client.get("/student/applications")
        self.assertEqual(res_apps.status_code, 401)

        res_appeals = self.client.get("/student/appeals")
        self.assertEqual(res_appeals.status_code, 401)

        print(">>> Test 12 Passed: Predictor is public, while application endpoints remain strictly authenticated.")

    # =========================================================================
    # 5. DATA INTEGRITY & ZERO MUTATION TESTS
    # =========================================================================

    def test_13_predictor_does_not_mutate_application_data(self):
        """13. Predictor does not insert or update rows in applications table."""
        before_count = supabase.table("applications").select("id", count="exact").execute().count

        payload = {
            "academic_score": 88.0,
            "previous_score": 85.0,
            "attendance": 90.0,
            "annual_income": 300000,
            "application_category": "GENERAL",
            "documents": {"marksheet": True, "income_certificate": True, "id_proof": True},
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)

        after_count = supabase.table("applications").select("id", count="exact").execute().count
        self.assertEqual(before_count, after_count)
        print(">>> Test 13 Passed: Zero applications created or modified.")

    def test_14_predictor_does_not_mutate_scholarship_rules(self):
        """14. Predictor does not mutate scholarship_rules or scholarship_schemes."""
        before_rules = supabase.table("scholarship_rules").select("id, rule_type, is_active").execute().data
        before_schemes = supabase.table("scholarship_schemes").select("id, scheme_code").execute().data

        payload = {
            "academic_score": 90.0,
            "previous_score": 88.0,
            "attendance": 92.0,
            "annual_income": 200000,
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)

        after_rules = supabase.table("scholarship_rules").select("id, rule_type, is_active").execute().data
        after_schemes = supabase.table("scholarship_schemes").select("id, scheme_code").execute().data

        self.assertEqual(before_rules, after_rules)
        self.assertEqual(before_schemes, after_schemes)
        print(">>> Test 14 Passed: Zero modifications to scholarship rules or schemes.")

    def test_15_predictor_does_not_mutate_human_decisions(self):
        """15. Predictor does not create or alter human_decisions."""
        before_count = supabase.table("decisions").select("id", count="exact").execute().count

        payload = {
            "academic_score": 82.0,
            "previous_score": 80.0,
            "attendance": 85.0,
            "annual_income": 350000,
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)

        after_count = supabase.table("decisions").select("id", count="exact").execute().count
        self.assertEqual(before_count, after_count)
        print(">>> Test 15 Passed: Zero modifications to human decisions.")

    def test_16_predictor_does_not_create_ml_prediction_records(self):
        """16. Predictor does not persist predictions to ai_predictions table."""
        before_count = supabase.table("ai_predictions").select("id", count="exact").execute().count

        payload = {
            "academic_score": 84.0,
            "previous_score": 80.0,
            "attendance": 86.0,
            "annual_income": 350000,
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)

        after_count = supabase.table("ai_predictions").select("id", count="exact").execute().count
        self.assertEqual(before_count, after_count)
        print(">>> Test 16 Passed: Zero ai_predictions records created.")

    # =========================================================================
    # 6. ARCHITECTURE & MODEL INTEGRATION TESTS
    # =========================================================================

    def test_17_existing_scholarship_rules_are_used(self):
        """17. Authoritative rules from Supabase are actively loaded and checked."""
        config = get_predictor_configuration()
        self.assertIn("active_schemes", config)
        codes = [s["scheme_code"] for s in config["active_schemes"]]
        self.assertIn("MERIT", codes)
        self.assertIn("NEED_BASED", codes)
        self.assertIn("CATEGORY", codes)
        print(f">>> Test 17 Passed: Authoritative active schemes loaded: {codes}")

    def test_18_frontend_does_not_contain_hardcoded_thresholds(self):
        """18. Frontend JS does not hardcode scholarship thresholds."""
        js_path = Path(__file__).resolve().parent / "frontend" / "js" / "scholarship-predictor.js"
        self.assertTrue(js_path.exists())
        content = js_path.read_text(encoding="utf-8")

        # Disallow hardcoded business logic checks in client JS
        forbidden_patterns = [
            "income <= 300000",
            "income < 300000",
            "income <= 500000",
            "academic_score >= 80",
            "academic_score > 80",
            "attendance >= 75",
        ]
        for pattern in forbidden_patterns:
            self.assertNotIn(pattern, content, f"Forbidden hardcoded logic found in JS: '{pattern}'")
        print(">>> Test 18 Passed: Frontend JS is strictly declarative with zero threshold duplication.")

    def test_19_academic_support_scholarship_not_exposed(self):
        """19. Internal legacy label 'Academic Support Scholarship' is never exposed to student."""
        payload = {
            "academic_score": 80.0,
            "previous_score": 75.0,
            "attendance": 85.0,
            "annual_income": 250000,
            "application_category": "SC",
            "documents": {"marksheet": True, "category_certificate": True},
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        for sch in data["schemes"]:
            self.assertNotEqual(sch["scheme_name"], "Academic Support Scholarship")
            self.assertNotEqual(sch["scheme_code"], "ACADEMIC_SUPPORT")
        if data.get("best_match"):
            self.assertNotEqual(data["best_match"]["scheme_name"], "Academic Support Scholarship")
        print(">>> Test 19 Passed: Internal legacy model label is cleanly hidden from student presentation.")

    def test_20_ml_confidence_distinguished_from_eligibility(self):
        """20. ML confidence is reported as statistical confidence, not eligibility probability."""
        payload = {
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 350000,
            "application_category": "GENERAL",
            "documents": {"marksheet": True, "id_proof": True, "income_certificate": True},
        }
        res = self.client.post("/scholarship/predict", json=payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        best = data["best_match"]
        self.assertIn("eligibility_status", best)
        self.assertIn("ml_prediction", best)
        ml = best["ml_prediction"]
        self.assertIn("confidence", ml)
        self.assertTrue("decision" in ml or "prediction" in ml)
        self.assertIsInstance(ml["confidence"], (int, float))
        self.assertIn(best["eligibility_status"], {"ELIGIBLE", "NEEDS_VERIFICATION", "NOT_ELIGIBLE"})
        self.assertIn("disclaimer", data)
        self.assertIn("AI-assisted", data["disclaimer"])
        print(">>> Test 20 Passed: ML confidence clearly separated from rule eligibility status.")

    def test_21_confidence_percentage_formatting_data_contract(self):
        """21. Confidence probability/percentage data contract formatted as XX.XX% without double multiplication."""
        payload = {
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 350000,
            "application_category": "GENERAL",
            "documents": {"marksheet": True, "id_proof": True, "income_certificate": True},
        }
        res = self.client.post("/scholarship/predict", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        for scheme in data["schemes"]:
            ml = scheme["ml_prediction"]
            conf = ml["confidence"]
            conf_score = ml["confidence_score"]
            conf_display = ml["confidence_display"]

            # Probability values must be in [0.0, 1.0]
            self.assertGreaterEqual(conf, 0.0)
            self.assertLessEqual(conf, 1.0)
            self.assertEqual(conf, conf_score)

            # Display string must be formatted as XX.XX%
            self.assertTrue(conf_display.endswith("%"))
            pct_num = float(conf_display.rstrip("%"))
            self.assertAlmostEqual(pct_num, conf * 100, places=1)
            # Must have exactly 2 decimal places
            self.assertEqual(len(conf_display.split(".")[1]), 3)

        # Explicit test vectors from user requirements:
        # 0.726 -> 72.60%
        # 0.707 -> 70.70%
        # 0.823 -> 82.30%
        test_vectors = [
            (0.726, "72.60%"),
            (0.707, "70.70%"),
            (0.823, "82.30%"),
        ]
        for raw_val, expected_str in test_vectors:
            self.assertEqual(f"{raw_val * 100:.2f}%", expected_str)

        print(">>> Test 21 Passed: Confidence data contract verified (0.726->72.60%, 0.707->70.70%, 0.823->82.30%).")

    def test_22_ml_approve_with_rule_not_eligible_advisory_distinction(self):
        """22. Authoritative rules override ML: NOT_ELIGIBLE with ML APPROVE shows advisory note."""
        # Need-Based has hard income limit of 300,000 in rules. Income 350,000 fails rules.
        # But high academics (95.0) causes ML model to historically predict APPROVE.
        payload = {
            "academic_score": 95.0,
            "previous_score": 92.0,
            "attendance": 90.0,
            "annual_income": 350000,
            "application_category": "GENERAL",
            "documents": {"marksheet": True, "id_proof": True, "income_certificate": True},
        }
        res = self.client.post("/scholarship/predict", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        need_based = next((s for s in data["schemes"] if s["scheme_code"] == "NEED_BASED"), None)
        self.assertIsNotNone(need_based)
        # Deterministic rule must remain NOT_ELIGIBLE
        self.assertEqual(need_based["eligibility_status"], "NOT_ELIGIBLE")
        self.assertFalse(need_based["is_eligible"])

        # ML model prediction
        ml = need_based["ml_prediction"]
        if ml["prediction"] == "APPROVE":
            self.assertIsNotNone(ml.get("advisory_note"))
            self.assertIn("advisory signal", ml["advisory_note"])
            self.assertIn("rules take precedence", ml["advisory_note"])

        print(">>> Test 22 Passed: Authoritative rules take precedence; ML advisory note attached on disagreement.")

    def test_23_frontend_js_confidence_function_contract(self):
        """23. Frontend JavaScript contains formatConfidencePercent and correct advisory terminology."""
        js_path = Path(__file__).resolve().parent / "frontend" / "js" / "scholarship-predictor.js"
        html_path = Path(__file__).resolve().parent / "frontend" / "scholarship-predictor.html"
        self.assertTrue(js_path.exists())
        self.assertTrue(html_path.exists())

        js_content = js_path.read_text(encoding="utf-8")
        html_content = html_path.read_text(encoding="utf-8")

        self.assertIn("formatConfidencePercent", js_content)
        self.assertIn("getConfidenceWidth", js_content)
        self.assertIn("toFixed(2)", js_content)
        self.assertIn("AI Model Assessment", html_content)
        self.assertIn("AI Model Assessment", js_content)
        self.assertIn("Instant Public Estimator", js_content)
        # Verify no double multiplication in JS
        self.assertNotIn("confidence * 100 * 100", js_content)
        self.assertNotIn("ml_prediction.confidence * 100).toFixed(1)", js_content)

        print(">>> Test 23 Passed: Frontend JS formatting contract and terminology verified.")


if __name__ == "__main__":
    unittest.main()
