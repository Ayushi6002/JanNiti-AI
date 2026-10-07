from pathlib import Path

from doc_verifier import extract_text_from_pdf
from document_extractor import extract_marksheet_fields


FILE_PATH = Path(
    r"D:\AI_proj\Main\Fin\JanNiti-AI-V2\test_marksheet.pdf"
)


try:
    file_bytes = FILE_PATH.read_bytes()

    text = extract_text_from_pdf(file_bytes)

    extracted = extract_marksheet_fields(text)

    print("Structured extraction successful!")

    print("\nExtracted fields:")
    print("-------------------------")
    print("Student Name:", extracted["student_name"])
    print("Academic Score:", extracted["academic_score"])
    print("Previous Score:", extracted["previous_score"])
    print("-------------------------")

except Exception as e:
    print("Structured extraction failed:")
    print(type(e).__name__)
    print(str(e))