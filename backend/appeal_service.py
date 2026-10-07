try:
    from backend.supabase_client import supabase
except ImportError:
    from supabase_client import supabase


ALLOWED_APPEAL_STATUSES = {
    "PENDING",
    "RESOLVED",
    "REJECTED",
}



def create_appeal(application_id: str, applicant_id: str, reason: str):
    """
    Create a new appeal for an application.
    """

    reason = (reason or "").strip()

    if not application_id:
        raise ValueError("Application ID is required.")

    if not applicant_id:
        raise ValueError("Applicant ID is required.")

    if not reason:
        raise ValueError("Appeal reason is required.")

    # Verify that the application belongs to this applicant.
    application_response = (
        supabase.table("applications")
        .select("id, applicant_id, status")
        .eq("id", application_id)
        .single()
        .execute()
    )

    application = application_response.data

    if not application:
        raise ValueError("Application not found.")

    if application["applicant_id"] != applicant_id:
        raise ValueError(
            "This application does not belong to the applicant."
        )

    # Appeals are intended for finalized applications.
    has_final_decision = application.get("status") in {"APPROVED", "REJECTED"}
    if not has_final_decision:
        try:
            dec_res = (
                supabase.table("decisions")
                .select("decision")
                .eq("application_id", application_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if dec_res.data and (dec_res.data[0].get("decision") or "").upper() in {"APPROVED", "REJECTED"}:
                has_final_decision = True
                latest_decision_val = (dec_res.data[0].get("decision") or "").upper()
                supabase.table("applications").update({"status": latest_decision_val}).eq("id", application_id).execute()
        except Exception as sync_err:
            print("Decision status sync warning during appeal:", sync_err)

    if not has_final_decision:
        raise ValueError(
            "An appeal can only be submitted after a final application decision."
        )

    # Prevent multiple pending appeals for the same application.
    existing_response = (
        supabase.table("appeals")
        .select("id, status")
        .eq("application_id", application_id)
        .eq("status", "PENDING")
        .execute()
    )

    if existing_response.data:
        raise ValueError(
            "This application already has a pending appeal."
        )

    data = {
        "application_id": application_id,
        "applicant_id": applicant_id,
        "reason": reason,
        "status": "PENDING",
    }

    response = (
        supabase.table("appeals")
        .insert(data)
        .execute()
    )

    # Transition application status to APPEAL_PENDING
    try:
        supabase.table("applications").update({"status": "APPEAL_PENDING"}).eq("id", application_id).execute()
    except Exception:
        pass

    return response.data[0] if (response.data and isinstance(response.data, list)) else response.data


def get_appeal_by_id(appeal_id: str):
    """
    Get a single appeal by ID.
    """

    response = (
        supabase.table("appeals")
        .select("*")
        .eq("id", appeal_id)
        .single()
        .execute()
    )

    return response.data


def get_appeals_by_applicant(applicant_id: str):
    """
    Get all appeals submitted by an applicant.
    """

    response = (
        supabase.table("appeals")
        .select("*")
        .eq("applicant_id", applicant_id)
        .order("created_at", desc=True)
        .execute()
    )

    return response.data


def get_all_appeals():
    """
    Get all appeals for admin/evaluator review.
    """

    response = (
        supabase.table("appeals")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    return response.data


def review_appeal(
    appeal_id: str,
    reviewed_by: str,
    status: str,
    review_comment: str = "",
):
    """
    Review an appeal.
    """

    status = (status or "").strip().upper()
    review_comment = (review_comment or "").strip()

    if status not in {"RESOLVED", "REJECTED"}:
        raise ValueError(
            "Appeal status must be RESOLVED or REJECTED."
    )

    if not reviewed_by:
        raise ValueError("Reviewer ID is required.")

    appeal = get_appeal_by_id(appeal_id)

    if not appeal:
        raise ValueError("Appeal not found.")

    if appeal["status"] != "PENDING":
        raise ValueError(
            f"Appeal cannot be reviewed because its status is "
            f"'{appeal['status']}'."
        )

    data = {
        "status": status,
        "reviewed_by": reviewed_by,
        "review_comment": review_comment or None,
    }

    response = (
        supabase.table("appeals")
        .update(data)
        .eq("id", appeal_id)
        .execute()
    )

    return response.data[0] if (response.data and isinstance(response.data, list)) else response.data