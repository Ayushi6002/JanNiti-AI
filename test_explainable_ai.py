"""
test_explainable_ai.py
-----------------------
Unit and integration test suite for Phase 1C: Interactive SHAP Explainability.

Verifies:
1. SHAP explanation successfully generated
2. Correct feature count (exactly 7 features)
3. Correct feature names
4. SHAP values are numeric floats
5. Feature ranking uses absolute SHAP magnitude (strictly descending)
6. Positive contribution classification works
7. Negative contribution classification works
8. Zero/negligible contribution classification works
9. Input values match prediction input
10. SHAP uses same feature preprocessing as ML prediction
11. Predicted class is correctly identified
12. Confidence remains 0.0 - 1.0 (never > 1.0)
13. SHAP values are not treated as percentages
14. Predictor remains public (unauthenticated access permitted)
15. Predictor remains read-only
16. Zero application mutations
17. Zero decision mutations
18. Zero scholarship-rule mutations
19. Additivity property: Base Value + sum(SHAP) == Predicted Probability
20. Graceful fallback on malformed input
21. Multi-scheme prediction contains SHAP explanation
22. Distinct rule-based eligibility vs ML SHAP explanation
23. High-income negative impact profile
24. Low-academic negative impact profile
25. Endpoint /scholarship/explain returns 200 with valid structure
"""

import math
import unittest
from typing import Any, Dict

from backend.app import app
from backend.explainable_ai_service import (
    generate_shap_explanation,
    _normalize_input_for_ml,
    _classify_direction,
    _classify_impact,
    FEATURE_DISPLAY_NAMES,
)
from backend.ml_service import ml_service
from backend.scholarship_predictor_service import predict_scholarships
from backend.supabase_client import supabase


class TestExplainableAIService(unittest.TestCase):
    """Unit tests for explainable_ai_service core functions."""

    def setUp(self):
        self.sample_profile = {
            "academic_score": 85.0,
            "previous_score": 82.0,
            "attendance": 90.0,
            "annual_income": 150000.0,
            "application_category": "OBC",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }

    def test_01_shap_explanation_successfully_generated(self):
        """Test that generate_shap_explanation returns a success response with full structure."""
        res = generate_shap_explanation(self.sample_profile)
        self.assertEqual(res.get("status"), "success")
        self.assertIn("prediction", res)
        self.assertIn("explanation", res)
        self.assertIsInstance(res["explanation"], dict)

    def test_02_correct_feature_count(self):
        """Test that explanation contains exactly 7 features."""
        res = generate_shap_explanation(self.sample_profile)
        features = res["explanation"]["features"]
        self.assertEqual(len(features), 7)

    def test_03_correct_feature_names(self):
        """Test that all 7 expected feature columns exist in the explanation."""
        res = generate_shap_explanation(self.sample_profile)
        features = res["explanation"]["features"]
        feature_keys = {f["feature"] for f in features}
        expected_keys = {
            "academic_score",
            "previous_score",
            "attendance",
            "annual_income",
            "application_category",
            "scholarship_scheme",
            "documents_verified",
        }
        self.assertEqual(feature_keys, expected_keys)

    def test_04_shap_values_are_numeric(self):
        """Test that all SHAP values and base value are valid numeric floats (not NaN or Inf)."""
        res = generate_shap_explanation(self.sample_profile)
        base_val = res["explanation"]["base_value"]
        self.assertIsInstance(base_val, float)
        self.assertFalse(math.isnan(base_val))

        for f in res["explanation"]["features"]:
            val = f["shap_value"]
            self.assertIsInstance(val, float)
            self.assertFalse(math.isnan(val))

    def test_05_feature_ranking_uses_absolute_shap_magnitude(self):
        """Test that features are strictly ranked by abs(shap_value) in descending order."""
        res = generate_shap_explanation(self.sample_profile)
        features = res["explanation"]["features"]
        magnitudes = [abs(f["shap_value"]) for f in features]
        # Check sorted descending
        for i in range(len(magnitudes) - 1):
            self.assertGreaterEqual(
                magnitudes[i],
                magnitudes[i + 1] - 1e-9,
                f"Feature ranking out of order at index {i}: {magnitudes[i]} < {magnitudes[i+1]}"
            )

    def test_06_positive_contribution_classification_works(self):
        """Test that direction classification correctly tags positive influences."""
        self.assertEqual(_classify_direction(0.12), "positive")
        self.assertEqual(_classify_direction(0.006), "positive")

    def test_07_negative_contribution_classification_works(self):
        """Test that direction classification correctly tags negative influences."""
        self.assertEqual(_classify_direction(-0.08), "negative")
        self.assertEqual(_classify_direction(-0.006), "negative")

    def test_08_neutral_contribution_classification_works(self):
        """Test that direction classification correctly tags negligible influences."""
        self.assertEqual(_classify_direction(0.001), "neutral")
        self.assertEqual(_classify_direction(-0.002), "neutral")
        self.assertEqual(_classify_direction(0.0), "neutral")

    def test_09_input_values_match_prediction_input(self):
        """Test that returned feature inputs accurately reflect the provided profile values."""
        res = generate_shap_explanation(self.sample_profile)
        features_by_name = {f["feature"]: f for f in res["explanation"]["features"]}

        self.assertEqual(features_by_name["academic_score"]["input_value"], 85.0)
        self.assertEqual(features_by_name["previous_score"]["input_value"], 82.0)
        self.assertEqual(features_by_name["attendance"]["input_value"], 90.0)
        self.assertEqual(features_by_name["annual_income"]["input_value"], 150000.0)

    def test_10_shap_uses_same_feature_preprocessing_as_ml(self):
        """Test that SHAP input encoding matches ml_service._encode_input exactly."""
        normalized = _normalize_input_for_ml(self.sample_profile)
        X = ml_service._encode_input(normalized)
        self.assertEqual(X.shape, (1, 7))
        self.assertEqual(list(X.columns), ml_service.feature_cols)

    def test_11_predicted_class_is_correctly_identified(self):
        """Test that predicted class matches ML model's direct prediction."""
        res = generate_shap_explanation(self.sample_profile)
        normalized = _normalize_input_for_ml(self.sample_profile)
        X = ml_service._encode_input(normalized)
        direct_pred_encoded = ml_service.model.predict(X)[0]
        expected_class = list(ml_service.encoders["target"].classes_)[direct_pred_encoded]

        self.assertEqual(res["prediction"]["class"], expected_class)
        self.assertEqual(res["explanation"]["output_class"], expected_class)

    def test_12_confidence_remains_zero_to_one(self):
        """Test that raw confidence probability is strictly bounded in [0.0, 1.0]."""
        res = generate_shap_explanation(self.sample_profile)
        conf = res["prediction"]["confidence"]
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)
        self.assertLessEqual(conf, 1.0, "Confidence must not exceed 1.0 (no 7260% bug)")

    def test_13_shap_values_not_treated_as_percentages(self):
        """Test that SHAP values are not displayed with percentage signs."""
        res = generate_shap_explanation(self.sample_profile)
        for f in res["explanation"]["features"]:
            shap_disp = f["shap_display"]
            self.assertFalse(shap_disp.endswith("%"), f"SHAP display must not be a percentage: {shap_disp}")

    def test_19_treeshap_additivity_property(self):
        """Test TreeSHAP additivity: Base Value + sum(SHAP values) == Predicted Probability."""
        res = generate_shap_explanation(self.sample_profile)
        base_val = res["explanation"]["base_value"]
        shap_sum = sum(f["shap_value"] for f in res["explanation"]["features"])
        calculated_prob = base_val + shap_sum

        # Verify against actual model probability
        normalized = _normalize_input_for_ml(self.sample_profile)
        X = ml_service._encode_input(normalized)
        proba = ml_service.model.predict_proba(X)[0]
        classes = list(ml_service.encoders["target"].classes_)
        target_idx = classes.index(res["prediction"]["class"])
        actual_prob = float(proba[target_idx])

        self.assertAlmostEqual(
            calculated_prob,
            actual_prob,
            places=2,
            msg=f"Additivity violated: base({base_val}) + sum({shap_sum}) = {calculated_prob} vs {actual_prob}"
        )

    def test_20_graceful_fallback_on_empty_input(self):
        """Test that unexpected or completely missing input yields graceful response without unhandled crash."""
        res = generate_shap_explanation({})
        # Should either successfully explain fallback default or return unavailable
        self.assertIn(res.get("status"), ("success", "unavailable"))
        if res.get("status") == "unavailable":
            self.assertIn("error", res)

    def test_23_high_income_profile_shows_negative_impact(self):
        """Test that very high family income exerts downward pressure for Need-Based scholarship."""
        high_income_profile = {
            "academic_score": 75.0,
            "previous_score": 75.0,
            "attendance": 85.0,
            "annual_income": 950000.0,
            "application_category": "General",
            "scholarship_scheme": "Need-Based Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = generate_shap_explanation(high_income_profile, class_override="APPROVE")
        features_by_name = {f["feature"]: f for f in res["explanation"]["features"]}
        income_feat = features_by_name["annual_income"]
        # Income for need-based should have negative or zero influence on APPROVE
        self.assertIn(income_feat["direction"], ("negative", "neutral"))

    def test_24_low_academic_profile_explanation(self):
        """Test low academic score features for Merit scholarship."""
        low_acad_profile = {
            "academic_score": 45.0,
            "previous_score": 42.0,
            "attendance": 55.0,
            "annual_income": 200000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        res = generate_shap_explanation(low_acad_profile, class_override="APPROVE")
        features_by_name = {f["feature"]: f for f in res["explanation"]["features"]}
        acad_feat = features_by_name["academic_score"]
        self.assertIn(acad_feat["direction"], ("negative", "neutral"))


class TestPredictorWithSHAPIntegration(unittest.TestCase):
    """Integration tests verifying SHAP is embedded in predict_scholarships."""

    def setUp(self):
        self.valid_input = {
            "academic_score": 88.0,
            "previous_score": 85.0,
            "attendance": 92.0,
            "annual_income": 120000.0,
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
            },
        }

    def test_21_predict_scholarships_embeds_shap_explanation(self):
        """Test that predict_scholarships includes shap_explanation in response."""
        res = predict_scholarships(self.valid_input)
        self.assertTrue(res.get("success"))

        # Best match should contain SHAP explanation in its ml_prediction
        best_match = res.get("best_match")
        self.assertIsNotNone(best_match)
        self.assertIn("ml_prediction", best_match)
        ml_pred = best_match["ml_prediction"]
        self.assertIn("shap_explanation", ml_pred)
        self.assertEqual(ml_pred["shap_explanation"].get("status"), "success")

        # Top level response should also have shap_explanation
        self.assertIn("shap_explanation", res)

    def test_22_distinction_between_rule_eligibility_and_shap(self):
        """Test that rule-based criteria and ML SHAP explanations are clearly separate concepts."""
        # Profile failing income rule for Need-Based, but ML may still classify based on high marks
        borderline_input = {
            "academic_score": 92.0,
            "previous_score": 90.0,
            "attendance": 95.0,
            "annual_income": 800000.0,  # Fails income ceiling
            "application_category": "GENERAL",
            "documents": {
                "marksheet": True,
                "income_certificate": True,
                "id_proof": True,
            },
        }
        res = predict_scholarships(borderline_input)
        # Find Need-Based scheme
        need_scheme = next((s for s in res.get("schemes", []) if "NEED" in s.get("scheme_code", "")), None)
        if need_scheme:
            # Rule eligibility must be NOT_ELIGIBLE because income failed
            self.assertEqual(need_scheme["eligibility_status"], "NOT_ELIGIBLE")
            # ML prediction may be APPROVE, and SHAP explains ML, not the rule
            shap_exp = need_scheme["ml_prediction"].get("shap_explanation")
            self.assertIsNotNone(shap_exp)
            self.assertIn("features", shap_exp["explanation"])


class TestAPISecurityAndDatabaseSafety(unittest.TestCase):
    """Verify endpoint security, public accessibility, and read-only database safety."""

    def setUp(self):
        self.client = app.test_client()

    def test_14_predictor_and_explain_endpoints_are_public(self):
        """Test that /scholarship/predict and /scholarship/explain require NO Authorization header."""
        payload = {
            "academic_score": 80.0,
            "previous_score": 78.0,
            "attendance": 85.0,
            "annual_income": 180000.0,
            "application_category": "General",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }

        # 1. Test /scholarship/explain public access
        res_exp = self.client.post("/scholarship/explain", json=payload)
        self.assertEqual(res_exp.status_code, 200, f"/scholarship/explain should be public: {res_exp.get_json()}")
        self.assertEqual(res_exp.get_json().get("status"), "success")

        # 2. Test /scholarship/predict public access
        predict_payload = {
            "academic_score": 80.0,
            "previous_score": 78.0,
            "attendance": 85.0,
            "annual_income": 180000.0,
            "application_category": "GENERAL",
            "documents": {"marksheet": True},
        }
        res_pred = self.client.post("/scholarship/predict", json=predict_payload)
        self.assertEqual(res_pred.status_code, 200, f"/scholarship/predict should be public: {res_pred.get_json()}")

    def test_15_read_only_and_no_database_mutations(self):
        """Test that SHAP explainability execution produces zero mutations in applications, decisions, rules."""
        # Count existing rows before
        apps_before = len(supabase.table("applications").select("id").execute().data or [])
        decisions_before = len(supabase.table("decisions").select("id").execute().data or [])
        rules_before = len(supabase.table("scholarship_rules").select("id").execute().data or [])

        # Execute prediction and SHAP explanation
        payload = {
            "academic_score": 82.0,
            "previous_score": 80.0,
            "attendance": 88.0,
            "annual_income": 200000.0,
            "application_category": "OBC",
            "scholarship_scheme": "Merit Scholarship",
            "documents_verified": "VERIFIED",
        }
        self.client.post("/scholarship/explain", json=payload)
        self.client.post("/scholarship/predict", json={
            "academic_score": 82.0,
            "previous_score": 80.0,
            "attendance": 88.0,
            "annual_income": 200000.0,
            "application_category": "OBC",
            "documents": {"marksheet": True},
        })

        # Count existing rows after
        apps_after = len(supabase.table("applications").select("id").execute().data or [])
        decisions_after = len(supabase.table("decisions").select("id").execute().data or [])
        rules_after = len(supabase.table("scholarship_rules").select("id").execute().data or [])

        self.assertEqual(apps_before, apps_after, "Applications count must not change")
        self.assertEqual(decisions_before, decisions_after, "Decisions count must not change")
        self.assertEqual(rules_before, rules_after, "Scholarship rules count must not change")


if __name__ == "__main__":
    unittest.main()
