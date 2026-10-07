from document_service import download_document
from doc_verifier import extract_text_from_pdf


STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "marksheet/test_marksheet.pdf"
)


try:
    # Step 1: Download from private Supabase Storage
    file_bytes = download_document(STORAGE_PATH)

    print("File downloaded from Supabase Storage!")
    print("File size:", len(file_bytes), "bytes")

    # Step 2: Extract text from downloaded bytes
    extracted_text = extract_text_from_pdf(file_bytes)

    print("\nText extraction successful!")
    print("-------------------------")
    print(extracted_text)
    print("-------------------------")

except Exception as e:
    print("Storage extraction failed:")
    print(type(e).__name__)
    print(str(e))