from application_service import get_application_by_id


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"
APPLICANT_ID = "e5c9e479-dde4-4dd7-91ee-b25d721332a7"


try:
    response = get_application_by_id(
        application_id=APPLICATION_ID,
        applicant_id=APPLICANT_ID
    )

    application = response.data

    print("Application retrieved successfully!")

    print("\nApplication Number:", application["application_number"])
    print("Status:", application["status"])

    print(
        "Scholarship:",
        application["scholarship_schemes"]["scheme_name"]
    )

    print(
        "Description:",
        application["scholarship_schemes"]["description"]
    )

except Exception as e:
    print("Failed to retrieve application:")
    print(type(e).__name__)
    print(str(e))