from auth_service import login

TEST_EMAIL = "ayushi1219jain@gmail.com"
TEST_PASSWORD = "TestPassword123!"

try:
    response = login(
        email=TEST_EMAIL,
        password=TEST_PASSWORD
    )

    print("Login successful!")

    if response.user:
        print("User ID:", response.user.id)
        print("Email:", response.user.email)

    if response.session:
        print("Access token received.")
        print("Login session created successfully.")
    else:
        print("No session returned.")

except Exception as e:
    print("Login failed:")
    print(type(e).__name__)
    print(str(e))