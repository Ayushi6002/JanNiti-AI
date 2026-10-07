from document_service import upload_document


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

LOCAL_FILE = r"D:\AI_proj\Main\Fin\JanNiti-AI-V2\test_income_certificate.pdf"

storage_path = upload_document(
    application_id=APPLICATION_ID,
    document_type="income_certificate",
    file_path=LOCAL_FILE
)

print("Income certificate uploaded!")
print("Storage path:", storage_path)