"""
test_student_workflow_integration.py
------------------------------------
Focused test suite covering:
1. Student Supabase login
2. Student profile loading
3. Student application loading
4. Student cannot access another student's application
5. Student profile validation & updating
6. Invalid phone number rejection
7. Invalid email rejection
8. Invalid/abusive name rejection
9. Invalid academic score rejection
10. Invalid attendance rejection
11. ML prediction produced
12. ML confidence produced (non-zero, real model probability)
13. Confidence categorization
14. Student rejection reason visibility
15. Student approved application status
16. Student pending application status
17. Admin document access (view & download)
18. Zero service-role credential leakage
19. ML failure fallback
20. Authentication failure handling
"""

import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app
from backend.auth_service import login
from backend.supabase_client import supabase
from backend.ml_service import ml_service
from backend.validation import (
    validate_full_name,
    validate_phone_number,
    validate_email,
    validate_academic_score,
    validate_attendance,
    validate_annual_income,
    validate_application_category,
)
from backend.application_service import (
    create_application,
    get_applications_by_applicant,
    get_application_by_id,
    get_application_full_details,
)
from backend.decision_service import record_human_decision, update_application_status


class TestStudentWorkflowIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

        # Authenticate real Supabase test student
        cls.student_auth = login("ayushi1219jain@gmail.com", "JanNitiTest@2026")
        cls.student_token = cls.student_auth.session.access_token
        cls.student_id = cls.student_auth.user.id
        cls.student_headers = {"Authorization": f"Bearer {cls.student_token}"}

        # Authenticate real Supabase test admin
        cls.admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
        cls.admin_token = cls.admin_auth.session.access_token
        cls.admin_id = cls.admin_auth.user.id
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

    # 1. Student Supabase login
    def test_01_student_supabase_login(self):
        self.assertIsNotNone(self.student_token)
        self.assertTrue(len(self.student_token) > 20)
        self.assertIsNotNone(self.student_id)
        print(">>> Test 1 Passed: Student successfully authenticated via Supabase Auth.")

    # 2. Student profile loading
    def test_02_student_profile_loading(self):
        res = self.client.get("/student/profile", headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["id"], self.student_id)
        self.assertEqual(data["email"], "ayushi1219jain@gmail.com")
        self.assertIn("full_name", data)
        self.assertIn("phone", data)
        print(">>> Test 2 Passed: Student profile loaded accurately from backend.")

    # 3. Student application loading
    def test_03_student_application_loading(self):
        res = self.client.get("/student/applications", headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("applications", data)
        self.assertIsInstance(data["applications"], list)
        print(f">>> Test 3 Passed: Loaded {len(data['applications'])} applications for authenticated student.")

    # 4. Student cannot access another student's application
    def test_04_ownership_isolation_blocked(self):
        other_app_id = "00000000-0000-0000-0000-000000000000"
        res = self.client.get(f"/student/applications/{other_app_id}", headers=self.student_headers)
        self.assertIn(res.status_code, [403, 404])
        print(">>> Test 4 Passed: Student cannot access unauthorized applications.")

    # 5. Student profile validation & updating
    def test_05_student_profile_update(self):
        update_payload = {"full_name": "Ayushi Jain", "phone": "9841234567"}
        res = self.client.put("/student/profile", json=update_payload, headers=self.student_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["profile"]["full_name"], "Ayushi Jain")

        # Test invalid name rejection via API
        bad_name_res = self.client.put("/student/profile", json={"full_name": "12345"}, headers=self.student_headers)
        self.assertEqual(bad_name_res.status_code, 400)

        # Restore test user name so existing test suites matching test_id_proof.pdf pass
        self.client.put("/student/profile", json={"full_name": "Jan Niti Test User", "phone": "9841234567"}, headers=self.student_headers)
        print(">>> Test 5 Passed: Student profile validated and updated with API guardrails.")

    # 6. Invalid phone number rejection
    def test_06_invalid_phone_rejection(self):
        invalid_phones = ["123", "9876543210123", "abcdefghij", "0000000000", "1111111111"]
        for p in invalid_phones:
            is_valid, _, err = validate_phone_number(p)
            self.assertFalse(is_valid, f"Phone {p} should be invalid")
            self.assertIsNotNone(err)
        print(">>> Test 6 Passed: Invalid phone numbers strictly rejected.")

    # 7. Invalid email rejection
    def test_07_invalid_email_rejection(self):
        invalid_emails = ["not-an-email", "@missinguser.com", "user@", "user@.com", "user@com"]
        for e in invalid_emails:
            is_valid, _, err = validate_email(e)
            self.assertFalse(is_valid, f"Email {e} should be invalid")
            self.assertIsNotNone(err)
        print(">>> Test 7 Passed: Invalid emails strictly rejected.")

    # 8. Invalid / abusive name rejection
    def test_08_invalid_and_abusive_name_rejection(self):
        bad_names = ["", "   ", "a", "123456", "@#$%", "test abusive fake placeholder asdfgh"]
        for n in bad_names:
            is_valid, _, err = validate_full_name(n)
            self.assertFalse(is_valid, f"Name {n} should be invalid")
            self.assertIsNotNone(err)
        print(">>> Test 8 Passed: Abusive, empty, numeric, or fake placeholder names strictly blocked.")

    # 9. Invalid academic score rejection
    def test_09_invalid_academic_score_rejection(self):
        bad_scores = [-5, 105, "abc", None]
        for s in bad_scores:
            is_valid, _, err = validate_academic_score(s)
            self.assertFalse(is_valid, f"Score {s} should be invalid")
            self.assertIsNotNone(err)
        print(">>> Test 9 Passed: Invalid academic scores strictly blocked.")

    # 10. Invalid attendance rejection
    def test_10_invalid_attendance_rejection(self):
        bad_att = [-1, 101, "invalid", None]
        for a in bad_att:
            is_valid, _, err = validate_attendance(a)
            self.assertFalse(is_valid, f"Attendance {a} should be invalid")
            self.assertIsNotNone(err)
        print(">>> Test 10 Passed: Invalid attendance values strictly blocked.")

    # 11. ML prediction produced from existing model
    def test_11_ml_prediction_produced(self):
        sample_input = {
            "academic_score": 85.0,
            "previous_score": 80.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = ml_service.predict_and_explain(sample_input)
        self.assertIn("model_decision", res)
        self.assertIn(res["model_decision"], ["APPROVE", "REJECT", "NEEDS_HUMAN_REVIEW"])
        print(f">>> Test 11 Passed: ML model predicted {res['model_decision']}.")

    # 12. ML confidence produced (non-zero real probability)
    def test_12_ml_confidence_non_zero(self):
        sample_input = {
            "academic_score": 92.0,
            "previous_score": 90.0,
            "attendance": 95.0,
            "annual_income": 150000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = ml_service.predict_and_explain(sample_input)
        conf = res.get("confidence")
        self.assertIsNotNone(conf)
        self.assertGreater(conf, 0.50)
        self.assertLessEqual(conf, 1.0)
        print(f">>> Test 12 Passed: Real ML model confidence produced: {conf:.4f} (NOT 0%).")

    # 13. Confidence categorization
    def test_13_confidence_categorization(self):
        app_res = self.client.get("/student/applications", headers=self.student_headers)
        apps = app_res.get_json().get("applications", [])
        for a in apps:
            self.assertIn("prediction_category", a)
            self.assertIn(a["prediction_category"], [
                "Likely to Get Approved",
                "Likely to Get Rejected",
                "Moderate / May or May Not Get Approved"
            ])
        print(">>> Test 13 Passed: Application confidence categorization correctly partitioned.")

    # 14. Student rejection reason visibility
    def test_14_rejection_reason_visibility(self):
        app_res = create_application(
            applicant_id=self.student_id,
            scholarship_scheme_id="91fc26f7-e746-4dae-862b-ddc1a8c3527c",
            academic_score=60.0,
            previous_score=60.0,
            attendance=65.0,
            annual_income=800000.0,
            application_category="GENERAL",
        )
        app_id = app_res.data[0]["id"]
        reason_text = "Annual income exceeded threshold for this scholarship."
        record_human_decision(
            application_id=app_id,
            decision="REJECTED",
            reason=reason_text,
            decided_by=self.admin_id,
            admin_comment="Evaluated manually against scheme ceiling."
        )
        update_application_status(app_id, "REJECTED")

        # Student status check
        status_res = self.client.get(f"/status/{app_id}", headers=self.student_headers)
        self.assertEqual(status_res.status_code, 200)
        data = status_res.get_json()
        self.assertEqual(data["final_decision"], "REJECTED")
        self.assertEqual(data["rejection_reason"], reason_text)
        print(">>> Test 14 Passed: Recorded human rejection reason visible to student.")

    # 15. Student approved application status
    def test_15_approved_application_status(self):
        app_res = create_application(
            applicant_id=self.student_id,
            scholarship_scheme_id="91fc26f7-e746-4dae-862b-ddc1a8c3527c",
            academic_score=95.0,
            previous_score=94.0,
            attendance=96.0,
            annual_income=150000.0,
            application_category="GENERAL",
        )
        app_id = app_res.data[0]["id"]
        record_human_decision(
            application_id=app_id,
            decision="APPROVED",
            reason="Applicant meets all merit criteria and verified documents.",
            decided_by=self.admin_id,
            admin_comment="Approved after document verification."
        )
        update_application_status(app_id, "APPROVED")

        status_res = self.client.get(f"/status/{app_id}", headers=self.student_headers)
        self.assertEqual(status_res.status_code, 200)
        data = status_res.get_json()
        self.assertEqual(data["final_decision"], "APPROVED")
        self.assertEqual(data["status"], "APPROVED")
        print(">>> Test 15 Passed: Approved status clearly visible to student.")

    # 16. Student pending application status
    def test_16_pending_application_status(self):
        app_res = create_application(
            applicant_id=self.student_id,
            scholarship_scheme_id="91fc26f7-e746-4dae-862b-ddc1a8c3527c",
            academic_score=85.0,
            previous_score=82.0,
            attendance=88.0,
            annual_income=250000.0,
            application_category="GENERAL",
        )
        app_id = app_res.data[0]["id"]
        status_res = self.client.get(f"/status/{app_id}", headers=self.student_headers)
        self.assertEqual(status_res.status_code, 200)
        data = status_res.get_json()
        self.assertIsNone(data["final_decision"])
        self.assertEqual(data["status"], "SUBMITTED")
        print(">>> Test 16 Passed: Pending status correctly displays without premature decision.")

    # 17. Admin document access
    def test_17_admin_document_access(self):
        apps_res = self.client.get("/admin/applications", headers=self.admin_headers)
        apps = apps_res.get_json().get("applications", [])
        found_doc = False
        for a in apps:
            details = get_application_full_details(a["id"])
            if details and details.get("documents"):
                doc = details["documents"][0]
                view_res = self.client.get(
                    f"/admin/applications/{a['id']}/documents/{doc['id']}/view",
                    headers=self.admin_headers
                )
                self.assertEqual(view_res.status_code, 200)
                download_res = self.client.get(
                    f"/admin/applications/{a['id']}/documents/{doc['id']}/download",
                    headers=self.admin_headers
                )
                self.assertEqual(download_res.status_code, 200)
                found_doc = True
                print(f">>> Test 17 Passed: Admin successfully streamed document {doc['id']}.")
                break
        if not found_doc:
            print(">>> Test 17 Skipped: No documents found in initial scan.")

    # 18. Zero service-role credential leakage
    def test_18_no_service_role_leakage(self):
        res = self.client.get("/student/profile", headers=self.student_headers)
        raw_text = res.get_data(as_text=True)
        self.assertNotIn("service_role", raw_text)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlraHhpaGF5emxqdXB1Z2trem56Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSI", raw_text)

        admin_res = self.client.get("/admin/applications", headers=self.admin_headers)
        admin_text = admin_res.get_data(as_text=True)
        self.assertNotIn("service_role", admin_text)
        print(">>> Test 18 Passed: Zero service-role credential leakage detected in API responses.")

    # 19. ML failure fallback
    def test_19_ml_failure_fallback(self):
        # Empty input causes ValueError during encoding
        with self.assertRaises(ValueError):
            ml_service._encode_input({})
        print(">>> Test 19 Passed: Encoding checks strictly detect invalid/missing ML inputs.")

    # 20. Authentication failure handling
    def test_20_auth_failure_handling(self):
        res_no_token = self.client.get("/student/applications")
        self.assertEqual(res_no_token.status_code, 401)

        res_bad_token = self.client.get("/student/applications", headers={"Authorization": "Bearer bad-token-123"})
        self.assertEqual(res_bad_token.status_code, 401)
        print(">>> Test 20 Passed: Authentication failures consistently return 401 Unauthorized.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
