from backend.supabase_client import supabase


USER_ID = "e5c9e479-dde4-4dd7-91ee-b25d721332a7"

try:
    response = supabase.auth.admin.update_user_by_id(
        USER_ID,
        {
            "email_confirm": True
        }
    )

    print("EMAIL CONFIRMED SUCCESSFULLY")
    print("User ID:", response.user.id)

except Exception as e:
    print("EMAIL CONFIRMATION FAILED")
    print(e)