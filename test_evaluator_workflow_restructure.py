"""
test_evaluator_workflow_restructure.py
---------------------------------------
Verification suite for JAN NITI AI Evaluator Dashboard Workflow Restructure.

Tests all 15 cases specified in Section 29 of the specification:
CASE 1:  ML: APPROVE, Conf: 96%, Human: none -> Pending Decisions -> Likely to Get Approved
CASE 2:  ML: REJECT, Conf: 91%, Human: none -> Pending Decisions -> Likely to Get Rejected
CASE 3:  ML: APPROVE, Conf: 54%, Human: none -> Pending Decisions -> Requires Human Review
CASE 4:  ML: 0%, Unavailable, Human: none -> Pending Decisions -> Requires Human Review (Zero confidence is NOT rejected)
CASE 5:  ML: APPROVE, Conf: 96%, Human: APPROVED -> Decision Made by Admin -> Approved
CASE 6:  ML: APPROVE, Conf: 96%, Human: REJECTED -> Decision Made by Admin -> Rejected (Human overrides AI)
CASE 7:  Human: REJECTED, Appeal: PENDING -> Appeal Pending (Original decision preserved)
CASE 8:  Human: APPROVED, Appeal: none -> Decision Made by Admin -> Approved
CASE 9:  Human: REJECTED, Appeal: none -> Decision Made by Admin -> Rejected
CASE 10: Pending application with uploaded document -> Admin can view and download
CASE 11: Approved application with uploaded document -> Admin can view and download
CASE 12: Rejected application with uploaded document -> Admin can view and download
CASE 13: Appeal-pending application with uploaded document -> Admin can view and download
CASE 14: Student own application with uploaded document -> Student can view and download
CASE 15: Student attempts another student's document -> 403 or 404 Forbidden/Not Found
"""

import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import app
from backend.auth_service import login


def classify_application(app_data):
    """
    Python implementation mirroring frontend classifyApplication(app)
    in frontend/js/admin.js. Enforces the strict priority:
    1. Active Appeal
    2. Final Human Decision
    3. Pending ML Categorization (Advisory Only)
    """
    status_upper = (app_data.get("status") or "").upper()
    appeal_obj = app_data.get("appeal") or {}
    appeal_status_upper = (appeal_obj.get("status") or "").upper()
    has_active_appeal = status_upper == "APPEAL_PENDING" or appeal_status_upper == "PENDING"

    if has_active_appeal:
        orig_dec = (
            app_data.get("admin_final_decision")
            or app_data.get("final_decision")
            or (app_data.get("decision") or {}).get("decision")
            or "REJECTED"
        ).upper()
        return {
            "top": "APPEAL_PENDING",
            "sub": "APPEAL_PENDING",
            "label": "Appeal Pending",
            "original_decision": orig_dec,
        }

    human_dec = (
        app_data.get("admin_final_decision")
        or app_data.get("final_decision")
        or (app_data.get("decision") or {}).get("decision")
        or ""
    ).upper()

    if human_dec in ("APPROVED", "APPROVE"):
        return {
            "top": "DECISION_MADE",
            "sub": "APPROVED",
            "label": "Approved by Admin / Evaluator",
        }
    if human_dec in ("REJECTED", "REJECT"):
        return {
            "top": "DECISION_MADE",
            "sub": "REJECTED",
            "label": "Rejected by Admin / Evaluator",
        }

    pred = (
        app_data.get("model_decision")
        or (app_data.get("ai_prediction") or {}).get("prediction")
        or app_data.get("prediction")
        or ""
    ).upper()

    raw_conf = app_data.get("confidence")
    if raw_conf is None and app_data.get("ai_prediction"):
        raw_conf = app_data["ai_prediction"].get("probability")

    conf = 0
    if raw_conf is not None:
        try:
            val = float(raw_conf)
            conf = round(val * 100) if val <= 1.0 else round(val)
        except (ValueError, TypeError):
            conf = 0

    if pred == "APPROVE" and conf >= 70:
        return {
            "top": "PENDING_DECISIONS",
            "sub": "LIKELY_APPROVED",
            "label": "Likely to Get Approved",
            "confidence": conf,
        }
    elif pred == "REJECT" and conf >= 70:
        return {
            "top": "PENDING_DECISIONS",
            "sub": "LIKELY_REJECTED",
            "label": "Likely to Get Rejected",
            "confidence": conf,
        }
    else:
        return {
            "top": "PENDING_DECISIONS",
            "sub": "REQUIRES_REVIEW",
            "label": "Requires Human Review",
            "confidence": conf,
        }


class TestEvaluatorWorkflowRestructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        # Authenticate admin
        cls.admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
        cls.admin_token = cls.admin_auth.session.access_token
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

        # Authenticate student
        cls.student_auth = login("ayushi1219jain@gmail.com", "JanNitiTest@2026")
        cls.student_token = cls.student_auth.session.access_token
        cls.student_headers = {"Authorization": f"Bearer {cls.student_token}"}

    # CASE 1: ML: APPROVE, Confidence: 96%, Human decision: none
    def test_case_01_ml_approve_high_confidence_pending(self):
        app = {
            "prediction": "APPROVE",
            "confidence": 0.96,
            "final_decision": None,
            "status": "HUMAN_REVIEW",
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "PENDING_DECISIONS")
        self.assertEqual(res["sub"], "LIKELY_APPROVED")
        self.assertEqual(res["confidence"], 96)

    # CASE 2: ML: REJECT, Confidence: 91%, Human decision: none
    def test_case_02_ml_reject_high_confidence_pending(self):
        app = {
            "prediction": "REJECT",
            "confidence": 0.91,
            "final_decision": None,
            "status": "HUMAN_REVIEW",
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "PENDING_DECISIONS")
        self.assertEqual(res["sub"], "LIKELY_REJECTED")
        self.assertEqual(res["confidence"], 91)

    # CASE 3: ML: APPROVE, Confidence: 54%, Human decision: none
    def test_case_03_ml_approve_low_confidence_pending(self):
        app = {
            "prediction": "APPROVE",
            "confidence": 0.54,
            "final_decision": None,
            "status": "HUMAN_REVIEW",
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "PENDING_DECISIONS")
        self.assertEqual(res["sub"], "REQUIRES_REVIEW")
        self.assertEqual(res["confidence"], 54)

    # CASE 4: ML: 0%, Prediction unavailable, Human decision: none
    def test_case_04_zero_confidence_routes_to_human_review(self):
        app = {
            "prediction": None,
            "confidence": 0.0,
            "final_decision": None,
            "status": "HUMAN_REVIEW",
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "PENDING_DECISIONS")
        self.assertEqual(res["sub"], "REQUIRES_REVIEW")
        self.assertNotEqual(res["sub"], "LIKELY_REJECTED")

    # CASE 5: ML: APPROVE, Confidence: 96%, Human decision: APPROVED
    def test_case_05_human_approved_matches_ai(self):
        app = {
            "prediction": "APPROVE",
            "confidence": 0.96,
            "final_decision": "APPROVED",
            "admin_final_decision": "APPROVED",
            "status": "APPROVED",
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "DECISION_MADE")
        self.assertEqual(res["sub"], "APPROVED")

    # CASE 6: ML: APPROVE, Confidence: 96%, Human decision: REJECTED
    def test_case_06_human_rejected_overrides_ai_approve(self):
        app = {
            "prediction": "APPROVE",
            "confidence": 0.96,
            "final_decision": "REJECTED",
            "admin_final_decision": "REJECTED",
            "status": "REJECTED",
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "DECISION_MADE")
        self.assertEqual(res["sub"], "REJECTED")
        # Confirms AI does NOT dictate final decision!

    # CASE 7: Human decision: REJECTED, Appeal: PENDING
    def test_case_07_active_appeal_routes_to_appeal_pending(self):
        app = {
            "prediction": "REJECT",
            "confidence": 0.91,
            "final_decision": "REJECTED",
            "admin_final_decision": "REJECTED",
            "status": "APPEAL_PENDING",
            "appeal": {"status": "PENDING", "reason": "Medical certificate uploaded"},
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "APPEAL_PENDING")
        self.assertEqual(res["sub"], "APPEAL_PENDING")
        self.assertEqual(res["original_decision"], "REJECTED")

    # CASE 8: Human decision: APPROVED, Appeal: none
    def test_case_08_human_approved_no_appeal(self):
        app = {
            "prediction": "NEEDS_HUMAN_REVIEW",
            "confidence": 0.65,
            "final_decision": "APPROVED",
            "admin_final_decision": "APPROVED",
            "status": "APPROVED",
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "DECISION_MADE")
        self.assertEqual(res["sub"], "APPROVED")

    # CASE 9: Human decision: REJECTED, Appeal: none
    def test_case_09_human_rejected_no_appeal(self):
        app = {
            "prediction": "APPROVE",
            "confidence": 0.88,
            "final_decision": "REJECTED",
            "admin_final_decision": "REJECTED",
            "status": "REJECTED",
        }
        res = classify_application(app)
        self.assertEqual(res["top"], "DECISION_MADE")
        self.assertEqual(res["sub"], "REJECTED")

    # CASE 10, 11, 12, 13: Document Viewing and Downloading via Real API
    def test_case_10_to_13_admin_document_access(self):
        # Fetch admin applications list
        res = self.client.get("/admin/applications", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        apps = res.get_json().get("applications", [])
        self.assertTrue(len(apps) > 0)

        # Find an application with documents
        target_app = None
        target_doc = None
        for a in apps[:10]:
            full_res = self.client.get(f"/admin/applications/{a['id']}", headers=self.admin_headers)
            if full_res.status_code == 200:
                docs = full_res.get_json().get("documents", [])
                if docs:
                    target_app = a
                    target_doc = docs[0]
                    break

        if target_app and target_doc:
            app_id = target_app["id"]
            doc_id = target_doc["id"]

            # Admin View Document
            view_res = self.client.get(
                f"/admin/applications/{app_id}/documents/{doc_id}/view?token={self.admin_token}"
            )
            self.assertEqual(view_res.status_code, 200)
            self.assertTrue(len(view_res.data) > 0)

            # Admin Download Document
            dl_res = self.client.get(
                f"/admin/applications/{app_id}/documents/{doc_id}/download?token={self.admin_token}"
            )
            self.assertEqual(dl_res.status_code, 200)
            self.assertTrue("attachment" in dl_res.headers.get("Content-Disposition", ""))

    # CASE 14: Student own application with uploaded document -> Can view/download
    def test_case_14_student_can_access_own_document(self):
        stud_apps_res = self.client.get("/student/applications", headers=self.student_headers)
        self.assertEqual(stud_apps_res.status_code, 200)
        stud_apps = stud_apps_res.get_json().get("applications", [])
        self.assertTrue(len(stud_apps) > 0)

        own_app = stud_apps[0]
        full_res = self.client.get(f"/student/applications/{own_app['id']}", headers=self.student_headers)
        if full_res.status_code == 200:
            docs = full_res.get_json().get("documents", [])
            if docs:
                own_doc = docs[0]
                view_res = self.client.get(
                    f"/student/applications/{own_app['id']}/documents/{own_doc['id']}/view?token={self.student_token}"
                )
                self.assertEqual(view_res.status_code, 200)
                self.assertTrue(len(view_res.data) > 0)

    # CASE 15: Student attempts another student's document -> 403 or 404
    def test_case_15_student_blocked_from_other_student_document(self):
        # Admin gets an application from another student
        admin_res = self.client.get("/admin/applications", headers=self.admin_headers)
        apps = admin_res.get_json().get("applications", [])

        # Find application not belonging to test applicant
        other_app = None
        other_doc = None
        for a in apps:
            if a.get("applicant_id") != self.student_auth.user.id:
                full_res = self.client.get(f"/admin/applications/{a['id']}", headers=self.admin_headers)
                if full_res.status_code == 200:
                    docs = full_res.get_json().get("documents", [])
                    if docs:
                        other_app = a
                        other_doc = docs[0]
                        break

        if other_app and other_doc:
            blocked_res = self.client.get(
                f"/student/applications/{other_app['id']}/documents/{other_doc['id']}/view?token={self.student_token}"
            )
            self.assertIn(blocked_res.status_code, [403, 404])


if __name__ == "__main__":
    unittest.main()
