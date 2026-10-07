from supabase_client import supabase


USER_ID = "e5c9e479-dde4-4dd7-91ee-b25d721332a7"

response = (
    supabase
    .table("profiles")
    .select("*")
    .eq("id", USER_ID)
    .single()
    .execute()
)

print("Applicant Profile:")
print(response.data)