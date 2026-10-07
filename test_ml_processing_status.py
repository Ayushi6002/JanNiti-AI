"""
test_ml_processing_status.py

Verifies the 8 test cases specified in Part 13 of the specification:
CASE 1: Prediction: APPROVE, Confidence: 96% -> Likely to Get Approved, 96%
CASE 2: Prediction: REJECT, Confidence: 85% -> Likely to Get Rejected, 85%
CASE 3: Prediction: APPROVE, Confidence: 54% -> Requires Human Review
CASE 4: Prediction: REJECT, Confidence: 55% -> Requires Human Review
CASE 5: Prediction: NEEDS_HUMAN_REVIEW, Confidence: 82% -> Requires Human Review
CASE 6: Prediction: null, Confidence: 0 fallback -> ML Processing Pending (NOT Likely to Get Rejected, NOT 0% model confidence)
CASE 7: Prediction: REJECT, Confidence: 96%, Human decision: APPROVED -> Decision Made by Admin -> Approved (NOT Likely to Get Rejected)
CASE 8: Prediction: APPROVE, Confidence: 96%, Human decision: REJECTED -> Decision Made by Admin -> Rejected
"""

import unittest
import re
from pathlib import Path


def js_get_normalized_confidence(app):
    raw_pred = app.get("model_decision") or (app.get("ai_prediction") and app["ai_prediction"].get("prediction")) or app.get("prediction") or ""
    has_pred = bool(app.get("ai_prediction") or (raw_pred and raw_pred not in ("NONE", "")))
    if not has_pred:
        return None

    raw = None
    if isinstance(app.get("confidence"), (int, float)):
        raw = app["confidence"]
    elif app.get("ai_prediction") and isinstance(app["ai_prediction"].get("probability"), (int, float)):
        raw = app["ai_prediction"]["probability"]

    if raw is None:
        return None
    if raw <= 1.0:
        return round(raw * 100)
    return round(raw)


def js_format_confidence(app):
    conf = js_get_normalized_confidence(app)
    if conf is None:
        return "Not Available — ML Processing Pending"
    return f"{conf}%"


def js_classify_application(app):
    # 1. Active Appeal
    status_upper = (app.get("status") or "").upper()
    appeal = app.get("appeal") or {}
    appeal_status_upper = (appeal.get("status") or "").upper()
    has_active_appeal = status_upper == "APPEAL_PENDING" or appeal_status_upper == "PENDING"

    if has_active_appeal:
        orig_dec = (app.get("admin_final_decision") or app.get("final_decision") or (app.get("decision") and app["decision"].get("decision")) or "REJECTED").upper()
        return {
            "top": "APPEAL_PENDING",
            "sub": "APPEAL_PENDING",
            "parentSub": "APPEAL_PENDING",
            "reviewSub": None,
            "label": "Appeal Pending",
            "originalDecision": orig_dec,
            "isAppeal": True,
            "confidence": js_get_normalized_confidence(app),
        }

    # 2. Final Human Decision
    human_dec = (app.get("admin_final_decision") or app.get("final_decision") or (app.get("decision") and app["decision"].get("decision")) or "").upper()
    if human_dec in ("APPROVED", "APPROVE"):
        return {
            "top": "DECISION_MADE",
            "sub": "APPROVED",
            "parentSub": "APPROVED",
            "reviewSub": None,
            "label": "Approved by Admin / Evaluator",
            "humanDecision": "APPROVED",
            "confidence": js_get_normalized_confidence(app),
        }
    if human_dec in ("REJECTED", "REJECT"):
        return {
            "top": "DECISION_MADE",
            "sub": "REJECTED",
            "parentSub": "REJECTED",
            "reviewSub": None,
            "label": "Rejected by Admin / Evaluator",
            "humanDecision": "REJECTED",
            "confidence": js_get_normalized_confidence(app),
        }

    # 3. Pending ML Categorization
    raw_pred = app.get("model_decision") or (app.get("ai_prediction") and app["ai_prediction"].get("prediction")) or app.get("prediction") or ""
    pred = raw_pred.upper() if raw_pred else ""
    has_prediction_record = bool(app.get("ai_prediction") or (raw_pred and raw_pred not in ("NONE", "")))
    conf = js_get_normalized_confidence(app)

    if not has_prediction_record or not pred:
        return {
            "top": "PENDING_DECISIONS",
            "sub": "ML_PROCESSING_PENDING",
            "parentSub": "REQUIRES_REVIEW",
            "reviewSub": "ML_PROCESSING_PENDING",
            "label": "ML Processing Pending",
            "confidence": None,
            "isMLPending": True,
        }

    if pred == "APPROVE" and conf is not None and conf >= 70:
        return {
            "top": "PENDING_DECISIONS",
            "sub": "LIKELY_APPROVED",
            "parentSub": "LIKELY_APPROVED",
            "reviewSub": None,
            "label": "Likely to Get Approved",
            "confidence": conf,
        }

    if pred == "REJECT" and conf is not None and conf >= 70:
        return {
            "top": "PENDING_DECISIONS",
            "sub": "LIKELY_REJECTED",
            "parentSub": "LIKELY_REJECTED",
            "reviewSub": None,
            "label": "Likely to Get Rejected",
            "confidence": conf,
        }

    return {
        "top": "PENDING_DECISIONS",
        "sub": "REQUIRES_REVIEW",
        "parentSub": "REQUIRES_REVIEW",
        "reviewSub": "MODEL_REVIEW_REQUIRED",
        "label": "Requires Human Review (Model Review Required)",
        "confidence": conf,
        "isModelReview": True,
    }


class TestMLProcessingStatus(unittest.TestCase):
    def test_case_1_likely_approved(self):
        """CASE 1: Prediction: APPROVE, Confidence: 96% -> Likely to Get Approved, 96%"""
        app = {
            "id": "c1",
            "prediction": "APPROVE",
            "confidence": 0.96,
            "ai_prediction": {"prediction": "APPROVE", "probability": 0.96},
        }
        c = js_classify_application(app)
        self.assertEqual(c["top"], "PENDING_DECISIONS")
        self.assertEqual(c["sub"], "LIKELY_APPROVED")
        self.assertEqual(c["confidence"], 96)
        self.assertEqual(js_format_confidence(app), "96%")

    def test_case_2_likely_rejected(self):
        """CASE 2: Prediction: REJECT, Confidence: 85% -> Likely to Get Rejected, 85%"""
        app = {
            "id": "c2",
            "prediction": "REJECT",
            "confidence": 0.85,
            "ai_prediction": {"prediction": "REJECT", "probability": 0.85},
        }
        c = js_classify_application(app)
        self.assertEqual(c["top"], "PENDING_DECISIONS")
        self.assertEqual(c["sub"], "LIKELY_REJECTED")
        self.assertEqual(c["confidence"], 85)
        self.assertEqual(js_format_confidence(app), "85%")

    def test_case_3_approve_low_confidence(self):
        """CASE 3: Prediction: APPROVE, Confidence: 54% -> Requires Human Review"""
        app = {
            "id": "c3",
            "prediction": "APPROVE",
            "confidence": 0.54,
            "ai_prediction": {"prediction": "APPROVE", "probability": 0.54},
        }
        c = js_classify_application(app)
        self.assertEqual(c["top"], "PENDING_DECISIONS")
        self.assertEqual(c["parentSub"], "REQUIRES_REVIEW")
        self.assertEqual(c["reviewSub"], "MODEL_REVIEW_REQUIRED")
        self.assertEqual(c["confidence"], 54)
        self.assertEqual(js_format_confidence(app), "54%")

    def test_case_4_reject_low_confidence(self):
        """CASE 4: Prediction: REJECT, Confidence: 55% -> Requires Human Review"""
        app = {
            "id": "c4",
            "prediction": "REJECT",
            "confidence": 0.55,
            "ai_prediction": {"prediction": "REJECT", "probability": 0.55},
        }
        c = js_classify_application(app)
        self.assertEqual(c["top"], "PENDING_DECISIONS")
        self.assertEqual(c["parentSub"], "REQUIRES_REVIEW")
        self.assertEqual(c["reviewSub"], "MODEL_REVIEW_REQUIRED")
        self.assertEqual(c["confidence"], 55)
        self.assertEqual(js_format_confidence(app), "55%")

    def test_case_5_needs_human_review_prediction(self):
        """CASE 5: Prediction: NEEDS_HUMAN_REVIEW, Confidence: 82% -> Requires Human Review"""
        app = {
            "id": "c5",
            "prediction": "NEEDS_HUMAN_REVIEW",
            "confidence": 0.82,
            "ai_prediction": {"prediction": "NEEDS_HUMAN_REVIEW", "probability": 0.82},
        }
        c = js_classify_application(app)
        self.assertEqual(c["top"], "PENDING_DECISIONS")
        self.assertEqual(c["parentSub"], "REQUIRES_REVIEW")
        self.assertEqual(c["reviewSub"], "MODEL_REVIEW_REQUIRED")
        self.assertEqual(c["confidence"], 82)

    def test_case_6_null_prediction_fallback_zero(self):
        """
        CASE 6: Prediction: null, Confidence: 0 fallback
        Expected: ML Processing Pending (NOT Likely to Get Rejected, NOT 0% model confidence)
        """
        app = {
            "id": "c6",
            "prediction": None,
            "model_decision": None,
            "confidence": 0.0,
            "ai_prediction": None,
        }
        c = js_classify_application(app)
        self.assertEqual(c["top"], "PENDING_DECISIONS")
        self.assertEqual(c["parentSub"], "REQUIRES_REVIEW")
        self.assertEqual(c["sub"], "ML_PROCESSING_PENDING")
        self.assertEqual(c["reviewSub"], "ML_PROCESSING_PENDING")
        self.assertTrue(c.get("isMLPending"))
        self.assertIsNone(c["confidence"])
        self.assertNotEqual(c["sub"], "LIKELY_REJECTED")
        formatted = js_format_confidence(app)
        self.assertNotEqual(formatted, "0%")
        self.assertIn("ML Processing Pending", formatted)

    def test_case_7_reject_overridden_by_human_approved(self):
        """
        CASE 7: Prediction: REJECT, Confidence: 96%, Human decision: APPROVED
        Expected: Decision Made by Admin -> Approved (NOT Likely to Get Rejected)
        """
        app = {
            "id": "c7",
            "prediction": "REJECT",
            "confidence": 0.96,
            "admin_final_decision": "APPROVED",
            "final_decision": "APPROVED",
            "ai_prediction": {"prediction": "REJECT", "probability": 0.96},
        }
        c = js_classify_application(app)
        self.assertEqual(c["top"], "DECISION_MADE")
        self.assertEqual(c["sub"], "APPROVED")
        self.assertNotEqual(c["top"], "PENDING_DECISIONS")
        self.assertNotEqual(c["sub"], "LIKELY_REJECTED")

    def test_case_8_approve_overridden_by_human_rejected(self):
        """
        CASE 8: Prediction: APPROVE, Confidence: 96%, Human decision: REJECTED
        Expected: Decision Made by Admin -> Rejected
        """
        app = {
            "id": "c8",
            "prediction": "APPROVE",
            "confidence": 0.96,
            "admin_final_decision": "REJECTED",
            "final_decision": "REJECTED",
            "ai_prediction": {"prediction": "APPROVE", "probability": 0.96},
        }
        c = js_classify_application(app)
        self.assertEqual(c["top"], "DECISION_MADE")
        self.assertEqual(c["sub"], "REJECTED")
        self.assertNotEqual(c["top"], "PENDING_DECISIONS")
        self.assertNotEqual(c["sub"], "LIKELY_APPROVED")

    def test_homepage_nav_does_not_contain_track_status(self):
        """Verify frontend/index.html site-nav does not contain Track Status"""
        index_path = Path(__file__).resolve().parent / "frontend" / "index.html"
        content = index_path.read_text(encoding="utf-8")
        nav_match = re.search(r'<nav class="site-nav">([\s\S]*?)</nav>', content)
        self.assertIsNotNone(nav_match, "Could not find site-nav in index.html")
        nav_html = nav_match.group(1)
        self.assertNotIn("Track Status", nav_html)
        self.assertIn("Home", nav_html)
        self.assertIn("Apply", nav_html)
        self.assertIn("Student Login", nav_html)
        self.assertIn("Evaluator Login", nav_html)


if __name__ == "__main__":
    unittest.main()
