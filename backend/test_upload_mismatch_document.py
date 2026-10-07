from document_service import upload_document


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

FILE_PATH = (
    r"D:\AI_proj\Main\Fin\JanNiti-AI-V2"
    r"\test_marksheet_mismatch.pdf"
)


try:
    storage_path = upload_document(
        application_id=APPLICATION_ID,
        document_type="marksheet",
        file_path=FILE_PATH
    )

    print("Mismatch PDF uploaded successfully!")
    print("Storage path:", storage_path)

except Exception as e:
    print("Mismatch PDF upload failed:")
    print(type(e).__name__)
    print(str(e))