from document_cross_checker import (
    compare_income_certificate_with_application
)


extracted_data = {
    "student_name": "Test Student",
    "annual_income": 800000.0
}

application_data = {
    "annual_income": 250000.0
}

result = compare_income_certificate_with_application(
    extracted_data,
    application_data
)

print("Income Certificate Comparison:")
print(result)