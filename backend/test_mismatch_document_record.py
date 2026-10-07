from document_service import create_document


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"


try:
    response = create_document(
        application_id=APPLICATION_ID,
        document_type="marksheet",
        file_name="test_marksheet_mismatch.pdf",
        storage_path=(
            "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
            "marksheet/test_marksheet_mismatch.pdf"
        )
    )

    print("Mismatch document record created!")

    for document in response.data:
        print("\nDocument:")
        print("ID:", document["id"])
        print("Application ID:", document["application_id"])
        print("Type:", document["document_type"])
        print("File:", document["file_name"])
        print("Storage Path:", document["storage_path"])
        print("Status:", document["verification_status"])

except Exception as e:
    print("Failed to create mismatch document record:")
    print(type(e).__name__)
    print(str(e))