from document_service import process_marksheet_document


DOCUMENT_ID = "8a4c7f7b-f243-40aa-9707-3bd57f1e4de8"

APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "marksheet/test_marksheet.pdf"
)


try:
    response = process_marksheet_document(
        document_id="fd41af05-0ab6-4fd5-9192-dc6da8582e73",
        application_id="b4d7cc1b-f40d-4387-94d4-42113ddbbb1d",
        storage_path="b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/marksheet/test_marksheet_mismatch.pdf"
    )

    print("Automatic document verification completed!")

    for document in response.data:
        print("\nDocument:")
        print("ID:", document["id"])
        print("Status:", document["verification_status"])
        print("Score:", document["verification_score"])
        print("Extracted Data:", document["extracted_data"])
        print("Mismatch Details:", document["mismatch_details"])
        print("Verified At:", document["verified_at"])

except Exception as e:
    print("Automatic document verification failed:")
    print(type(e).__name__)
    print(str(e))