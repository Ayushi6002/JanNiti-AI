from document_service import upload_document


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

LOCAL_FILE = r"D:\AI_proj\Main\Fin\JanNiti-AI-V2\test_id_proof.pdf"

storage_path = upload_document(
    application_id=APPLICATION_ID,
    document_type="id_proof",
    file_path=LOCAL_FILE
)

print("ID proof uploaded!")
print("Storage path:", storage_path)