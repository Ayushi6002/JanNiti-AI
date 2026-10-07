from document_service import download_document


STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "marksheet/test_marksheet_mismatch.pdf"
)


try:
    file_bytes = download_document(STORAGE_PATH)

    print("Mismatch PDF exists in Supabase Storage!")
    print("File size:", len(file_bytes), "bytes")

    if file_bytes.startswith(b"%PDF"):
        print("PDF signature verified.")

except Exception as e:
    print("Mismatch PDF download failed:")
    print(type(e).__name__)
    print(str(e))