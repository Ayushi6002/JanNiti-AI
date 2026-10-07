from document_extractor import extract_income_certificate_fields


text = """
JAN NITI AI TEST DOCUMENT

Student Name: Test Student
Annual Income: 250000
"""

result = extract_income_certificate_fields(text)

print("Extracted Income Certificate Data:")
print(result)