from document_cross_checker import compare_marksheet_with_application


extracted_data = {
    "student_name": "Test Student",
    "academic_score": 72.0,
    "previous_score": 84.0
}


application_data = {
    "academic_score": 88.5,
    "previous_score": 84.0
}


try:
    result = compare_marksheet_with_application(
        extracted_data,
        application_data
    )

    print("Cross-check completed!")

    print("\nOverall status:")
    print(result["overall_status"])

    print("\nField results:")

    for field, details in result["fields"].items():
        print(
            f"{field}: "
            f"{details['status']} "
            f"(document={details['document_value']}, "
            f"application={details['application_value']})"
        )

except Exception as e:
    print("Cross-check failed:")
    print(type(e).__name__)
    print(str(e))