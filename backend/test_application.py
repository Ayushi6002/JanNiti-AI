from application_service import create_application


APPLICANT_ID = "e5c9e479-dde4-4dd7-91ee-b25d721332a7"

MERIT_SCHEME_ID = "91fc26f7-e746-4dae-862b-ddc1a8c3527c"


try:
    response = create_application(
        applicant_id=APPLICANT_ID,
        scholarship_scheme_id=MERIT_SCHEME_ID,
        academic_score=88.5,
        previous_score=84.0,
        attendance=92.0,
        annual_income=250000,
        application_category="GENERAL"
    )

    print("Application created successfully!")

    for application in response.data:
        print("\nApplication:")
        print("ID:", application["id"])
        print("Application Number:", application["application_number"])
        print("Status:", application["status"])

except Exception as e:
    print("Application creation failed:")
    print(type(e).__name__)
    print(str(e))