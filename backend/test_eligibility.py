from eligibility_service import evaluate_application_eligibility


APPLICATION_ID = "b4d7cc1b-f40d-4387-94d4-42113ddbbb1d"

MERIT_SCHEME_ID = "91fc26f7-e746-4dae-862b-ddc1a8c3527c"


result = evaluate_application_eligibility(
    APPLICATION_ID,
    MERIT_SCHEME_ID
)


print("\n====================================")
print("ELIGIBILITY EVALUATION")
print("====================================")

print("Application ID:", result["application_id"])

print("\nEligible:", result["eligible"])

print(
    "Rules:",
    result["passed_count"],
    "passed /",
    result["total_rules"]
)

print("\nPASSED RULES:")

for rule in result["passed_rules"]:
    print("\n-------------------------")
    print("Rule:", rule["rule_name"])
    print("Status:", rule["status"])
    print("Message:", rule["message"])

print("\nFAILED RULES:")

for rule in result["failed_rules"]:
    print("\n-------------------------")
    print("Rule:", rule["rule_name"])
    print("Status:", rule["status"])
    print("Message:", rule["message"])

print("\n====================================")