from document_service import update_document_storage


DOCUMENT_ID = "8a4c7f7b-f243-40aa-9707-3bd57f1e4de8"

FILE_NAME = "test_marksheet.pdf"

STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "marksheet/test_marksheet.pdf"
)


try:
    response = update_document_storage(
        document_id=DOCUMENT_ID,
        file_name=FILE_NAME,
        storage_path=STORAGE_PATH
    )

    print("Document record updated successfully!")

    for document in response.data:
        print("\nDocument:")
        print("ID:", document["id"])
        print("File:", document["file_name"])
        print("Storage Path:", document["storage_path"])
        print("Status:", document["verification_status"])

except Exception as e:
    print("Document update failed:")
    print(type(e).__name__)
    print(str(e))