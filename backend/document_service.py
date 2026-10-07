try:
    from backend.supabase_client import supabase
    from backend.doc_verifier import extract_text_from_pdf
    from backend.document_extractor import (
        extract_marksheet_fields,
        extract_income_certificate_fields,
        extract_id_proof_fields,
        extract_category_certificate_fields,
    )
    from backend.document_cross_checker import (
        compare_marksheet_with_application,
        compare_income_certificate_with_application,
        compare_id_proof_with_profile,
        compare_category_certificate_with_application,
    )
    from backend.application_service import (
        get_application_verification_data,
        get_applicant_profile,
    )
except ImportError:
    from supabase_client import supabase
    from doc_verifier import extract_text_from_pdf
    from document_extractor import (
        extract_marksheet_fields,
        extract_income_certificate_fields,
        extract_id_proof_fields,
        extract_category_certificate_fields,
    )
    from document_cross_checker import (
        compare_marksheet_with_application,
        compare_income_certificate_with_application,
        compare_id_proof_with_profile,
        compare_category_certificate_with_application,
    )
    from application_service import (
        get_application_verification_data,
        get_applicant_profile,
    )
from datetime import datetime, timezone
import hashlib
from pathlib import Path



def create_document(
    application_id,
    document_type,
    file_name,
    storage_path
):
    data = {
        "application_id": application_id,
        "document_type": document_type,
        "file_name": file_name,
        "storage_path": storage_path,
        "verification_status": "PENDING"
    }

    response = (
        supabase
        .table("documents")
        .insert(data)
        .execute()
    )

    return response


BUCKET_NAME = "application-documents"


def upload_document(
    application_id: str,
    document_type: str,
    file_path: str
):
    file_path_obj = Path(file_path)

    if not file_path_obj.exists():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    storage_path = (
        f"{application_id}/"
        f"{document_type}/"
        f"{file_path_obj.name}"
    )

    with open(file_path_obj, "rb") as file:
        supabase.storage.from_(BUCKET_NAME).upload(
            storage_path,
            file,
            {
                "content-type": "application/pdf",
                "upsert": "false"
            }
        )

    return storage_path


def upload_document_bytes(
    application_id: str,
    document_type: str,
    file_name: str,
    file_bytes: bytes,
    content_type: str = "application/pdf",
    upsert: bool = True
) -> str:
    """
    Upload raw document bytes to Supabase Storage.
    """
    storage_path = (
        f"{application_id}/"
        f"{document_type}/"
        f"{file_name}"
    )

    supabase.storage.from_(BUCKET_NAME).upload(
        storage_path,
        file_bytes,
        {
            "content-type": content_type,
            "upsert": "true" if upsert else "false"
        }
    )

    return storage_path



def update_document_storage(
    document_id,
    file_name,
    storage_path
):
    response = (
        supabase
        .table("documents")
        .update({
            "file_name": file_name,
            "storage_path": storage_path
        })
        .eq("id", document_id)
        .execute()
    )

    return response


def update_document_verification(
    document_id,
    verification_status,
    verification_score,
    extracted_text,
    extracted_data,
    mismatch_details
):
    data = {
        "verification_status": verification_status,
        "verification_score": verification_score,
        "extracted_text": extracted_text,
        "extracted_data": extracted_data,
        "mismatch_details": mismatch_details,
        "verified_at": datetime.now(timezone.utc).isoformat()
    }

    response = (
        supabase
        .table("documents")
        .update(data)
        .eq("id", document_id)
        .execute()
    )

    return response


def download_document(storage_path: str) -> bytes:
    response = (
        supabase
        .storage
        .from_(BUCKET_NAME)
        .download(storage_path)
    )

    if response is None:
        raise RuntimeError(
            f"Supabase returned no data for: {storage_path}"
        )

    return response


def process_marksheet_document(
    document_id,
    application_id,
    storage_path
):
    print("STEP 1: Downloading document...")

    file_bytes = download_document(storage_path)

    print(
        "STEP 1 OK:",
        type(file_bytes),
        len(file_bytes)
    )

    print("STEP 2: Extracting text...")

    extracted_text = extract_text_from_pdf(file_bytes)

    print(
        "STEP 2 OK:",
        repr(extracted_text)
    )

    if not extracted_text.strip():
        return update_document_verification(
            document_id=document_id,
            verification_status="NEEDS_REVIEW",
            verification_score=0.0,
            extracted_text="",
            extracted_data={},
            mismatch_details={
                "reason": "No extractable text found"
            }
        )

    print("STEP 3: Extracting fields...")

    extracted_data = extract_marksheet_fields(
        extracted_text
    )

    print(
        "STEP 3 OK:",
        extracted_data
    )

    print("STEP 4: Fetching application data...")

    application_data = get_application_verification_data(
        application_id
    )

    print(
        "STEP 4 OK:",
        application_data
    )

    print("STEP 5: Comparing...")

    comparison = compare_marksheet_with_application(
        extracted_data,
        application_data
    )

    print(
        "STEP 5 OK:",
        comparison
    )

    total_fields = len(comparison["fields"])

    matched_fields = sum(
        1
        for field in comparison["fields"].values()
        if field["status"] == "MATCH"
    )

    verification_score = (
        (matched_fields / total_fields) * 100
        if total_fields > 0
        else 0.0
    )

    overall_status = comparison["overall_status"]

    if overall_status == "MATCH":
        verification_status = "VERIFIED"

    elif overall_status == "MISMATCH":
        verification_status = "MISMATCH"

    else:
        verification_status = "NEEDS_REVIEW"

    print("STEP 6: Updating document...")

    result = update_document_verification(
        document_id=document_id,
        verification_status=verification_status,
        verification_score=verification_score,
        extracted_text=extracted_text,
        extracted_data=extracted_data,
        mismatch_details=comparison["fields"]
    )

    print(
        "STEP 6 RESULT:",
        result
    )

    return result


def process_income_certificate_document(
    document_id,
    application_id,
    storage_path
):
    print("STEP 1: Downloading income certificate...")

    file_bytes = download_document(storage_path)

    print(
        "STEP 1 OK:",
        type(file_bytes),
        len(file_bytes)
    )

    print("STEP 2: Extracting text...")

    extracted_text = extract_text_from_pdf(file_bytes)

    print(
        "STEP 2 OK:",
        repr(extracted_text)
    )

    if not extracted_text.strip():
        return update_document_verification(
            document_id=document_id,
            verification_status="NEEDS_REVIEW",
            verification_score=0.0,
            extracted_text="",
            extracted_data={},
            mismatch_details={
                "reason": "No extractable text found"
            }
        )

    print("STEP 3: Extracting income fields...")

    extracted_data = extract_income_certificate_fields(
        extracted_text
    )

    print(
        "STEP 3 OK:",
        extracted_data
    )

    print("STEP 4: Fetching application data...")

    application_data = get_application_verification_data(
        application_id
    )

    print(
        "STEP 4 OK:",
        application_data
    )

    print("STEP 5: Comparing income...")

    comparison = compare_income_certificate_with_application(
        extracted_data,
        application_data
    )

    print(
        "STEP 5 OK:",
        comparison
    )

    total_fields = len(comparison["fields"])

    matched_fields = sum(
        1
        for field in comparison["fields"].values()
        if field["status"] == "MATCH"
    )

    verification_score = (
        (matched_fields / total_fields) * 100
        if total_fields > 0
        else 0.0
    )

    overall_status = comparison["overall_status"]

    if overall_status == "MATCH":
        verification_status = "VERIFIED"

    elif overall_status == "MISMATCH":
        verification_status = "MISMATCH"

    else:
        verification_status = "NEEDS_REVIEW"

    print("STEP 6: Updating document...")

    result = update_document_verification(
        document_id=document_id,
        verification_status=verification_status,
        verification_score=verification_score,
        extracted_text=extracted_text,
        extracted_data=extracted_data,
        mismatch_details=comparison["fields"]
    )

    print(
        "STEP 6 RESULT:",
        result
    )

    return result


def process_id_proof_document(
    document_id,
    application_id,
    storage_path
):
    print("STEP 1: Downloading ID proof...")

    file_bytes = download_document(storage_path)

    print(
        "STEP 1 OK:",
        type(file_bytes),
        len(file_bytes)
    )

    print("STEP 2: Extracting text...")

    extracted_text = extract_text_from_pdf(file_bytes)

    print(
        "STEP 2 OK:",
        repr(extracted_text)
    )

    if not extracted_text.strip():
        return update_document_verification(
            document_id=document_id,
            verification_status="NEEDS_REVIEW",
            verification_score=0.0,
            extracted_text="",
            extracted_data={},
            mismatch_details={
                "reason": "No extractable text found"
            }
        )

    print("STEP 3: Extracting ID fields...")

    extracted_data = extract_id_proof_fields(
        extracted_text
    )

    print(
        "STEP 3 OK:",
        extracted_data
    )

    print("STEP 4: Fetching applicant profile...")

    application_data = get_application_verification_data(
        application_id
    )

    applicant_id = application_data["applicant_id"]

    profile_data = get_applicant_profile(
        applicant_id
    )

    print(
        "STEP 4 OK:",
        profile_data
    )

    print("STEP 5: Comparing ID proof...")

    comparison = compare_id_proof_with_profile(
        extracted_data,
        profile_data
    )

    print(
        "STEP 5 OK:",
        comparison
    )

    total_fields = len(comparison["fields"])

    matched_fields = sum(
        1
        for field in comparison["fields"].values()
        if field["status"] == "MATCH"
    )

    verification_score = (
        (matched_fields / total_fields) * 100
        if total_fields > 0
        else 0.0
    )

    overall_status = comparison["overall_status"]

    if overall_status == "MATCH":
        verification_status = "VERIFIED"

    elif overall_status == "MISMATCH":
        verification_status = "MISMATCH"

    else:
        verification_status = "NEEDS_REVIEW"

    print("STEP 6: Updating document...")

    result = update_document_verification(
        document_id=document_id,
        verification_status=verification_status,
        verification_score=verification_score,
        extracted_text=extracted_text,
        extracted_data=extracted_data,
        mismatch_details=comparison["fields"]
    )

    print(
        "STEP 6 RESULT:",
        result
    )

    return result


def process_category_certificate_document(
    document_id,
    application_id,
    storage_path
):
    print("STEP 1: Downloading category certificate...")

    file_bytes = download_document(storage_path)

    print(
        "STEP 1 OK:",
        type(file_bytes),
        len(file_bytes)
    )

    print("STEP 2: Extracting text...")

    extracted_text = extract_text_from_pdf(file_bytes)

    print(
        "STEP 2 OK:",
        repr(extracted_text)
    )

    if not extracted_text.strip():
        return update_document_verification(
            document_id=document_id,
            verification_status="NEEDS_REVIEW",
            verification_score=0.0,
            extracted_text="",
            extracted_data={},
            mismatch_details={
                "reason": "No extractable text found"
            }
        )

    print("STEP 3: Extracting category fields...")

    extracted_data = extract_category_certificate_fields(
        extracted_text
    )

    print(
        "STEP 3 OK:",
        extracted_data
    )

    print("STEP 4: Fetching application & profile data...")

    application_data = get_application_verification_data(
        application_id
    )

    applicant_id = application_data.get("applicant_id") if isinstance(application_data, dict) else None
    profile_data = get_applicant_profile(applicant_id) if applicant_id else None

    print(
        "STEP 4 OK:",
        application_data,
        profile_data
    )

    print("STEP 5: Comparing category certificate...")

    comparison = compare_category_certificate_with_application(
        extracted_data,
        application_data,
        profile_data
    )

    print(
        "STEP 5 OK:",
        comparison
    )

    verification_score = comparison.get("verification_score", 0.0)
    verification_status = comparison.get("verification_status", "NEEDS_REVIEW")

    print("STEP 6: Updating document...")

    result = update_document_verification(
        document_id=document_id,
        verification_status=verification_status,
        verification_score=verification_score,
        extracted_text=extracted_text,
        extracted_data=extracted_data,
        mismatch_details=comparison
    )

    print(
        "STEP 6 RESULT:",
        result
    )

    return result


DOCUMENT_PROCESSORS = {
    "marksheet": process_marksheet_document,
    "income_certificate": process_income_certificate_document,
    "id_proof": process_id_proof_document,
    "category_certificate": process_category_certificate_document,
}


def process_document(
    document_id: str,
    application_id: str,
    document_type: str,
    storage_path: str
):
    """
    Route and process a document according to its document type.
    Extracts text, extracts structured fields, cross-checks against application/profile,
    and updates document verification fields in Supabase.
    """
    processor = DOCUMENT_PROCESSORS.get(document_type)

    if processor:
        return processor(document_id, application_id, storage_path)

    # Fallback for document types without specialized cross-checkers
    file_bytes = download_document(storage_path)
    extracted_text = extract_text_from_pdf(file_bytes)

    verification_status = "VERIFIED" if extracted_text.strip() else "NEEDS_REVIEW"
    verification_score = 100.0 if extracted_text.strip() else 0.0

    return update_document_verification(
        document_id=document_id,
        verification_status=verification_status,
        verification_score=verification_score,
        extracted_text=extracted_text,
        extracted_data={},
        mismatch_details={}
    )