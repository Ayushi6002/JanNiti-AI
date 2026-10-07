from backend.supabase_client import supabase


USER_ID = "e5c9e479-dde4-4dd7-91ee-b25d721332a7"
NEW_PASSWORD = "JanNitiTest@2026"


try:
    response = supabase.auth.admin.update_user_by_id(
        USER_ID,
        {
            "password": NEW_PASSWORD
        }
    )

    print("PASSWORD RESET SUCCESSFULLY")
    print("User ID:", response.user.id)

except Exception as e:
    print("PASSWORD RESET FAILED")
    print(e)