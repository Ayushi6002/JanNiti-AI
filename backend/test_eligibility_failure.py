from eligibility_service import (
    get_scholarship_rules,
    evaluate_rule
)


MERIT_SCHEME_ID = "91fc26f7-e746-4dae-862b-ddc1a8c3527c"


# Deliberately failing test data.
test_application = {
    "academic_score": 65.0,
    "previous_score": 60.0,
    "attendance": 68.0,
    "annual_income": 900000.0
}


# Pretend that required documents are verified
# so we can specifically test the numerical rules.
test_verification_summary = {
    "required_documents": [
        "marksheet",
        "id_proof",
        "income_certificate"
    ],
    "documents": {
        "marksheet": {
            "status": "VERIFIED"
        },
        "id_proof": {
            "status": "VERIFIED"
        },
        "income_certificate": {
            "status": "VERIFIED"
        }
    }
}


rules = get_scholarship_rules(MERIT_SCHEME_ID)


print("\n====================================")
print("ELIGIBILITY FAILURE TEST")
print("====================================")

failed_count = 0

for rule in rules:

    result = evaluate_rule(
        rule,
        test_application,
        test_verification_summary
    )

    print("\n-------------------------")
    print("Rule:", rule["rule_name"])
    print("Status:", result["status"])
    print("Message:", result["message"])

    if result["status"] == "FAIL":
        failed_count += 1


print("\n====================================")
print("FAILED RULE COUNT:", failed_count)
print("====================================")