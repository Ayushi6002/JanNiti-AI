from document_service import update_document_storage


DOCUMENT_ID = "87677e9f-67c3-4cf6-9349-df4f246c7f76"

STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "income_certificate/test_income_certificate.pdf"
)

response = update_document_storage(
    document_id=DOCUMENT_ID,
    file_name="test_income_certificate.pdf",
    storage_path=STORAGE_PATH
)

print("Income certificate document updated!")
print(response)