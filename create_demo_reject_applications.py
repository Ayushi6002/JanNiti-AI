import sys
from pathlib import Path

# Add project root only
root_dir = str(Path(__file__).resolve().parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.supabase_client import supabase
from backend.application_service import create_application, update_application_status
from backend.document_service import create_document, upload_document_bytes, process_document
from backend.verification_service import generate_verification_summary
from backend.eligibility_service import evaluate_application_eligibility
from backend.prediction_service import save_prediction
from backend.anomaly_detection_service import analyze_and_record_application_anomalies

APPLICANT_ID = "e5c9e479-dde4-4dd7-91ee-b25d721332a7"
MERIT_SCHEME_ID = "91fc26f7-e746-4dae-862b-ddc1a8c3527c"

def create_demo_applications():
    # Load test document bytes
    with open("test_marksheet.pdf", "rb") as f:
        marksheet_bytes = f.read()
    with open("test_id_proof.pdf", "rb") as f:
        id_proof_bytes = f.read()
    with open("test_income_certificate.pdf", "rb") as f:
        income_bytes = f.read()

    demo_configs = [
        {
            "tag": "DEMO REJECT 1",
            "academic_score": 35.0,
            "previous_score": 38.0,
            "attendance": 40.0,
            "annual_income": 800000.0,
            "application_category": "GENERAL",
        },
        {
            "tag": "DEMO REJECT 2",
            "academic_score": 32.0,
            "previous_score": 35.0,
            "attendance": 42.0,
            "annual_income": 750000.0,
            "application_category": "GENERAL",
        }
    ]

    created_apps = []

    for cfg in demo_configs:
        print(f"\n--- Creating {cfg['tag']} ---")
        app_res = create_application(
            applicant_id=APPLICANT_ID,
            scholarship_scheme_id=MERIT_SCHEME_ID,
            academic_score=cfg["academic_score"],
            previous_score=cfg["previous_score"],
            attendance=cfg["attendance"],
            annual_income=cfg["annual_income"],
            application_category=cfg["application_category"],
        )
        app_id = app_res.data[0]["id"]
        app_num = app_res.data[0]["application_number"]
        print(f"Created application: {app_id} ({app_num})")

        # Set status to DOCUMENT_CHECK
        update_application_status(app_id, "DOCUMENT_CHECK")

        # Upload & process documents
        docs_to_upload = [
            ("marksheet", "test_marksheet.pdf", marksheet_bytes),
            ("id_proof", "test_id_proof.pdf", id_proof_bytes),
            ("income_certificate", "test_income_certificate.pdf", income_bytes),
        ]

        for doc_type, file_name, file_bytes in docs_to_upload:
            storage_path = upload_document_bytes(
                application_id=app_id,
                document_type=doc_type,
                file_name=file_name,
                file_bytes=file_bytes,
                content_type="application/pdf"
            )
            doc_record_res = create_document(
                application_id=app_id,
                document_type=doc_type,
                file_name=file_name,
                storage_path=storage_path
            )
            doc_id = doc_record_res.data[0]["id"]
            process_document(doc_id, app_id, doc_type, storage_path)
            print(f"  Processed {doc_type}: {doc_id}")

        # Verification summary & Eligibility
        summary = generate_verification_summary(app_id)
        print(f"  Verification Summary: {summary['overall_status']}")

        eligibility = evaluate_application_eligibility(app_id, MERIT_SCHEME_ID)
        print(f"  Eligibility: eligible={eligibility.get('eligible')}")

        # AI Processing
        update_application_status(app_id, "AI_PROCESSING")
        pred_res = save_prediction(app_id)
        pred_data = pred_res[0] if isinstance(pred_res, list) else pred_res
        print(f"  AI Prediction: {pred_data.get('prediction')} (probability: {pred_data.get('probability')})")

        # Anomaly analysis
        try:
            analyze_and_record_application_anomalies(app_id)
        except Exception as e:
            print("  Anomaly note:", e)

        # Transition to HUMAN_REVIEW (Pending evaluator decision)
        update_application_status(app_id, "HUMAN_REVIEW")

        created_apps.append({
            "id": app_id,
            "application_number": app_num,
            "prediction": pred_data.get("prediction"),
            "probability": pred_data.get("probability"),
            "status": "HUMAN_REVIEW",
        })

    print("\nSummary of created demo applications:")
    for a in created_apps:
        print(a)

if __name__ == "__main__":
    create_demo_applications()
