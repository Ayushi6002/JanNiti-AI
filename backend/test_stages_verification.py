import numpy as np
from backend.ml_service import ml_service
from backend.scholarship_predictor_service import validate_prediction_input, predict_scholarships

ml_service.set_active_version("stage_aware_v1")

stages_test = [
    {
        "name": "FIRST_YEAR — HSC",
        "raw_input": {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "HSC_12TH",
            "qualifying_score": 88.0,
            "ssc_score": 85.0,
            "annual_income": 120000,
            "category": "OBC",
            "documents_verified": "VERIFIED"
        },
        "expected_att": np.nan,
        "expected_att_app": 0,
        "expected_qtype": "HSC_12TH"
    },
    {
        "name": "FIRST_YEAR — Diploma",
        "raw_input": {
            "academic_stage": "FIRST_YEAR",
            "qualification_type": "DIPLOMA",
            "qualifying_score": 90.0,
            "ssc_score": 82.0,
            "annual_income": 150000,
            "category": "SC",
            "documents_verified": "VERIFIED"
        },
        "expected_att": np.nan,
        "expected_att_app": 0,
        "expected_qtype": "DIPLOMA"
    },
    {
        "name": "SECOND_YEAR",
        "raw_input": {
            "academic_stage": "SECOND_YEAR",
            "first_year_score": 82.0,
            "qualifying_score": 84.0,
            "attendance": 86.0,
            "annual_income": 200000,
            "category": "General",
            "documents_verified": "VERIFIED"
        },
        "expected_att": 86.0,
        "expected_att_app": 1,
        "expected_qtype": "NOT_APPLICABLE"
    },
    {
        "name": "THIRD_YEAR",
        "raw_input": {
            "academic_stage": "THIRD_YEAR",
            "second_year_score": 84.0,
            "first_year_score": 80.0,
            "attendance": 88.0,
            "annual_income": 180000,
            "category": "EWS",
            "documents_verified": "VERIFIED"
        },
        "expected_att": 88.0,
        "expected_att_app": 1,
        "expected_qtype": "NOT_APPLICABLE"
    },
    {
        "name": "FOURTH_YEAR",
        "raw_input": {
            "academic_stage": "FOURTH_YEAR",
            "third_year_score": 86.0,
            "second_year_score": 83.0,
            "attendance": 89.0,
            "annual_income": 220000,
            "category": "ST",
            "documents_verified": "VERIFIED"
        },
        "expected_att": 89.0,
        "expected_att_app": 1,
        "expected_qtype": "NOT_APPLICABLE"
    },
    {
        "name": "POSTGRADUATE",
        "raw_input": {
            "academic_stage": "POSTGRADUATE",
            "ug_score": 85.0,
            "previous_score": 82.0,
            "attendance": 90.0,
            "annual_income": 250000,
            "category": "OBC",
            "documents_verified": "VERIFIED"
        },
        "expected_att": 90.0,
        "expected_att_app": 1,
        "expected_qtype": "NOT_APPLICABLE"
    }
]

print("=== ACADEMIC STAGE END-TO-END VERIFICATION (stage_aware_v1) ===")
for case in stages_test:
    name = case["name"]
    raw = case["raw_input"]

    # Check encoding
    encoded_df = ml_service._encode_input(raw)
    cols = list(encoded_df.columns)
    assert len(cols) == 10, f"Expected 10 features, got {len(cols)}"

    att_val = encoded_df["attendance"].values[0]
    att_app = encoded_df["is_attendance_applicable"].values[0]
    qtype = encoded_df["qualification_type"].values[0]
    stage = encoded_df["academic_stage"].values[0]

    if np.isnan(case["expected_att"]):
        assert np.isnan(att_val), f"Expected NaN attendance for {name}, got {att_val}"
    else:
        assert att_val == case["expected_att"], f"Expected attendance {case['expected_att']}, got {att_val}"

    assert att_app == case["expected_att_app"], f"Expected is_attendance_applicable={case['expected_att_app']}, got {att_app}"

    # Prediction & SHAP
    res = ml_service.predict_and_explain(raw)
    p_approve = res["estimated_approval_probability"]
    final_dec = res["final_decision"]
    reasons = res["top_reasons"]

    print(f"\n[OK] Stage: {name}")
    print(f"     Features Encoded: {dict(encoded_df.iloc[0])}")
    print(f"     Decision: {final_dec} | P(APPROVE): {p_approve:.4f}")
    print(f"     Top SHAP Reasons ({len(reasons)}):")
    for r in reasons:
        print(f"       - {r['feature']}: impact={r['impact']}, dir={r['direction']} | {r['human_explanation']}")

    # For first-year, verify attendance is not falsely penalized
    if "FIRST_YEAR" in name:
        for r in reasons:
            if r["feature"] in ("attendance", "is_attendance_applicable"):
                print(f"       -> Attendance factor direction in first year: {r['direction']}")
                assert r["direction"] == "neutral" or r["impact"] == 0.0

print("\n>>> ALL ACADEMIC STAGES VERIFIED END-TO-END WITH REMEDIATED CANDIDATE MODEL!")
