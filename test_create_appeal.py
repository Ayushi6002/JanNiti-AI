from backend.appeal_service import create_appeal


application_id = "d0d30ded-8ca0-46b2-a45d-0eb250a9388e"
applicant_id = "e5c9e479-dde4-4dd7-91ee-b25d721332a7"

try:
    result = create_appeal(
        application_id=application_id,
        applicant_id=applicant_id,
        reason="Testing duplicate pending appeal protection."
    )

    print("APPEAL CREATED SUCCESSFULLY")
    print(result)

except Exception as e:
    print("APPEAL CREATION FAILED")
    print(e)