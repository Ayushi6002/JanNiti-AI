from pathlib import Path
from doc_verifier import extract_text_from_pdf


FILE_PATH = Path(
    r"D:\AI_proj\Main\Fin\JanNiti-AI-V2\test_marksheet.pdf"
)


try:
    file_bytes = FILE_PATH.read_bytes()

    text = extract_text_from_pdf(file_bytes)

    print("PDF text extraction successful!")
    print("\nExtracted text:")
    print("-------------------------")
    print(text)
    print("-------------------------")

except Exception as e:
    print("PDF extraction failed:")
    print(type(e).__name__)
    print(str(e))