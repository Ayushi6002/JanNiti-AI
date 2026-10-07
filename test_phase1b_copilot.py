"""
test_phase1b_copilot.py
--------------------------------------------------------------------------------
Phase 1B Test Suite — AI Scholarship Eligibility Copilot
Covers:
  - Step 6: Authorization Tests (Student access, 401, Admin blocked, ID isolation, DB read-only)
  - Step 7: Eligibility Rule Tests (TEST 1 - TEST 7)
  - Step 8: Data Integrity Test (Snapshot comparison, Zero Database Mutations)
--------------------------------------------------------------------------------
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app
from backend.auth_service import login
from backend.supabase_client import supabase
from backend.copilot_service import (
    evaluate_student_eligibility,
    build_scheme_verification_summary,
)


class TestPhase1BCopilot(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

        # Real Supabase applicant
        cls.student_auth = login("ayushi1219jain@gmail.com", "JanNitiTest@2026")
        cls.student_token = cls.student_auth.session.access_token
        cls.student_id = cls.student_auth.user.id
        cls.student_headers = {"Authorization": f"Bearer {cls.student_token}"}

        # Real Supabase admin
        cls.admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
        cls.admin_token = cls.admin_auth.session.access_token
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

    # =========================================================================
    # STEP 6: AUTHORIZATION TESTS
    # =========================================================================

    def test_auth_01_student_can_access_own_copilot(self):
        """1. Authenticated student can access their own Copilot endpoint."""
        res = self.client.get("/student/copilot/eligibility", headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["student"]["id"], self.student_id)
        self.assertIn("scholarships", data)
        self.assertIsInstance(data["scholarships"], list)
        self.assertGreaterEqual(len(data["scholarships"]), 1)
        print(">>> Auth Test 1 Passed: Student successfully accessed own Copilot.")

    def test_auth_02_unauthenticated_gets_401(self):
        """2. Unauthenticated user gets 401 Unauthorized."""
        res = self.client.get("/student/copilot/eligibility")
        self.assertEqual(res.status_code, 401)
        res_post = self.client.post("/student/copilot/eligibility", json={"candidate_data": {}})
        self.assertEqual(res_post.status_code, 401)
        print(">>> Auth Test 2 Passed: Unauthenticated request received 401.")

    def test_auth_03_admin_blocked_from_student_endpoint(self):
        """3. Admin role is rejected with 403 on student Copilot endpoint."""
        res = self.client.get("/student/copilot/eligibility", headers=self.admin_headers)
        self.assertEqual(res.status_code, 403)
        res_post = self.client.post("/student/copilot/eligibility", json={"candidate_data": {}}, headers=self.admin_headers)
        self.assertEqual(res_post.status_code, 403)
        print(">>> Auth Test 3 Passed: Admin correctly blocked with 403.")

    def test_auth_04_student_cannot_request_other_student_data(self):
        """4. Student endpoint does NOT trust applicant_id parameter from caller."""
        other_fake_id = "00000000-0000-0000-0000-000000000000"
        # Passing applicant_id in query params or JSON body must be ignored
        res = self.client.get(f"/student/copilot/eligibility?applicant_id={other_fake_id}", headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        # Must return the authenticated student's ID, never the spoofed one
        self.assertEqual(data["student"]["id"], self.student_id)
        self.assertNotEqual(data["student"]["id"], other_fake_id)

        res_post = self.client.post(
            "/student/copilot/eligibility",
            json={"applicant_id": other_fake_id, "candidate_data": {}},
            headers=self.student_headers,
        )
        self.assertEqual(res_post.status_code, 200)
        post_data = res_post.get_json()
        self.assertEqual(post_data["student"]["id"], self.student_id)
        print(">>> Auth Test 4 Passed: Client-supplied applicant_id ignored; session user enforced.")

    def test_auth_05_copilot_does_not_modify_application_records(self):
        """5. Copilot calls do not modify application records."""
        before = supabase.table("applications").select("id, status, updated_at").eq("applicant_id", self.student_id).execute()
        self.client.get("/student/copilot/eligibility", headers=self.student_headers)
        after = supabase.table("applications").select("id, status, updated_at").eq("applicant_id", self.student_id).execute()
        self.assertEqual(before.data, after.data)
        print(">>> Auth Test 5 Passed: Zero modifications to application records.")

    def test_auth_06_copilot_does_not_modify_scholarship_rules(self):
        """6. Copilot calls do not modify scholarship rules or schemes."""
        before_schemes = supabase.table("scholarship_schemes").select("id, is_active").execute()
        before_rules = supabase.table("scholarship_rules").select("id, rule_code").execute()
        self.client.get("/student/copilot/eligibility", headers=self.student_headers)
        after_schemes = supabase.table("scholarship_schemes").select("id, is_active").execute()
        after_rules = supabase.table("scholarship_rules").select("id, rule_code").execute()
        self.assertEqual(before_schemes.data, after_schemes.data)
        self.assertEqual(before_rules.data, after_rules.data)
        print(">>> Auth Test 6 Passed: Zero modifications to scholarship rules or schemes.")

    def test_auth_07_copilot_does_not_modify_decisions(self):
        """7. Copilot calls do not modify human decisions."""
        before = supabase.table("decisions").select("id, decision").execute()
        self.client.get("/student/copilot/eligibility", headers=self.student_headers)
        after = supabase.table("decisions").select("id, decision").execute()
        self.assertEqual(before.data, after.data)
        print(">>> Auth Test 7 Passed: Zero modifications to human decisions.")

    def test_auth_08_copilot_does_not_create_ml_predictions(self):
        """8. Copilot calls do not insert rows into ai_predictions."""
        before = supabase.table("ai_predictions").select("id").execute()
        self.client.get("/student/copilot/eligibility", headers=self.student_headers)
        after = supabase.table("ai_predictions").select("id").execute()
        self.assertEqual(len(before.data), len(after.data))
        print(">>> Auth Test 8 Passed: Zero new ML predictions created by Copilot.")

    # =========================================================================
    # STEP 7: ELIGIBILITY TESTS (TEST 1 - TEST 7)
    # =========================================================================

    def test_eligibility_01_profile_meeting_all_merit_criteria(self):
        """
        TEST 1: Profile meeting all Merit criteria (academic >= 75, prev >= 70,
        attendance >= 75, income <= 800000, all required docs verified).
        Expected: ELIGIBLE.
        """
        candidate = {
            "academic_score": 85.0,
            "previous_score": 80.0,
            "attendance": 85.0,
            "annual_income": 400000,
            "application_category": "GEN",
        }
        mock_docs = [
            {"document_type": "marksheet", "verification_status": "VERIFIED"},
            {"document_type": "id_proof", "verification_status": "VERIFIED"},
            {"document_type": "income_certificate", "verification_status": "VERIFIED"},
        ]
        with patch("backend.copilot_service.get_applicant_all_documents", return_value=mock_docs):
            report = evaluate_student_eligibility(self.student_id, candidate_data=candidate)
            merit = next((s for s in report["scholarships"] if s["scheme_code"] == "MERIT"), None)
            self.assertIsNotNone(merit)
            self.assertEqual(merit["status"], "ELIGIBLE")
            self.assertEqual(merit["match_percentage"], 100)
            self.assertIn("satisfy all configured", merit["explanation"].lower())
            print(f">>> Eligibility Test 1 Passed: Merit evaluation is ELIGIBLE ({merit['match_percentage']}%).")

    def test_eligibility_02_income_above_merit_threshold(self):
        """
        TEST 2: Income above Merit threshold (income > 800000).
        Expected: NOT_ELIGIBLE.
        """
        candidate = {
            "academic_score": 88.0,
            "previous_score": 82.0,
            "attendance": 90.0,
            "annual_income": 950000,  # Threshold is <= 800000
        }
        mock_docs = [
            {"document_type": "marksheet", "verification_status": "VERIFIED"},
            {"document_type": "id_proof", "verification_status": "VERIFIED"},
            {"document_type": "income_certificate", "verification_status": "VERIFIED"},
        ]
        with patch("backend.copilot_service.get_applicant_all_documents", return_value=mock_docs):
            report = evaluate_student_eligibility(self.student_id, candidate_data=candidate)
            merit = next((s for s in report["scholarships"] if s["scheme_code"] == "MERIT"), None)
            self.assertIsNotNone(merit)
            self.assertEqual(merit["status"], "NOT_ELIGIBLE")
            self.assertGreater(len(merit["failed_criteria"]), 0)
            income_failed = any("income" in str(f.get("criteria", "")).lower() or "income" in str(f.get("rule_name", "")).lower() for f in merit["failed_criteria"])
            self.assertTrue(income_failed)
            print(f">>> Eligibility Test 2 Passed: High income correctly results in NOT_ELIGIBLE.")

    def test_eligibility_03_academic_score_below_threshold(self):
        """
        TEST 3: Academic score below threshold (e.g. 60 < 75).
        Expected: NOT_ELIGIBLE.
        """
        candidate = {
            "academic_score": 60.0,  # Below 75
            "previous_score": 80.0,
            "attendance": 85.0,
            "annual_income": 300000,
        }
        mock_docs = [
            {"document_type": "marksheet", "verification_status": "VERIFIED"},
            {"document_type": "id_proof", "verification_status": "VERIFIED"},
            {"document_type": "income_certificate", "verification_status": "VERIFIED"},
        ]
        with patch("backend.copilot_service.get_applicant_all_documents", return_value=mock_docs):
            report = evaluate_student_eligibility(self.student_id, candidate_data=candidate)
            merit = next((s for s in report["scholarships"] if s["scheme_code"] == "MERIT"), None)
            self.assertIsNotNone(merit)
            self.assertEqual(merit["status"], "NOT_ELIGIBLE")
            score_failed = any("academic" in str(f.get("criteria", "")).lower() or "academic" in str(f.get("rule_name", "")).lower() for f in merit["failed_criteria"])
            self.assertTrue(score_failed)
            print(f">>> Eligibility Test 3 Passed: Low score correctly results in NOT_ELIGIBLE.")

    def test_eligibility_04_all_numeric_pass_but_income_cert_missing(self):
        """
        TEST 4: All numeric criteria pass but income certificate missing.
        Expected: NEEDS_VERIFICATION.
        """
        candidate = {
            "academic_score": 85.0,
            "previous_score": 80.0,
            "attendance": 85.0,
            "annual_income": 300000,
        }
        # Only marksheet and id_proof uploaded; income_certificate is missing
        mock_docs = [
            {"document_type": "marksheet", "verification_status": "VERIFIED"},
            {"document_type": "id_proof", "verification_status": "VERIFIED"},
        ]
        with patch("backend.copilot_service.get_applicant_all_documents", return_value=mock_docs):
            report = evaluate_student_eligibility(self.student_id, candidate_data=candidate)
            merit = next((s for s in report["scholarships"] if s["scheme_code"] == "MERIT"), None)
            self.assertIsNotNone(merit)
            self.assertEqual(merit["status"], "NEEDS_VERIFICATION")
            self.assertIn("income certificate", merit["explanation"].lower())
            self.assertIsNotNone(merit["next_action"])
            print(">>> Eligibility Test 4 Passed: Missing document correctly yields NEEDS_VERIFICATION.")

    def test_eligibility_05_evaluate_all_three_scholarship_schemes_simultaneously(self):
        """
        TEST 5: Evaluate all three active scholarship schemes simultaneously.
        Expected: Separate result for each (MERIT, NEED_BASED, CATEGORY).
        """
        res = self.client.get("/student/copilot/eligibility", headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        codes = [s["scheme_code"] for s in data["scholarships"]]
        self.assertIn("MERIT", codes)
        self.assertIn("NEED_BASED", codes)
        self.assertIn("CATEGORY", codes)
        # Check that each scheme has distinct results, criteria, and explanations
        for s in data["scholarships"]:
            self.assertIn(s["status"], ["ELIGIBLE", "NEEDS_VERIFICATION", "NOT_ELIGIBLE"])
            self.assertIsInstance(s["match_percentage"], int)
            self.assertTrue(0 <= s["match_percentage"] <= 100)
            self.assertIsInstance(s["explanation"], str)
            self.assertTrue(len(s["explanation"]) > 0)
        print(f">>> Eligibility Test 5 Passed: Evaluated schemes simultaneously: {codes}")

    def test_eligibility_06_document_status_uncertain(self):
        """
        TEST 6: Document status UNCERTAIN or PENDING.
        Expected: NEEDS_VERIFICATION where that document is required.
        """
        candidate = {
            "academic_score": 85.0,
            "previous_score": 80.0,
            "attendance": 85.0,
            "annual_income": 300000,
        }
        # income_certificate has UNCERTAIN verification status
        mock_docs = [
            {"document_type": "marksheet", "verification_status": "VERIFIED"},
            {"document_type": "id_proof", "verification_status": "VERIFIED"},
            {"document_type": "income_certificate", "verification_status": "UNCERTAIN"},
        ]
        with patch("backend.copilot_service.get_applicant_all_documents", return_value=mock_docs):
            report = evaluate_student_eligibility(self.student_id, candidate_data=candidate)
            merit = next((s for s in report["scholarships"] if s["scheme_code"] == "MERIT"), None)
            self.assertIsNotNone(merit)
            self.assertEqual(merit["status"], "NEEDS_VERIFICATION")
            print(">>> Eligibility Test 6 Passed: UNCERTAIN document yields NEEDS_VERIFICATION.")

    def test_eligibility_07_existing_application_with_human_decision_not_altered(self):
        """
        TEST 7: Existing application with human decision.
        Expected: Copilot reports eligibility only. It must NOT alter final decision.
        """
        # Fetch existing decisions for any applications of this student
        apps = supabase.table("applications").select("id, status").eq("applicant_id", self.student_id).execute().data
        app_ids = [a["id"] for a in apps]
        before_decisions = []
        if app_ids:
            before_decisions = supabase.table("decisions").select("id, application_id, decision").in_("application_id", app_ids).execute().data

        # Call copilot
        res = self.client.get("/student/copilot/eligibility", headers=self.student_headers)
        self.assertEqual(res.status_code, 200)

        # Re-check decisions
        after_decisions = []
        if app_ids:
            after_decisions = supabase.table("decisions").select("id, application_id, decision").in_("application_id", app_ids).execute().data

        self.assertEqual(before_decisions, after_decisions)
        print(">>> Eligibility Test 7 Passed: Authoritative human decisions completely unaltered.")

    # =========================================================================
    # STEP 8: DATA INTEGRITY TEST (ZERO MUTATIONS)
    # =========================================================================

    def test_data_integrity_zero_database_mutations(self):
        """
        STEP 8: Before calling Copilot:
        capture: application, profile, documents, decisions, ai_predictions, appeals
        After calling: compare all values.
        Expected: ZERO DATABASE MUTATIONS.
        """
        # Snapshots before
        snap_apps = supabase.table("applications").select("*").execute().data
        snap_profiles = supabase.table("profiles").select("*").execute().data
        snap_docs = supabase.table("documents").select("*").execute().data
        snap_decisions = supabase.table("decisions").select("*").execute().data
        snap_predictions = supabase.table("ai_predictions").select("*").execute().data
        snap_appeals = supabase.table("appeals").select("*").execute().data

        # Call GET endpoint
        res_get = self.client.get("/student/copilot/eligibility", headers=self.student_headers)
        self.assertEqual(res_get.status_code, 200)

        # Call POST pre-submission endpoint with candidate values
        candidate_payload = {
            "candidate_data": {
                "academic_score": 92.5,
                "previous_score": 88.0,
                "attendance": 90.0,
                "annual_income": 200000,
                "application_category": "OBC",
            }
        }
        res_post = self.client.post("/student/copilot/eligibility", json=candidate_payload, headers=self.student_headers)
        self.assertEqual(res_post.status_code, 200)

        # Snapshots after
        post_apps = supabase.table("applications").select("*").execute().data
        post_profiles = supabase.table("profiles").select("*").execute().data
        post_docs = supabase.table("documents").select("*").execute().data
        post_decisions = supabase.table("decisions").select("*").execute().data
        post_predictions = supabase.table("ai_predictions").select("*").execute().data
        post_appeals = supabase.table("appeals").select("*").execute().data

        # Strict equality assertions across all 6 critical tables
        self.assertEqual(len(snap_apps), len(post_apps), "Applications row count changed!")
        self.assertEqual(snap_apps, post_apps, "Applications content mutated!")

        self.assertEqual(len(snap_profiles), len(post_profiles), "Profiles row count changed!")
        self.assertEqual(snap_profiles, post_profiles, "Profiles content mutated!")

        self.assertEqual(len(snap_docs), len(post_docs), "Documents row count changed!")
        self.assertEqual(snap_docs, post_docs, "Documents content mutated!")

        self.assertEqual(len(snap_decisions), len(post_decisions), "Decisions row count changed!")
        self.assertEqual(snap_decisions, post_decisions, "Decisions content mutated!")

        self.assertEqual(len(snap_predictions), len(post_predictions), "AI predictions row count changed!")
        self.assertEqual(snap_predictions, post_predictions, "AI predictions content mutated!")

        self.assertEqual(len(snap_appeals), len(post_appeals), "Appeals row count changed!")
        self.assertEqual(snap_appeals, post_appeals, "Appeals content mutated!")

        print(">>> Step 8 Data Integrity Passed: ABSOLUTELY ZERO DATABASE MUTATIONS.")


if __name__ == "__main__":
    unittest.main()
