from document_cross_checker import compare_id_proof_with_profile


extracted_data = {
    "student_name": "Jan Niti Test User",
    "id_type": "Aadhaar",
    "id_number": "123456789012"
}

profile_data = {
    "full_name": "Different Test User"
}

result = compare_id_proof_with_profile(
    extracted_data,
    profile_data
)

print("ID Proof Comparison:")
print(result)