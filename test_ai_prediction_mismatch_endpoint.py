from backend.auth_service import login
import urllib.request
import urllib.error
import json


# Login as test admin
r = login(
    "jannititestadmin@gmail.com",
    "AdminTest@123"
)

token = r.session.access_token


# Fresh application JN-2026-000007
application_id = "bc6b750f-528a-44e3-9134-59d216e163d0"

# Intentionally use an AI prediction belonging to another application
ai_prediction_id = "8d4670eb-3364-473a-a971-53cfb8ce61a7"


body = {
    "application_id": application_id,
    "decision": "APPROVED",
    "reason": "Testing mismatched AI prediction protection",
    "ai_prediction_id": ai_prediction_id,
    "admin_comment": "This request should be blocked"
}


request = urllib.request.Request(
    "http://127.0.0.1:5000/admin/decision",
    data=json.dumps(body).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    },
    method="POST"
)


try:
    response = urllib.request.urlopen(request)

    print("HTTP STATUS:", response.status)
    print(response.read().decode())

except urllib.error.HTTPError as e:
    print("HTTP STATUS:", e.code)
    print(e.read().decode())