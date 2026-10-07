from document_service import create_document


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

response = create_document(
    application_id=APPLICATION_ID,
    document_type="income_certificate",
    file_name="test_income_certificate.pdf",
    storage_path=""
)

print("Income certificate document record created!")

print(response)