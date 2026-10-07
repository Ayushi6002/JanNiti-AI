from document_service import process_income_certificate_document


DOCUMENT_ID = "87677e9f-67c3-4cf6-9349-df4f246c7f76"

APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "income_certificate/test_income_certificate.pdf"
)


response = process_income_certificate_document(
    document_id=DOCUMENT_ID,
    application_id=APPLICATION_ID,
    storage_path=STORAGE_PATH
)


print("\nAutomatic income certificate verification completed!")

print("\nDocument:")
print("ID:", response.data[0]["id"])
print("Status:", response.data[0]["verification_status"])
print("Score:", response.data[0]["verification_score"])
print("Extracted Data:", response.data[0]["extracted_data"])
print("Mismatch Details:", response.data[0]["mismatch_details"])
print("Verified At:", response.data[0]["verified_at"])