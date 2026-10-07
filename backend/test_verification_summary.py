from verification_service import generate_verification_summary


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"


summary = generate_verification_summary(APPLICATION_ID)


print("\n====================================")
print("APPLICATION VERIFICATION SUMMARY")
print("====================================")

print("Application ID:", summary["application_id"])
print("Scholarship Scheme:", summary["scheme_name"])

print("\nRequired Documents:")
for document in summary["required_documents"]:
    print("-", document)

print("\nDocument Status:")

for document_type, document_data in summary["documents"].items():
    print("\n-------------------------")
    print("Type:", document_type)
    print("Status:", document_data["status"])

    if "score" in document_data:
        print("Score:", document_data["score"])

print("\n====================================")
print("OVERALL STATUS:", summary["overall_status"])
print("====================================")

print("\nMissing Documents:")
print(summary["missing_documents"])

print("\nMismatched Documents:")
print(summary["mismatched_documents"])

print("\nNeeds Review Documents:")
print(summary["needs_review_documents"])