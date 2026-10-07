from backend.decision_service import validate_ai_prediction


application_id = "bc6b750f-528a-44e3-9134-59d216e163d0"

# This prediction belongs to a DIFFERENT application:
ai_prediction_id = "8d4670eb-3364-473a-a971-53cfb8ce61a7"


try:
    result = validate_ai_prediction(
        application_id,
        ai_prediction_id
    )

    print("ERROR: mismatched prediction was accepted")
    print(result)

except ValueError as e:
    print("VALIDATION BLOCKED:", e)