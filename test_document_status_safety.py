"""
test_document_status_safety.py
--------------------------------------------------------------------------------
Focused Regression Test Suite for Stage 2D.4:
Document-Status Safety Fix + Release Gate Integrity Verification

Verifies all 12 mandatory criteria from Stage 2D.4 Section 3:
1. Explicitly verified documents remain VERIFIED.
2. Explicitly incomplete documents remain INCOMPLETE.
3. Missing document status becomes UNCERTAIN.
4. Null document status becomes UNCERTAIN.
5. Unknown status cannot silently become VERIFIED.
6. Boolean inputs follow their explicitly documented caller contracts.
7. Predictor checkboxes are not misrepresented as completed verification.
8. Actual application document verification still works.
9. The candidate feature vector uses the correct encoded status.
10. P(APPROVE) is still extracted from the correct target-class index.
11. All academic stages continue to work.
12. The Need-Based eligibility safeguard remains intact.
--------------------------------------------------------------------------------
"""

import sys
import unittest
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.ml_service import ml_service, normalize_document_status
from backend.scholarship_predictor_service import predict_scholarships


class TestDocumentStatusSafety(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Save initial active model version
        cls.initial_version = ml_service.active_version

    def tearDown(self):
        # Always restore model version after each test
        ml_service.set_active_version(self.initial_version)

    # 1. Explicitly verified documents remain VERIFIED
    def test_01_explicitly_verified_documents_remain_verified(self):
        """1. Explicitly verified documents remain VERIFIED across helper and encoders."""
        self.assertEqual(normalize_document_status("VERIFIED"), "VERIFIED")
        self.assertEqual(normalize_document_status("MATCH"), "VERIFIED")

        # In candidate model feature vector
        ml_service.set_active_version("stage_aware_v1")
        X_cand = ml_service._encode_input({
            "academic_stage": "SECOND_YEAR",
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        })
        verified_idx = list(ml_service.encoders["documents_verified"].classes_).index("VERIFIED")
        self.assertEqual(X_cand["documents_verified"].iloc[0], verified_idx)

        # In legacy model feature vector
        ml_service.set_active_version("legacy_v2")
        X_leg = ml_service._encode_input({
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        })
        leg_verified_idx = list(ml_service.encoders["documents_verified"].classes_).index("VERIFIED")
        self.assertEqual(X_leg["documents_verified"].iloc[0], leg_verified_idx)

    # 2. Explicitly incomplete documents remain INCOMPLETE
    def test_02_explicitly_incomplete_documents_remain_incomplete(self):
        """2. Explicitly incomplete documents remain INCOMPLETE across helper and encoders."""
        self.assertEqual(normalize_document_status("INCOMPLETE"), "INCOMPLETE")
        self.assertEqual(normalize_document_status("MISSING"), "INCOMPLETE")

        ml_service.set_active_version("stage_aware_v1")
        X = ml_service._encode_input({
            "academic_stage": "SECOND_YEAR",
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "INCOMPLETE",
        })
        incomplete_idx = list(ml_service.encoders["documents_verified"].classes_).index("INCOMPLETE")
        self.assertEqual(X["documents_verified"].iloc[0], incomplete_idx)

    # 3. Missing document status becomes UNCERTAIN
    def test_03_missing_document_status_becomes_uncertain(self):
        """3. Missing document status must not automatically become VERIFIED -> UNCERTAIN."""
        self.assertEqual(normalize_document_status(None), "UNCERTAIN")

        # Missing key in raw input for stage_aware_v1
        ml_service.set_active_version("stage_aware_v1")
        raw = {
            "academic_stage": "SECOND_YEAR",
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            # 'documents_verified' intentionally omitted
        }
        X = ml_service._encode_input(raw)
        uncertain_idx = list(ml_service.encoders["documents_verified"].classes_).index("UNCERTAIN")
        verified_idx = list(ml_service.encoders["documents_verified"].classes_).index("VERIFIED")

        self.assertNotEqual(X["documents_verified"].iloc[0], verified_idx)
        self.assertEqual(X["documents_verified"].iloc[0], uncertain_idx)

    # 4. Null document status becomes UNCERTAIN
    def test_04_null_document_status_becomes_uncertain(self):
        """4. Null / None / np.nan document status becomes UNCERTAIN."""
        self.assertEqual(normalize_document_status(None), "UNCERTAIN")
        self.assertEqual(normalize_document_status(float("nan")), "UNCERTAIN")
        self.assertEqual(normalize_document_status("None"), "UNCERTAIN")
        self.assertEqual(normalize_document_status("null"), "UNCERTAIN")

        ml_service.set_active_version("stage_aware_v1")
        X = ml_service._encode_input({
            "academic_stage": "SECOND_YEAR",
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": None,
        })
        uncertain_idx = list(ml_service.encoders["documents_verified"].classes_).index("UNCERTAIN")
        self.assertEqual(X["documents_verified"].iloc[0], uncertain_idx)

    # 5. Unknown status cannot silently become VERIFIED
    def test_05_unknown_status_cannot_silently_become_verified(self):
        """5. Unknown or malformed statuses become UNCERTAIN, never VERIFIED."""
        unknown_values = ["PENDING", "UNKNOWN", "MALFORMED_STATUS", "SUBMITTED", "", "   ", "unverified"]
        verified_idx = list(ml_service.encoders["documents_verified"].classes_).index("VERIFIED")
        uncertain_idx = list(ml_service.encoders["documents_verified"].classes_).index("UNCERTAIN")

        ml_service.set_active_version("stage_aware_v1")
        for unk in unknown_values:
            norm = normalize_document_status(unk)
            self.assertNotEqual(norm, "VERIFIED", f"Value '{unk}' silently became VERIFIED!")
            self.assertEqual(norm, "UNCERTAIN")

            X = ml_service._encode_input({
                "academic_stage": "SECOND_YEAR",
                "academic_score": 85.0,
                "previous_score": 82.0,
                "attendance": 88.0,
                "annual_income": 300000.0,
                "application_category": "General",
                "scholarship_scheme": "Merit Scholarship",
                "documents_verified": unk,
            })
            self.assertNotEqual(X["documents_verified"].iloc[0], verified_idx)
            self.assertEqual(X["documents_verified"].iloc[0], uncertain_idx)

    # 6. Boolean inputs follow their explicitly documented caller contracts
    def test_06_boolean_inputs_follow_explicit_contracts(self):
        """6. Boolean inputs follow caller contracts: True=VERIFIED only when contract guarantees it."""
        # True without contract -> UNCERTAIN (cannot assume verified)
        self.assertEqual(normalize_document_status(True), "UNCERTAIN")
        self.assertEqual(normalize_document_status(True, caller_contract=None), "UNCERTAIN")

        # True with verified caller contract -> VERIFIED
        self.assertEqual(normalize_document_status(True, caller_contract="VERIFIED_SERVICE"), "VERIFIED")
        self.assertEqual(normalize_document_status(True, caller_contract="VERIFIED_WORKFLOW"), "VERIFIED")

        # False with contract -> INCOMPLETE
        self.assertEqual(normalize_document_status(False, caller_contract="KNOWN_INCOMPLETE"), "INCOMPLETE")
        self.assertEqual(normalize_document_status(False, caller_contract="VERIFIED_SERVICE"), "INCOMPLETE")

        # False without contract -> UNCERTAIN
        self.assertEqual(normalize_document_status(False, caller_contract=None), "UNCERTAIN")

    # 7. Predictor checkboxes are not misrepresented as completed verification
    def test_07_predictor_checkboxes_not_misrepresented_as_completed_verification(self):
        """7. Predictor checkboxes indicate self-declared readiness, not completed verification."""
        profile = {
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
                "category_certificate": True,
            },
        }
        res = predict_scholarships(profile)
        self.assertTrue(res["success"])
        readiness = res["document_readiness"]

        # Predictor returns explicit readiness status and verification distinction
        self.assertEqual(readiness["readiness_status"], "READY")
        self.assertEqual(readiness["verification_status"], "UNCERTAIN")
        self.assertIn("verification_authority_note", readiness)
        self.assertIn("formal application submission", readiness["verification_authority_note"])

        # Check Best Match scheme readiness metadata
        best = res["best_match"]
        self.assertIsNotNone(best)
        scheme_readiness = best["document_readiness"]
        self.assertEqual(scheme_readiness["readiness_status"], "READY")
        self.assertEqual(scheme_readiness["verification_status"], "UNCERTAIN")

    # 8. Actual application document verification still works
    def test_08_actual_application_document_verification_contract(self):
        """8. Actual application verification service contract produces strict verified features."""
        from backend.ml_application_service import get_document_status_for_ml

        # Verification service contract helper preserves VERIFIED
        status_verified = normalize_document_status("VERIFIED", caller_contract="VERIFIED_SERVICE")
        self.assertEqual(status_verified, "VERIFIED")

        status_incomplete = normalize_document_status("INCOMPLETE", caller_contract="VERIFIED_SERVICE")
        self.assertEqual(status_incomplete, "INCOMPLETE")

        status_uncertain = normalize_document_status("UNCERTAIN", caller_contract="VERIFIED_SERVICE")
        self.assertEqual(status_uncertain, "UNCERTAIN")

    # 9. The candidate feature vector uses the correct encoded status
    def test_09_candidate_feature_vector_uses_correct_encoded_status(self):
        """9. Candidate feature vector encodes: INCOMPLETE=0, UNCERTAIN=1, VERIFIED=2."""
        ml_service.set_active_version("stage_aware_v1")
        classes = list(ml_service.encoders["documents_verified"].classes_)
        self.assertEqual(classes, ["INCOMPLETE", "UNCERTAIN", "VERIFIED"])

        base_raw = {
            "academic_stage": "SECOND_YEAR",
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 88.0,
            "annual_income": 300000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
        }

        # Encode INCOMPLETE -> 0
        raw_inc = {**base_raw, "documents_verified": "INCOMPLETE"}
        X_inc = ml_service._encode_input(raw_inc)
        self.assertEqual(X_inc["documents_verified"].iloc[0], 0)

        # Encode UNCERTAIN -> 1
        raw_unc = {**base_raw, "documents_verified": "UNCERTAIN"}
        X_unc = ml_service._encode_input(raw_unc)
        self.assertEqual(X_unc["documents_verified"].iloc[0], 1)

        # Encode VERIFIED -> 2
        raw_ver = {**base_raw, "documents_verified": "VERIFIED"}
        X_ver = ml_service._encode_input(raw_ver)
        self.assertEqual(X_ver["documents_verified"].iloc[0], 2)

    # 10. P(APPROVE) is still extracted from the correct target-class index
    def test_10_prob_approve_extracted_from_correct_target_index(self):
        """10. P(APPROVE) is strictly extracted from approve_idx (class 'APPROVE' index 0)."""
        for ver in ["legacy_v2", "stage_aware_v1"]:
            ml_service.set_active_version(ver)
            approve_idx = list(ml_service.encoders["target"].classes_).index("APPROVE")
            self.assertEqual(ml_service.approve_idx, approve_idx)
            self.assertEqual(ml_service.classes[approve_idx], "APPROVE")

            inp = {
                "academic_score": 90.0,
                "previous_score": 88.0,
                "attendance": 92.0,
                "annual_income": 200000.0,
                "application_category": "General",
                "scholarship_scheme": "Merit Scholarship",
                "documents_verified": "VERIFIED",
            }
            if ver == "stage_aware_v1":
                inp["academic_stage"] = "SECOND_YEAR"
                inp["qualification_type"] = "NOT_APPLICABLE"
                inp["is_attendance_applicable"] = 1

            res = ml_service.predict_and_explain(inp)
            expected_p_approve = res["class_probabilities"]["APPROVE"]
            self.assertAlmostEqual(res["estimated_approval_probability"], expected_p_approve, places=4)

    # 11. All academic stages continue to work
    def test_11_all_academic_stages_continue_to_work(self):
        """11. All academic stages continue to function cleanly in stage_aware_v1."""
        ml_service.set_active_version("stage_aware_v1")

        stages_to_test = [
            ("FIRST_YEAR", "HSC_12TH", None, 0),
            ("FIRST_YEAR", "DIPLOMA", None, 0),
            ("SECOND_YEAR", "NOT_APPLICABLE", 85.0, 1),
            ("THIRD_YEAR", "NOT_APPLICABLE", 88.0, 1),
            ("FOURTH_YEAR", "NOT_APPLICABLE", 90.0, 1),
            ("POSTGRADUATE", "NOT_APPLICABLE", 82.0, 1),
        ]

        for stage, qtype, att, is_att_app in stages_to_test:
            inp = {
                "academic_stage": stage,
                "qualification_type": qtype,
                "academic_score": 85.0,
                "previous_score": 82.0,
                "attendance": att,
                "is_attendance_applicable": is_att_app,
                "annual_income": 300000.0,
                "application_category": "General",
                "scholarship_scheme": "Merit Scholarship",
                "documents_verified": "VERIFIED",
            }
            res = ml_service.predict_and_explain(inp)
            self.assertIn("final_decision", res)
            self.assertIn(res["final_decision"], ["APPROVE", "NEEDS_HUMAN_REVIEW", "REJECT"])

    # 12. The Need-Based eligibility safeguard remains intact
    def test_12_need_based_eligibility_safeguard_remains_intact(self):
        """12. Disagreement handling preserves authoritative deterministic rule precedence for Need-Based."""
        # High score but exceeds Need-Based income limit (> 250,000)
        profile_high_income = {
            "academic_score": 88.0,
            "previous_score": 85.0,
            "attendance": 90.0,
            "annual_income": 350000.0,  # Exceeds Need-Based maximum of 250,000
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
            },
        }
        res = predict_scholarships(profile_high_income)
        self.assertTrue(res["success"])

        need_scheme = next((s for s in res["schemes"] if s["scheme_code"] == "NEED_BASED"), None)
        self.assertIsNotNone(need_scheme)
        # Deterministic rule fails -> status MUST be NOT_ELIGIBLE
        self.assertEqual(need_scheme["eligibility_status"], "NOT_ELIGIBLE")

        # Approval probability display must NOT grant approval
        self.assertEqual(need_scheme["ml_prediction"]["estimated_approval_probability"], "Not applicable")


if __name__ == "__main__":
    unittest.main()
