"""
Fix Decision Labels - Document Verification Consistency
-----------------------------------------------------------
Problem found: in the original teammate CSV, `documents_verified` had almost
no relationship with `decision` (INCOMPLETE docs got approved at nearly the
same rate as VERIFIED docs). Since the project brief requires document status
to be a genuine "top reason" in explanations, this needs to be a real,
learnable signal - not noise.

This script re-derives the `decision` column using a transparent rule that
combines the existing numeric/categorical columns with document status,
while keeping every other column (IDs, scores, income, category, scheme,
audit_group) exactly as the teammate generated them.

Rule (transparent, so it's easy to defend to evaluators):
1. Compute an eligibility_score from academic_score, previous_score,
   attendance, and an income adjustment (need-based scheme + lower income
   gets a small boost, mirroring real scholarship logic).
2. Document status acts as a hard modifier on top of that score:
   - INCOMPLETE  -> can never result in APPROVE (capped at Needs Review/Reject)
   - UNCERTAIN   -> can never result in APPROVE at the top confidence tier
                    (capped at Needs Review if it would otherwise be Approve)
   - VERIFIED    -> normal thresholds apply
3. Small random noise (5%) added for realism, so the model has to learn a
   genuine boundary rather than memorize a clean rule.

`audit_group` is untouched by this relabeling logic - it must stay
uncorrelated with decision, since it is only meant for the fairness audit.
"""

import pandas as pd
import numpy as np

IN_PATH = "JAN_NITI_FINAL_DECISION_DATASET.csv"
OUT_PATH = "JAN_NITI_FINAL_DECISION_DATASET_fixed.csv"
SEED = 42


def compute_eligibility_score(row):
    academic = row["academic_score"]
    previous = row["previous_score"]
    attendance = row["attendance"]
    income = row["annual_income"]
    scheme = row["scholarship_scheme"]

    base = 0.45 * academic + 0.35 * previous + 0.20 * attendance

    # Need-based scheme: lower income gives a modest boost (need-based logic)
    if scheme == "Need-Based Scholarship":
        # income ranges roughly 60k - 1.8M in this dataset
        income_boost = max(0, (600000 - income) / 600000) * 8  # up to +8 points
        base += income_boost

    return base


def apply_document_rule(eligibility_score, doc_status, rng):
    # Base decision from eligibility score alone
    # Thresholds set near the 33rd/66th percentile of the score distribution
    # so that, before document penalties are applied, classes start balanced.
    if eligibility_score >= 79:
        raw_decision = "APPROVE"
    elif eligibility_score >= 69:
        raw_decision = "NEEDS_HUMAN_REVIEW"
    else:
        raw_decision = "REJECT"

    # Document status modifiers (hard safety rules)
    if doc_status == "INCOMPLETE":
        # Never approve with incomplete documents
        if raw_decision == "APPROVE":
            raw_decision = "NEEDS_HUMAN_REVIEW"
        # Push borderline reviews toward reject since docs are incomplete
        if raw_decision == "NEEDS_HUMAN_REVIEW" and rng.random() < 0.5:
            raw_decision = "REJECT"
    elif doc_status == "UNCERTAIN":
        # Uncertain docs cap the ceiling at Needs Review
        if raw_decision == "APPROVE":
            raw_decision = "NEEDS_HUMAN_REVIEW"

    # 5% label noise for realism
    if rng.random() < 0.05:
        raw_decision = rng.choice(["APPROVE", "NEEDS_HUMAN_REVIEW", "REJECT"])

    return raw_decision


def main():
    rng = np.random.default_rng(SEED)
    df = pd.read_csv(IN_PATH)

    df["eligibility_score_internal"] = df.apply(compute_eligibility_score, axis=1)
    df["decision"] = [
        apply_document_rule(score, doc, rng)
        for score, doc in zip(df["eligibility_score_internal"], df["documents_verified"])
    ]
    df = df.drop(columns=["eligibility_score_internal"])

    print("New decision distribution:")
    print(df["decision"].value_counts(normalize=True).round(3))

    print("\nDocuments_verified vs decision (should now show a real relationship):")
    print(pd.crosstab(df["documents_verified"], df["decision"], normalize="index").round(3))

    print("\nAudit_group vs decision (should remain balanced - fairness check):")
    print(pd.crosstab(df["audit_group"], df["decision"], normalize="index").round(3))

    df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved fixed dataset to {OUT_PATH}")


if __name__ == "__main__":
    main()
