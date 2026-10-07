import re


def extract_marksheet_fields(text: str) -> dict:
    """
    Extract structured fields from marksheet text.

    Returns:
        {
            "student_name": ...,
            "academic_score": ...,
            "previous_score": ...
        }
    """

    result = {
        "student_name": None,
        "academic_score": None,
        "previous_score": None
    }

    # Student name
    name_match = re.search(
        r"Student\s*Name\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )

    if name_match:
        result["student_name"] = name_match.group(1).strip()

    # Academic score
    academic_match = re.search(
        r"Academic\s*Score\s*:\s*([0-9]+(?:\.[0-9]+)?)",
        text,
        re.IGNORECASE
    )

    if academic_match:
        result["academic_score"] = float(
            academic_match.group(1)
        )

    # Previous score
    previous_match = re.search(
        r"Previous\s*Score\s*:\s*([0-9]+(?:\.[0-9]+)?)",
        text,
        re.IGNORECASE
    )

    if previous_match:
        result["previous_score"] = float(
            previous_match.group(1)
        )

    return result

def extract_income_certificate_fields(text: str) -> dict:
    result = {
        "student_name": None,
        "annual_income": None
    }

    name_match = re.search(
        r"Student\s*Name\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )

    if name_match:
        result["student_name"] = name_match.group(1).strip()

    income_match = re.search(
        r"Annual\s*Income\s*:\s*₹?\s*([0-9]+(?:\.[0-9]+)?)",
        text,
        re.IGNORECASE
    )

    if income_match:
        result["annual_income"] = float(income_match.group(1))

    return result
def extract_id_proof_fields(text: str) -> dict:
    result = {
        "student_name": None,
        "id_type": None,
        "id_number": None
    }

    name_match = re.search(
        r"Student\s*Name\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )

    if name_match:
        result["student_name"] = name_match.group(1).strip()

    id_type_match = re.search(
        r"ID\s*Type\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )

    if id_type_match:
        result["id_type"] = id_type_match.group(1).strip()

    id_number_match = re.search(
        r"ID\s*Number\s*:\s*([A-Za-z0-9-]+)",
        text,
        re.IGNORECASE
    )

    if id_number_match:
        result["id_number"] = id_number_match.group(1).strip()

    return result


def normalize_category(category_val) -> str:
    """
    Normalize category variations to standard codes:
    SC, ST, OBC, EWS, GENERAL.
    Returns None if category cannot be resolved or is empty.
    """
    if not category_val:
        return None

    cleaned = re.sub(r"[\s\-_]+", " ", str(category_val)).strip().upper()

    mapping = {
        # SC
        "SC": "SC",
        "SCHEDULED CASTE": "SC",
        "SCHEDULED CASTES": "SC",
        # ST
        "ST": "ST",
        "SCHEDULED TRIBE": "ST",
        "SCHEDULED TRIBES": "ST",
        # OBC
        "OBC": "OBC",
        "OTHER BACKWARD CLASS": "OBC",
        "OTHER BACKWARD CLASSES": "OBC",
        "OTHER BACKWARD CATEGORY": "OBC",
        # EWS
        "EWS": "EWS",
        "ECONOMICALLY WEAKER SECTION": "EWS",
        "ECONOMICALLY WEAKER SECTIONS": "EWS",
        # GENERAL
        "GENERAL": "GENERAL",
        "GEN": "GENERAL",
        "GENERAL CATEGORY": "GENERAL",
        "UNRESERVED": "GENERAL",
        "UR": "GENERAL",
        "OPEN": "GENERAL",
    }

    if cleaned in mapping:
        return mapping[cleaned]

    # Partial matching fallback
    if "SCHEDULED CASTE" in cleaned or cleaned == "SC":
        return "SC"
    if "SCHEDULED TRIBE" in cleaned or cleaned == "ST":
        return "ST"
    if "OTHER BACKWARD" in cleaned or "OBC" in cleaned.split():
        return "OBC"
    if "ECONOMICALLY WEAKER" in cleaned or "EWS" in cleaned.split():
        return "EWS"
    if "GENERAL" in cleaned or "UNRESERVED" in cleaned:
        return "GENERAL"

    return cleaned


def extract_category_certificate_fields(text: str) -> dict:
    """
    Extract structured fields from category certificate text.
    Extracts student_name, category, normalized_category, certificate_number,
    issuing_authority, issue_date, and expiry_date.
    """
    result = {
        "student_name": None,
        "category": None,
        "normalized_category": None,
        "certificate_number": None,
        "issuing_authority": None,
        "issue_date": None,
        "expiry_date": None,
    }

    # Student name
    name_match = re.search(
        r"(?:Student\s*Name|Applicant\s*Name|Candidate\s*Name|Name)\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )
    if name_match:
        result["student_name"] = name_match.group(1).strip()

    # Category
    category_match = re.search(
        r"(?:Category|Caste\s*Category|Social\s*Category|Caste)\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )
    if category_match:
        raw_category = category_match.group(1).strip()
        result["category"] = raw_category
        result["normalized_category"] = normalize_category(raw_category)

    # Certificate number
    certificate_match = re.search(
        r"(?:Certificate\s*Number|Certificate\s*No\.?|Cert\.?\s*No\.?)\s*:\s*([A-Za-z0-9\-_/]+)",
        text,
        re.IGNORECASE
    )
    if certificate_match:
        result["certificate_number"] = certificate_match.group(1).strip()

    # Issuing authority
    authority_match = re.search(
        r"(?:Issuing\s*Authority|Issued\s*By|Authority)\s*:\s*([^\n\r]+)",
        text,
        re.IGNORECASE
    )
    if authority_match:
        result["issuing_authority"] = authority_match.group(1).strip()

    # Issue date
    issue_match = re.search(
        r"(?:Issue\s*Date|Date\s*of\s*Issue)\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{2}-[0-9]{2}-[0-9]{4})",
        text,
        re.IGNORECASE
    )
    if issue_match:
        result["issue_date"] = issue_match.group(1).strip()

    # Expiry / validity date
    expiry_match = re.search(
        r"(?:Expiry\s*Date|Date\s*of\s*Expiry|Valid\s*Till|Valid\s*Upto|Validity\s*Date|Validity)\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{2}-[0-9]{2}-[0-9]{4})",
        text,
        re.IGNORECASE
    )
    if expiry_match:
        result["expiry_date"] = expiry_match.group(1).strip()

    return result