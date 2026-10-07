from backend.appeal_service import review_appeal


appeal_id = "0c316058-a81d-4429-bb6d-9321c742e776"
admin_id = "3a0c2c7f-28bd-4c85-90a9-cc5ce5ed85c0"

try:
    result = review_appeal(
        appeal_id=appeal_id,
        reviewed_by=admin_id,
        status="RESOLVED",
        review_comment="Appeal reviewed successfully during workflow testing."
    )

    print("APPEAL REVIEWED SUCCESSFULLY")
    print(result)

except Exception as e:
    print("APPEAL REVIEW FAILED")
    print(e)