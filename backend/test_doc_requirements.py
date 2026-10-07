from doc_verifier import get_required_documents


TEST_SCHEMES = [
    "Merit Scholarship",
    "Need Based Scholarship",
    "Category Based Scholarship"
]


try:
    for scheme in TEST_SCHEMES:
        documents = get_required_documents(scheme)

        print("--------------------------------")
        print("Scheme:", scheme)
        print("Required documents:", documents)

except Exception as e:
    print("Failed to fetch document requirements:")
    print(type(e).__name__)
    print(str(e))