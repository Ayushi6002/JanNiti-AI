from supabase_client import supabase


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

response = (
    supabase
    .table("documents")
    .select(
        """
        id,
        document_type,
        file_name,
        verification_status,
        verification_score,
        extracted_data,
        mismatch_details,
        verified_at
        """
    )
    .eq("application_id", APPLICATION_ID)
    .order("created_at")
    .execute()
)

print("Application Documents:")

for document in response.data:
    print("\n-------------------------")
    print("ID:", document["id"])
    print("Type:", document["document_type"])
    print("Status:", document["verification_status"])
    print("Score:", document["verification_score"])
    print("Extracted Data:", document["extracted_data"])
    print("Mismatch Details:", document["mismatch_details"])