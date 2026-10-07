from document_service import create_document


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

response = create_document(
    application_id=APPLICATION_ID,
    document_type="id_proof",
    file_name="test_id_proof.pdf",
    storage_path=""
)

print("ID proof document record created!")
print(response)