from document_service import process_id_proof_document


DOCUMENT_ID = "dff46273-ad07-4908-a41b-90ffd8df8c73"

APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "id_proof/test_id_proof.pdf"
)


response = process_id_proof_document(
    document_id=DOCUMENT_ID,
    application_id=APPLICATION_ID,
    storage_path=STORAGE_PATH
)


print("\nAutomatic ID proof verification completed!")

print("\nDocument:")
print("ID:", response.data[0]["id"])
print("Status:", response.data[0]["verification_status"])
print("Score:", response.data[0]["verification_score"])
print("Extracted Data:", response.data[0]["extracted_data"])
print("Mismatch Details:", response.data[0]["mismatch_details"])
print("Verified At:", response.data[0]["verified_at"])