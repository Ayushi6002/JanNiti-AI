from document_extractor import extract_id_proof_fields


text = """
JAN NITI AI TEST DOCUMENT

Student Name: Jan Niti Test User
ID Type: Aadhaar
ID Number: 123456789012
"""

result = extract_id_proof_fields(text)

print("Extracted ID Proof Data:")
print(result)