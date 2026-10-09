try:
    from backend.supabase_client import supabase
    from backend.ml_application_service import predict_application
    from backend.ml_service import ml_service
except ImportError:
    from supabase_client import supabase
    from ml_application_service import predict_application
    from ml_service import ml_service


def save_prediction(application_id: str):
    """
    Run ML prediction for an application and persist
    the prediction + explanation in Supabase.
    """

    result = predict_application(application_id)

    prediction = result["prediction"]
    active_ver = prediction.get("model_version") or ml_service.active_version or "jan_niti_rf_v2"

    data = {
        "application_id": application_id,
        "model_version": active_ver,
        "prediction": prediction["final_decision"],
        "probability": prediction["confidence"],
        "explanation": {
            "model_decision": prediction["model_decision"],
            "final_decision": prediction["final_decision"],
            "confidence": prediction["confidence"],
            "override_applied": prediction["override_applied"],
        },
        "top_reasons": prediction["top_reasons"],
        "feature_breakdown": prediction["top_reasons"],
    }


    response = (
        supabase
        .table("ai_predictions")
        .insert(data)
        .execute()
    )

    return response.data