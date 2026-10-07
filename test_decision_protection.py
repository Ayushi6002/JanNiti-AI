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


# Try to change an already-approved application
body = {
    "application_id": "d0d30ded-8ca0-46b2-a45d-0eb250a9388e",
    "decision": "REJECTED",
    "reason": "Testing finalized application protection",
    "admin_comment": "This should be blocked"
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