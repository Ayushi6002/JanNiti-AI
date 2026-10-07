from supabase_client import supabase


STORAGE_PATH = (
    "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d/"
    "marksheet/test_marksheet_mismatch.pdf"
)


try:
    response = (
        supabase
        .storage
        .from_("application-documents")
        .download(STORAGE_PATH)
    )

    print("Direct download completed!")
    print("Response type:", type(response))
    print("Response is None:", response is None)

    if response is not None:
        print("File size:", len(response), "bytes")

        if response.startswith(b"%PDF"):
            print("PDF signature verified.")

except Exception as e:
    print("Direct download failed:")
    print(type(e).__name__)
    print(str(e))