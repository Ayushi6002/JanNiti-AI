from document_service import update_document_verification


DOCUMENT_ID = "8a4c7f7b-f243-40aa-9707-3bd57f1e4de8"


extracted_text = """
JAN NITI AI TEST DOCUMENT
Student Name: Test Student
Academic Score: 88.5
Previous Score: 84.0
"""


extracted_data = {
    "student_name": "Test Student",
    "academic_score": 88.5,
    "previous_score": 84.0
}


mismatch_details = {
    "academic_score": {
        "status": "MATCH",
        "document_value": 88.5,
        "application_value": 88.5
    },
    "previous_score": {
        "status": "MATCH",
        "document_value": 84.0,
        "application_value": 84.0
    }
}


try:
    response = update_document_verification(
        document_id=DOCUMENT_ID,
        verification_status="VERIFIED",
        verification_score=100.0,
        extracted_text=extracted_text,
        extracted_data=extracted_data,
        mismatch_details=mismatch_details
    )

    print("Document verification result saved!")

    for document in response.data:
        print("\nDocument:")
        print("ID:", document["id"])
        print("Status:", document["verification_status"])
        print("Score:", document["verification_score"])
        print("Extracted Data:", document["extracted_data"])
        print("Mismatch Details:", document["mismatch_details"])
        print("Verified At:", document["verified_at"])

except Exception as e:
    print("Failed to save verification result:")
    print(type(e).__name__)
    print(str(e))