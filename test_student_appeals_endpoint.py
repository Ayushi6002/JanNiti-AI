from backend.auth_service import login
import urllib.request
import urllib.error


r = login(
    "ayushi1219jain@gmail.com",
    "JanNitiTest@2026"
)

token = r.session.access_token

request = urllib.request.Request(
    "http://127.0.0.1:5000/student/appeals",
    headers={
        "Authorization": f"Bearer {token}"
    },
    method="GET"
)

try:
    response = urllib.request.urlopen(request)

    print("HTTP STATUS:", response.status)
    print(response.read().decode())

except urllib.error.HTTPError as e:
    print("HTTP STATUS:", e.code)
    print(e.read().decode())