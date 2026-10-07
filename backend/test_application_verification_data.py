from application_service import get_application_verification_data


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"


try:
    application = get_application_verification_data(
        APPLICATION_ID
    )

    print("Application verification data retrieved!")

    print("\nApplication Number:", application["application_number"])
    print("Academic Score:", application["academic_score"])
    print("Previous Score:", application["previous_score"])
    print("Attendance:", application["attendance"])
    print("Annual Income:", application["annual_income"])
    print("Category:", application["application_category"])

except Exception as e:
    print("Failed to retrieve application data:")
    print(type(e).__name__)
    print(str(e))