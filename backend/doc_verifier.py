"""
doc_verifier.py
------------------

Document verification for scholarship applications.

Scope:
  - Confirms required documents are present.
  - Extracts text from uploaded PDFs.
  - Checks whether the extracted text is relevant to the
    claimed document type using document-specific keywords.
  - Does NOT verify authenticity.
  - Does NOT cross-check values such as income against
    the application form.

Per-document status:
  VERIFIED / PARTIAL_MATCH / MISMATCH / MISSING

Overall status:
  VERIFIED / UNCERTAIN / INCOMPLETE

Aggregation rule:
  - Any required document MISSING or MISMATCH
    -> overall INCOMPLETE
  - Any required document PARTIAL_MATCH
    -> overall UNCERTAIN
  - All required documents VERIFIED
    -> overall VERIFIED
"""

import io

import pdfplumber

from backend.supabase_client import supabase


# ---------------------------------------------------------
# Verification thresholds
# ---------------------------------------------------------

VERIFIED_THRESHOLD = 0.60
MISMATCH_CUTOFF = 0.30


# ---------------------------------------------------------
# Document keyword configuration
# ---------------------------------------------------------
#
# These are deliberately focused keywords rather than a
# large generic keyword list.
#
# The previous implementation divided the number of matches
# by a large keyword list, causing genuine documents with
# one strong keyword to receive an artificially low score.
#
# Example:
#   "academic" found in a marksheet
#   should not become 1/5 = 0.20 and be treated as a mismatch.
#
# ---------------------------------------------------------

DOC_KEYWORDS = {
    "marksheet": [
        "academic",
        "marks",
        "result",
    ],

    "id_proof": [
        "aadhaar",
        "aadhar",
        "identity",
    ],

    "income_certificate": [
        "income",
        "annual income",
        "income certificate",
    ],

    "category_certificate": [
        "category",
        "caste",
        "community",
    ],
}


# ---------------------------------------------------------
# Strong / primary keywords
# ---------------------------------------------------------
#
# A strong document-specific keyword can independently
# establish a VERIFIED result for this prototype.
#
# This is useful because documents often use only one
# standard term instead of containing every possible
# keyword.
# ---------------------------------------------------------

PRIMARY_KEYWORDS = {
    "marksheet": {
        "academic",
        "marks",
        "result",
    },

    "id_proof": {
        "aadhaar",
        "aadhar",
        "identity",
    },

    "income_certificate": {
        "income",
        "annual income",
        "income certificate",
    },

    "category_certificate": {
        "category",
        "caste",
        "community",
    },
}


def get_required_documents(scholarship_scheme: str) -> list:
    """
    Fetch required documents for a scholarship scheme.

    The application uses scheme_code values such as:

        MERIT
        NEED_BASED
        CATEGORY

    Supabase stores both:
        scheme_code
        scheme_name

    Therefore this function intentionally queries scheme_code.
    """

    scholarship_scheme = (
        str(scholarship_scheme)
        .strip()
        .upper()
    )

    response = (
        supabase
        .table("scholarship_schemes")
        .select("required_documents")
        .eq("scheme_code", scholarship_scheme)
        .single()
        .execute()
    )

    if not response.data:
        return []

    required_documents = response.data.get(
        "required_documents"
    )

    if not required_documents:
        return []

    return required_documents


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from a PDF using pdfplumber.

    Returns an empty string if:
      - the PDF cannot be parsed
      - the PDF contains no extractable text
      - an unexpected extraction error occurs

    Note:
      This prototype does not perform OCR.
    """

    try:
        text_parts = []

        with pdfplumber.open(
            io.BytesIO(file_bytes)
        ) as pdf:

            for page in pdf.pages:
                page_text = page.extract_text()

                if page_text:
                    text_parts.append(page_text)

        return " ".join(text_parts)

    except Exception:
        return ""


def validate_single_document(
    file_bytes: bytes,
    doc_type: str
) -> dict:
    """
    Validate one uploaded document against its expected type.

    Returns:
        status
        matched_keywords
        match_ratio
        note
    """

    # -----------------------------------------------------
    # Validate document type
    # -----------------------------------------------------

    if doc_type not in DOC_KEYWORDS:

        return {
            "status": "MISMATCH",
            "matched_keywords": [],
            "match_ratio": 0.0,
            "note": (
                f"Unknown document type '{doc_type}'"
            ),
        }

    # -----------------------------------------------------
    # Extract PDF text
    # -----------------------------------------------------

    text = extract_text_from_pdf(file_bytes)

    text_lower = text.lower().strip()

    # -----------------------------------------------------
    # Handle empty / unreadable PDFs
    # -----------------------------------------------------

    if not text_lower:

        return {
            "status": "MISMATCH",
            "matched_keywords": [],
            "match_ratio": 0.0,
            "note": (
                "No extractable text found in file "
                "(empty, corrupted, or a scanned image "
                "with no text layer)"
            ),
        }

    # -----------------------------------------------------
    # Keyword matching
    # -----------------------------------------------------

    keywords = DOC_KEYWORDS[doc_type]

    matched_keywords = []

    for keyword in keywords:

        if keyword.lower() in text_lower:
            matched_keywords.append(keyword)

    # -----------------------------------------------------
    # Calculate keyword match ratio
    # -----------------------------------------------------

    match_ratio = (
        len(matched_keywords) / len(keywords)
        if keywords
        else 0.0
    )

    match_ratio = round(
        match_ratio,
        2
    )

    # -----------------------------------------------------
    # Determine whether a strong keyword exists
    # -----------------------------------------------------

    primary_keywords = PRIMARY_KEYWORDS.get(
        doc_type,
        set()
    )

    matched_primary = [
        keyword
        for keyword in matched_keywords
        if keyword.lower() in {
            primary.lower()
            for primary in primary_keywords
        }
    ]

    # -----------------------------------------------------
    # Determine status
    # -----------------------------------------------------
    #
    # A strong document-specific keyword is enough to mark
    # the document VERIFIED in this prototype.
    #
    # Otherwise:
    #   >= 60%  -> VERIFIED
    #   > 30%   -> PARTIAL_MATCH
    #   <= 30%  -> MISMATCH
    #
    # -----------------------------------------------------

    if matched_primary:

        status = "VERIFIED"

        note = (
            "Strong document-specific keyword "
            "identified"
        )

    elif match_ratio >= VERIFIED_THRESHOLD:

        status = "VERIFIED"

        note = None

    elif match_ratio > MISMATCH_CUTOFF:

        status = "PARTIAL_MATCH"

        note = (
            "Some relevant keywords found, "
            "but below confidence threshold"
        )

    else:

        status = "MISMATCH"

        note = (
            "No relevant keywords found - file may "
            "not match the claimed document type"
        )

    return {
        "status": status,
        "matched_keywords": matched_keywords,
        "match_ratio": match_ratio,
        "note": note,
    }


def verify_submission(
    scholarship_scheme: str,
    submitted_files: dict
) -> dict:
    """
    Verify all required documents for an application.

    Parameters
    ----------
    scholarship_scheme:
        Scheme code such as MERIT, NEED_BASED, CATEGORY.

    submitted_files:
        Dictionary mapping document type to raw PDF bytes.

        Example:

            {
                "marksheet": b"...",
                "id_proof": b"...",
                "income_certificate": b"..."
            }

        Missing keys mean the applicant did not submit
        that required document.

    Returns
    -------
    dict
        Overall verification status plus per-document
        verification details.
    """

    # -----------------------------------------------------
    # Get required documents
    # -----------------------------------------------------

    required = get_required_documents(
        scholarship_scheme
    )

    per_document = {}

    # -----------------------------------------------------
    # Verify every required document
    # -----------------------------------------------------

    for doc_type in required:

        # -------------------------------------------------
        # Missing document
        # -------------------------------------------------

        if doc_type not in submitted_files:

            per_document[doc_type] = {
                "status": "MISSING",
                "matched_keywords": [],
                "match_ratio": 0.0,
                "note": (
                    "Required document was not submitted"
                ),
            }

            continue

        # -------------------------------------------------
        # Verify submitted document
        # -------------------------------------------------

        per_document[doc_type] = (
            validate_single_document(
                submitted_files[doc_type],
                doc_type
            )
        )

    # -----------------------------------------------------
    # Aggregate document statuses
    # -----------------------------------------------------

    statuses = {
        document["status"]
        for document in per_document.values()
    }

    # -----------------------------------------------------
    # Overall INCOMPLETE
    # -----------------------------------------------------

    if (
        "MISSING" in statuses
        or "MISMATCH" in statuses
    ):

        overall = "INCOMPLETE"

    # -----------------------------------------------------
    # Overall UNCERTAIN
    # -----------------------------------------------------

    elif "PARTIAL_MATCH" in statuses:

        overall = "UNCERTAIN"

    # -----------------------------------------------------
    # Overall VERIFIED
    # -----------------------------------------------------

    else:

        overall = "VERIFIED"

    # -----------------------------------------------------
    # Return complete verification result
    # -----------------------------------------------------

    return {
        "overall_status": overall,
        "required_documents": required,
        "per_document": per_document,
    }