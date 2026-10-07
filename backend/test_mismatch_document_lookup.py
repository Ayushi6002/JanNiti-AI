from supabase_client import supabase


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"


try:
    response = (
        supabase
        .table("documents")
        .select(
            "id, application_id, document_type, file_name, "
            "storage_path, verification_status"
        )
        .eq("application_id", APPLICATION_ID)
        .eq("file_name", "test_marksheet_mismatch.pdf")
        .execute()
    )

    print("Lookup successful!")
    print("Matching records:", len(response.data))

    for document in response.data:
        print("\nDocument:")
        print("ID:", document["id"])
        print("Application ID:", document["application_id"])
        print("Type:", document["document_type"])
        print("File:", document["file_name"])
        print("Storage Path:", document["storage_path"])
        print("Status:", document["verification_status"])

except Exception as e:
    print("Lookup failed:")
    print(type(e).__name__)
    print(str(e))