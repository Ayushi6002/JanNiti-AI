try:
    from backend.supabase_client import supabase
    from backend.application_service import get_application_verification_data
except ImportError:
    from supabase_client import supabase
    from application_service import get_application_verification_data


def get_required_documents_for_application(application_id: str):
    """
    Get the scholarship scheme and its required documents
    for a specific application.
    """

    response = (
        supabase
        .table("applications")
        .select(
            """
            id,
            scholarship_scheme_id,
            scholarship_schemes (
                scheme_name,
                required_documents
            )
            """
        )
        .eq("id", application_id)
        .single()
        .execute()
    )

    application = response.data

    if not application:
        raise ValueError("Application not found.")

    scheme = application.get("scholarship_schemes")

    if not scheme:
        raise ValueError("Scholarship scheme not found.")

    return scheme["scheme_name"], scheme["required_documents"]


def get_application_documents(application_id: str):
    """
    Fetch all documents uploaded for an application.
    """

    response = (
        supabase
        .table("documents")
        .select(
            """
            id,
            document_type,
            file_name,
            verification_status,
            verification_score,
            extracted_data,
            mismatch_details,
            verified_at
            """
        )
        .eq("application_id", application_id)
        .order("created_at")
        .execute()
    )

    return response.data or []


def generate_verification_summary(application_id: str):
    """
    Generate an application-level document verification summary.

    This does not modify the database yet.
    """

    scheme_name, required_documents = (
        get_required_documents_for_application(application_id)
    )

    documents = get_application_documents(application_id)

    # Group documents by document type.
    documents_by_type = {}

    for document in documents:
        document_type = document["document_type"]

        if document_type not in documents_by_type:
            documents_by_type[document_type] = []

        documents_by_type[document_type].append(document)

    summary = {
        "application_id": application_id,
        "scheme_name": scheme_name,
        "required_documents": required_documents,
        "documents": {},
        "overall_status": None,
        "missing_documents": [],
        "mismatched_documents": [],
        "needs_review_documents": []
    }

    for required_type in required_documents:

        matching_documents = documents_by_type.get(required_type, [])

        # No document uploaded.
        if not matching_documents:
            summary["documents"][required_type] = {
                "status": "MISSING"
            }

            summary["missing_documents"].append(required_type)

            continue

        # Pick the most recently created document.
        # Prefer a verified document.
        verified_documents = [
            document
            for document in matching_documents
            if document["verification_status"] == "VERIFIED"
        ]

        if verified_documents:
            document = verified_documents[-1]
        else:
            # If no verified document exists, use the latest document
            # so that its problem can be surfaced.
            document = matching_documents[-1]

        status = document["verification_status"]

        summary["documents"][required_type] = {
            "document_id": document["id"],
            "file_name": document["file_name"],
            "status": status,
            "score": document["verification_score"],
            "extracted_data": document["extracted_data"],
            "mismatch_details": document["mismatch_details"],
            "verified_at": document["verified_at"]
        }

        if status == "MISMATCH":
            summary["mismatched_documents"].append(required_type)

        elif status in ["NEEDS_REVIEW", "INCOMPLETE", "PENDING"]:
            summary["needs_review_documents"].append(required_type)

    # Determine overall application verification status.
    if summary["missing_documents"]:
        summary["overall_status"] = "INCOMPLETE"

    elif summary["mismatched_documents"]:
        summary["overall_status"] = "NEEDS_REVIEW"

    elif summary["needs_review_documents"]:
        summary["overall_status"] = "NEEDS_REVIEW"

    else:
        summary["overall_status"] = "VERIFIED"

    return summary