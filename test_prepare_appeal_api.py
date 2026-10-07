from backend.application_service import create_application
from backend.decision_service import process_human_decision


APPLICANT_ID = "e5c9e479-dde4-4dd7-91ee-b25d721332a7"
MERIT_SCHEME_ID = "91fc26f7-e746-4dae-862b-ddc1a8c3527c"


# 1. Create a fresh application
application_response = create_application(
    applicant_id=APPLICANT_ID,
    scholarship_scheme_id=MERIT_SCHEME_ID,
    academic_score=88.5,
    previous_score=84.0,
    attendance=92.0,
    annual_income=250000,
    application_category="GENERAL",
)

application = application_response.data[0]

application_id = application["id"]

print("APPLICATION CREATED")
print("Application ID:", application_id)
print("Application Number:", application["application_number"])


# 2. Finalize the application
decision_result = process_human_decision(
    application_id=application_id,
    decision="APPROVED",
    reason="Preparing finalized application for appeal API testing.",
    decided_by=None,
    admin_comment="Appeal API test setup",
)

print("\nAPPLICATION FINALIZED")
print("Old status:", decision_result["old_status"])
print("New status:", decision_result["new_status"])
print("Decision:", decision_result["decision"])