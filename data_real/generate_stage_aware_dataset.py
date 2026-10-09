"""
generate_stage_aware_dataset.py
--------------------------------
Stage 2D.1 Remediated Training Dataset Generator for Jan Niti AI.

Constructs a realistic, stage-aware scholarship applicant dataset (12,000 records)
that adheres to canonical Category Semantics and Stage 2A academic profile data contracts:

CANONICAL CATEGORIES:
- General (40% / 4,800 records)
- OBC (27% / 3,240 records)
- SC (15% / 1,800 records)
- ST (8% / 960 records)
- EWS (10% / 1,200 records)

IMPORTANT METHODOLOGY & LIMITATIONS DISCLOSURE:
1. Synthetic/Engineered: This dataset is entirely synthetic and engineered for algorithm
   development, feature schema validation, missing-value modeling, and safety testing.
2. Category Distribution: The category proportions are engineered synthetic weights
   intended to provide adequate statistical representation for all constitutional groups.
   THEY DO NOT CLAIM TO REPRESENT THE EMPIRICAL CENSUS OR REAL INDIAN SCHOLARSHIP POPULATIONS.
3. Category-Neutral Decision Rules: Approval outcomes are derived purely from academic
   merit, attendance, income constraints, document status, and noise. NO ARTIFICIAL
   CATEGORY ADVANTAGES OR PENALTIES ARE INJECTED INTO THE TARGET DECISION LABELS.

Cohorts:
1. FIRST_YEAR (~25% / 3,000 records)
   - qualification_type: HSC_12TH (75%), DIPLOMA (20%), OTHER (5%)
   - qualifying_score: Real pre-college qualifying score (e.g. 12th/Diploma %)
   - ssc_score: Secondary school percentage (correlated with qualifying_score)
   - academic_score = qualifying_score (canonical primary academic merit)
   - previous_score = ssc_score (canonical secondary academic merit)
   - attendance = NaN (strictly missing/null, college attendance does NOT exist)
   - is_attendance_applicable = 0

2. SECOND_YEAR (~25% / 3,000 records)
   - first_year_score: First year college aggregate percentage
   - qualifying_score: 12th/Diploma score prior to college
   - academic_score = first_year_score
   - previous_score = qualifying_score
   - attendance = first_year_college_attendance (45 - 100%)
   - is_attendance_applicable = 1
   - qualification_type = None

3. THIRD_YEAR (~20% / 2,400 records)
   - second_year_score: Second year college aggregate percentage
   - first_year_score: First year college percentage
   - academic_score = second_year_score
   - previous_score = first_year_score
   - attendance = second_year_college_attendance (45 - 100%)
   - is_attendance_applicable = 1
   - qualification_type = None

4. FOURTH_YEAR (~15% / 1,800 records)
   - third_year_score: Third year college aggregate percentage
   - second_year_score: Second year college percentage
   - academic_score = third_year_score
   - previous_score = second_year_score
   - attendance = third_year_college_attendance (45 - 100%)
   - is_attendance_applicable = 1
   - qualification_type = None

5. POSTGRADUATE (~15% / 1,800 records)
   - ug_score: Final undergraduate degree aggregate percentage
   - previous_score: Prior qualifying examination / 12th percentage
   - academic_score = ug_score
   - previous_score = previous_score
   - attendance = undergraduate_final_attendance (45 - 100%)
   - is_attendance_applicable = 1
   - qualification_type = None
"""

import numpy as np
import pandas as pd

SEED = 42
TOTAL_RECORDS = 12000
OUT_PATH = "data_real/jan_niti_stage_aware_dataset_remediated.csv"


def generate_dataset():
    rng = np.random.default_rng(SEED)

    # Cohort sizing
    cohort_sizes = {
        "FIRST_YEAR": 3000,     # 25%
        "SECOND_YEAR": 3000,    # 25%
        "THIRD_YEAR": 2400,     # 20%
        "FOURTH_YEAR": 1800,    # 15%
        "POSTGRADUATE": 1800,   # 15%
    }

    records = []
    app_counter = 200000

    # Canonical Social Categories: General, OBC, SC, ST, EWS
    # Distinct constitutional reservation groups without conflation
    categories = ["General", "OBC", "SC", "ST", "EWS"]
    cat_weights = [0.40, 0.27, 0.15, 0.08, 0.10]

    schemes = ["Merit Scholarship", "Need-Based Scholarship", "Academic Support Scholarship"]
    scheme_weights = [0.38, 0.37, 0.25]

    doc_statuses = ["VERIFIED", "INCOMPLETE", "UNCERTAIN"]
    doc_weights = [0.85, 0.10, 0.05]

    for stage, count in cohort_sizes.items():
        for _ in range(count):
            app_counter += 1
            app_id = f"APP{app_counter}"

            # Common background attributes
            category = rng.choice(categories, p=cat_weights)
            scheme = rng.choice(schemes, p=scheme_weights)
            docs = rng.choice(doc_statuses, p=doc_weights)

            # Income distribution matching historical (log-normal distributed ~60k to 1.8M)
            income_log = rng.normal(loc=12.9, scale=0.6)
            income = float(np.clip(np.exp(income_log), 60000, 1800000))
            income = round(income, -2)

            qualification_type = None
            qualifying_score = None
            ssc_score = None
            first_year_score = None
            second_year_score = None
            third_year_score = None
            ug_score = None
            attendance = None
            is_attendance_applicable = 1

            if stage == "FIRST_YEAR":
                q_type = rng.choice(["HSC_12TH", "DIPLOMA", "OTHER"], p=[0.75, 0.20, 0.05])
                qualification_type = q_type

                # Qualifying score (12th / Diploma percentage, ~45% to 98%)
                q_score = rng.normal(loc=74.0, scale=12.5)
                q_score = float(np.clip(q_score, 40.0, 98.0))
                qualifying_score = round(q_score, 1)

                # SSC score (correlated with qualifying score)
                ssc = qualifying_score * 0.7 + rng.normal(loc=22.0, scale=7.0)
                ssc = float(np.clip(ssc, 40.0, 99.0))
                ssc_score = round(ssc, 1)

                academic_score = qualifying_score
                previous_score = ssc_score
                attendance = np.nan
                is_attendance_applicable = 0

            elif stage == "SECOND_YEAR":
                # FY score
                fy = rng.normal(loc=71.5, scale=13.0)
                fy = float(np.clip(fy, 40.0, 98.0))
                first_year_score = round(fy, 1)

                # Qualifying score (12th/Diploma)
                qs = first_year_score * 0.6 + rng.normal(loc=30.0, scale=8.0)
                qs = float(np.clip(qs, 40.0, 98.0))
                qualifying_score = round(qs, 1)

                att = rng.normal(loc=78.5, scale=11.5)
                att = float(np.clip(att, 45.0, 100.0))
                attendance = round(att, 1)

                academic_score = first_year_score
                previous_score = qualifying_score

            elif stage == "THIRD_YEAR":
                # SY score
                sy = rng.normal(loc=72.0, scale=12.8)
                sy = float(np.clip(sy, 40.0, 98.0))
                second_year_score = round(sy, 1)

                fy = second_year_score * 0.7 + rng.normal(loc=22.0, scale=7.0)
                fy = float(np.clip(fy, 40.0, 98.0))
                first_year_score = round(fy, 1)

                att = rng.normal(loc=78.2, scale=11.6)
                att = float(np.clip(att, 45.0, 100.0))
                attendance = round(att, 1)

                academic_score = second_year_score
                previous_score = first_year_score

            elif stage == "FOURTH_YEAR":
                # TY score
                ty = rng.normal(loc=73.0, scale=12.5)
                ty = float(np.clip(ty, 40.0, 98.0))
                third_year_score = round(ty, 1)

                sy = third_year_score * 0.75 + rng.normal(loc=18.0, scale=6.5)
                sy = float(np.clip(sy, 40.0, 98.0))
                second_year_score = round(sy, 1)

                att = rng.normal(loc=79.0, scale=11.2)
                att = float(np.clip(att, 45.0, 100.0))
                attendance = round(att, 1)

                academic_score = third_year_score
                previous_score = second_year_score

            elif stage == "POSTGRADUATE":
                # UG score
                ug = rng.normal(loc=72.5, scale=12.2)
                ug = float(np.clip(ug, 40.0, 98.0))
                ug_score = round(ug, 1)

                prev = ug_score * 0.7 + rng.normal(loc=23.0, scale=7.0)
                prev = float(np.clip(prev, 40.0, 98.0))
                prev = round(prev, 1)

                att = rng.normal(loc=78.0, scale=11.5)
                att = float(np.clip(att, 45.0, 100.0))
                attendance = round(att, 1)

                academic_score = ug_score
                previous_score = prev

            # Decision calculation
            if stage == "FIRST_YEAR":
                # Attendance waived: re-weighted to 60% qualifying + 40% ssc
                base = 0.60 * academic_score + 0.40 * previous_score
            else:
                # Continuing student: 45% academic + 35% previous + 20% attendance
                base = 0.45 * academic_score + 0.35 * previous_score + 0.20 * attendance

            if scheme == "Need-Based Scholarship":
                income_boost = max(0.0, (600000.0 - income) / 600000.0) * 8.0
                base += income_boost

            # Apply document safety rules & realistic 5% noise
            if base >= 79.0:
                raw_decision = "APPROVE"
            elif base >= 69.0:
                raw_decision = "NEEDS_HUMAN_REVIEW"
            else:
                raw_decision = "REJECT"

            if docs == "INCOMPLETE":
                if raw_decision == "APPROVE":
                    raw_decision = "NEEDS_HUMAN_REVIEW"
                if raw_decision == "NEEDS_HUMAN_REVIEW" and rng.random() < 0.5:
                    raw_decision = "REJECT"
            elif docs == "UNCERTAIN":
                if raw_decision == "APPROVE":
                    raw_decision = "NEEDS_HUMAN_REVIEW"

            if rng.random() < 0.05:
                raw_decision = rng.choice(["APPROVE", "NEEDS_HUMAN_REVIEW", "REJECT"])

            records.append({
                "application_id": app_id,
                "academic_stage": stage,
                "qualification_type": qualification_type if qualification_type else "NOT_APPLICABLE",
                "academic_score": academic_score,
                "previous_score": previous_score,
                "attendance": attendance,
                "is_attendance_applicable": is_attendance_applicable,
                "annual_income": income,
                "application_category": category,
                "scholarship_scheme": scheme,
                "documents_verified": docs,
                "qualifying_score": qualifying_score,
                "ssc_score": ssc_score,
                "first_year_score": first_year_score,
                "second_year_score": second_year_score,
                "third_year_score": third_year_score,
                "ug_score": ug_score,
                "decision": raw_decision,
            })

    df = pd.DataFrame(records)
    df.to_csv(OUT_PATH, index=False)
    print(f"Generated {len(df)} records in {OUT_PATH}")
    print("\nAcademic stage distribution:")
    print(df["academic_stage"].value_counts(normalize=True).round(3))
    print("\nDecision distribution:")
    print(df["decision"].value_counts(normalize=True).round(3))
    print("\nMissing attendance count by stage:")
    print(df.groupby("academic_stage")["attendance"].apply(lambda s: s.isna().sum()))


if __name__ == "__main__":
    generate_dataset()
