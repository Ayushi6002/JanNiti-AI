from document_service import update_document_storage


DOCUMENT_ID = "dff46273-ad07-4908-a41b-90ffd8df8c73"

STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "id_proof/test_id_proof.pdf"
)

response = update_document_storage(
    document_id=DOCUMENT_ID,
    file_name="test_id_proof.pdf",
    storage_path=STORAGE_PATH
)

print("ID proof document updated!")
print(response)