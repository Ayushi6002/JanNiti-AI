from supabase_client import supabase


FOLDER_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/marksheet"
)


try:
    response = (
        supabase
        .storage
        .from_("application-documents")
        .list(FOLDER_PATH)
    )

    print("Storage listing successful!")
    print("\nFiles found:")

    for item in response:
        print("-", item.get("name"))

except Exception as e:
    print("Storage listing failed:")
    print(type(e).__name__)
    print(str(e))