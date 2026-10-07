from backend.supabase_client import supabase
from backend.audit_service import log_audit


ALLOWED_DECISIONS = {
    "APPROVED",
    "REJECTED",
}

ALLOWED_REVIEW_STATUSES = {
    "SUBMITTED",
    "DOCUMENT_CHECK",
    "AI_PROCESSING",
    "HUMAN_REVIEW",
}


def record_human_decision(
    application_id: str,
    decision: str,
    reason: str,
    ai_prediction_id: str | None = None,
    decided_by: str | None = None,
    admin_comment: str | None = None,
):
    """
    Record a human evaluator's final decision.

    The AI prediction is stored separately in ai_predictions.
    This table stores the human decision and links it
    to the AI prediction that was reviewed.
    """

    decision = decision.upper().strip()

    if decision not in ALLOWED_DECISIONS:
        raise ValueError(
            f"Invalid decision '{decision}'. "
            f"Expected one of: {sorted(ALLOWED_DECISIONS)}"
        )

    if not reason or not reason.strip():
        raise ValueError("A reason is required for a human decision.")

    data = {
        "application_id": application_id,
        "decision": decision,
        "reason": reason.strip(),
        "decision_type": "HUMAN",
        "ai_prediction_id": ai_prediction_id,
        "decided_by": decided_by,
        "admin_comment": admin_comment,
    }

    response = (
        supabase
        .table("decisions")
        .insert(data)
        .execute()
    )

    return response.data


def update_application_status(application_id: str, decision: str):
    """
    Update the application status after a human decision.
    """

    decision = decision.upper().strip()

    if decision == "APPROVED":
        status = "APPROVED"
    elif decision == "REJECTED":
        status = "REJECTED"
    else:
        raise ValueError(
            f"Invalid final decision '{decision}'. "
            f"Expected APPROVED or REJECTED."
        )

    response = (
        supabase
        .table("applications")
        .update({
            "status": status
        })
        .eq("id", application_id)
        .execute()
    )

    return response.data


def validate_ai_prediction(
    application_id: str,
    ai_prediction_id: str,
):
    """
    Verify that the supplied AI prediction exists
    and belongs to the same application.
    """

    response = (
        supabase
        .table("ai_predictions")
        .select("id, application_id, prediction, probability, model_version")
        .eq("id", ai_prediction_id)
        .single()
        .execute()
    )

    prediction = response.data

    if not prediction:
        raise ValueError(
            f"AI prediction '{ai_prediction_id}' was not found."
        )

    if prediction["application_id"] != application_id:
        raise ValueError(
            "The supplied AI prediction does not belong "
            "to this application."
        )

    return prediction


def process_human_decision(
    application_id: str,
    decision: str,
    reason: str,
    ai_prediction_id: str | None = None,
    decided_by: str | None = None,
    admin_comment: str | None = None,
):
    """
    Complete human decision workflow:

    1. Read the current application status.
    2. Validate that the application is in a reviewable state.
    3. Validate the AI prediction if supplied.
    4. Record the human decision.
    5. Update the application status.
    6. Create an audit log.
    """

    decision = decision.upper().strip()

    if decision not in ALLOWED_DECISIONS:
        raise ValueError(
            f"Invalid decision '{decision}'. "
            f"Expected one of: {sorted(ALLOWED_DECISIONS)}"
        )

    if not reason or not reason.strip():
        raise ValueError("A reason is required for a human decision.")

    # Get current application status before changing it
    application_response = (
        supabase
        .table("applications")
        .select("id, status")
        .eq("id", application_id)
        .single()
        .execute()
    )

    application = application_response.data

    if not application:
        raise ValueError(
            f"Application '{application_id}' was not found."
        )

    old_status = application["status"]

    # Prevent decisions on already-finalized or otherwise invalid states
    if old_status not in ALLOWED_REVIEW_STATUSES:
        raise ValueError(
            f"Application '{application_id}' cannot receive a human decision "
            f"while its status is '{old_status}'. "
            f"Expected one of: {sorted(ALLOWED_REVIEW_STATUSES)}"
        )

    # Validate the AI prediction before creating the human decision
    if ai_prediction_id:
        validate_ai_prediction(
            application_id=application_id,
            ai_prediction_id=ai_prediction_id,
        )

    # 1. Record human decision
    decision_result = record_human_decision(
        application_id=application_id,
        decision=decision,
        reason=reason,
        ai_prediction_id=ai_prediction_id,
        decided_by=decided_by,
        admin_comment=admin_comment,
    )

    # 2. Update application status
    status_result = update_application_status(
        application_id,
        decision,
    )

    # 3. Create audit log
    audit_result = log_audit(
        application_id=application_id,
        action="STATUS_CHANGED",
        old_value={
            "status": old_status
        },
        new_value={
            "status": decision
        },
        reason=reason,
        actor_id=decided_by,
        entity_type="application",
        entity_id=application_id,
    )

    return {
        "application_id": application_id,
        "decision": decision,
        "old_status": old_status,
        "new_status": decision,
        "decision_record": decision_result,
        "status_record": status_result,
        "audit_record": audit_result,
    }