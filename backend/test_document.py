from document_service import create_document


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"


try:
    response = create_document(
        application_id=APPLICATION_ID,
        document_type="marksheet",
        file_name="marksheet_test.pdf",
        storage_path="applications/b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/marksheet_test.pdf"
    )

    print("Document record created successfully!")

    for document in response.data:
        print("\nDocument:")
        print("ID:", document["id"])
        print("Application ID:", document["application_id"])
        print("Type:", document["document_type"])
        print("File:", document["file_name"])
        print("Storage Path:", document["storage_path"])
        print("Verification Status:", document["verification_status"])

except Exception as e:
    print("Document creation failed:")
    print(type(e).__name__)
    print(str(e))