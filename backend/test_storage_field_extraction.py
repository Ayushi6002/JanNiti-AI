from document_service import download_document
from doc_verifier import extract_text_from_pdf
from document_extractor import extract_marksheet_fields


STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "marksheet/test_marksheet.pdf"
)


try:
    # 1. Download the PDF from private Storage
    file_bytes = download_document(STORAGE_PATH)

    print("File downloaded successfully!")

    # 2. Extract text
    extracted_text = extract_text_from_pdf(file_bytes)

    print("\nText extracted successfully!")

    # 3. Extract structured fields
    extracted_data = extract_marksheet_fields(extracted_text)

    print("\nStructured fields extracted!")
    print("-------------------------")
    print("Student Name:", extracted_data["student_name"])
    print("Academic Score:", extracted_data["academic_score"])
    print("Previous Score:", extracted_data["previous_score"])
    print("-------------------------")

except Exception as e:
    print("Storage field extraction failed:")
    print(type(e).__name__)
    print(str(e))