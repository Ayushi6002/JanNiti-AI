from supabase_client import supabase


response = (
    supabase
    .table("scholarship_schemes")
    .select(
        "scheme_code, scheme_name, required_documents"
    )
    .execute()
)

print("Required documents:\n")

for scheme in response.data:
    print("--------------------------------")
    print("Scheme:", scheme["scheme_name"])
    print("Code:", scheme["scheme_code"])
    print("Required documents:")
    print(scheme["required_documents"])