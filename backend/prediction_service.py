try:
    from backend.supabase_client import supabase
    from backend.ml_application_service import predict_application
except ImportError:
    from supabase_client import supabase
    from ml_application_service import predict_application


MODEL_VERSION = "jan_niti_rf_v2"


def save_prediction(application_id: str):
    """
    Run ML prediction for an application and persist
    the prediction + explanation in Supabase.
    """

    result = predict_application(application_id)

    prediction = result["prediction"]

    data = {
        "application_id": application_id,
        "model_version": MODEL_VERSION,
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