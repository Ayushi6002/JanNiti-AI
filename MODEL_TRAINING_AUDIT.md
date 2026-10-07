# MODEL TRAINING AUDIT: SCHOLARSHIP DECISION CLASSIFIER (v2)

**Audit Date:** October 2026  
**Audited Artifacts:**
- Model Binary: `model/model_v2.pkl`
- Feature Encoders: `model/encoders_v2.pkl`
- Training Script: `model/train_model_v2.py`
- Label Derivation Script: `data_real/fix_document_labels.py`
- Training Dataset: `data_real/JAN_NITI_FINAL_DECISION_DATASET_fixed.csv`

---

## 1. Executive Summary

This audit establishes the relationship between JanNiti AI's machine learning model (`model_v2.pkl`) and the authoritative rule-based eligibility engine.

A key observation was investigated: an applicant with an annual income exceeding the Need-Based Scholarship limit (e.g. ₹3,50,000 vs. the ₹3,00,000 ceiling) can receive a rule-based status of **NOT ELIGIBLE**, yet the ML classifier predicts **APPROVE** with high confidence (e.g., 82.30%).

**Key Audit Conclusion:**
- The ML model was trained on historical administrative decision records where academic performance accounted for 80% of the composite baseline score, and income only provided an optional boost rather than acting as a hard disqualifier.
- The deterministic scholarship rules configured in Supabase (`scholarship_rules`) are **authoritative** and govern actual eligibility.
- The ML classifier is an **advisory signal** reflecting historical decision trends and does **not** override deterministic rules.
- Rule-based `NOT_ELIGIBLE` status takes absolute precedence over ML `APPROVE`.

---

## 2. Training Dataset Specification

| Parameter | Specification |
|:---|:---|
| **Dataset Path** | `data_real/JAN_NITI_FINAL_DECISION_DATASET_fixed.csv` |
| **Record Count** | 10,000 records |
| **Target Variable** | `decision` (`APPROVE`, `NEEDS_HUMAN_REVIEW`, `REJECT`) |
| **Target Distribution** | `NEEDS_HUMAN_REVIEW`: 3,563 (35.63%)<br>`REJECT`: 3,552 (35.52%)<br>`APPROVE`: 2,885 (28.85%) |
| **Train / Test Split** | 80% Train (8,000), 20% Test (2,000), Stratified by target, `random_state=42` |

### Feature Columns (7 Features)
1. `academic_score` (Numeric, float 0–100)
2. `previous_score` (Numeric, float 0–100)
3. `attendance` (Numeric, float 0–100)
4. `annual_income` (Numeric, INR)
5. `application_category` (Categorical: General, OBC, SC, ST, EWS)
6. `scholarship_scheme` (Categorical: Merit Scholarship, Need-Based Scholarship, Category Support Scholarship)
7. `documents_verified` (Categorical: VERIFIED, INCOMPLETE, UNCERTAIN)

*Note:* `audit_group` and `application_id` are intentionally excluded from training features.

---

## 3. Model Architecture & Verified Performance

- **Estimator:** `RandomForestClassifier`
  - `n_estimators = 200`
  - `max_depth = 8`
  - `random_state = 42`
  - `class_weight = "balanced"`
- **Test Set Accuracy:** **88.1%** (0.881)
- **Macro F1-Score:** **0.88**

### Verified Feature Importances
| Feature | Importance | Share |
|:---|:---|:---|
| `academic_score` | 0.4408 | **44.08%** |
| `previous_score` | 0.3513 | **35.13%** |
| `documents_verified` | 0.0861 | **8.61%** |
| `attendance` | 0.0694 | **6.94%** |
| `annual_income` | 0.0299 | **2.99%** |
| `application_category` | 0.0125 | **1.25%** |
| `scholarship_scheme` | 0.0100 | **1.00%** |

Together, academic scores (`academic_score` + `previous_score`) account for **79.21%** of the model's total decision weight. `annual_income` accounts for only **2.99%**.

---

## 4. Root Cause of ML vs. Rule Disagreement

### Training Label Derivation Analysis (`data_real/fix_document_labels.py`)
In the label generation pipeline, labels were assigned via the following formula:

```python
base = 0.45 * academic_score + 0.35 * previous_score + 0.20 * attendance

if scheme == "Need-Based Scholarship":
    income_boost = max(0, (600000 - income) / 600000) * 8
    base += income_boost
```

Decisions were assigned based on thresholds:
- `base >= 79` & `documents == "VERIFIED"` &rarr; **`APPROVE`**
- `69 <= base < 79` &rarr; **`NEEDS_HUMAN_REVIEW`**
- `base < 69` &rarr; **`REJECT`**

### Finding:
1. **No Hard Income Ceiling in Training Data:**  
   The synthetic/historical generation used `income` solely as an *additive boost* (up to +8 points for low income), but never imposed a hard cap.
2. **Academic Dominance:**  
   An applicant with `academic_score = 95.0`, `previous_score = 92.0`, and `attendance = 90.0` achieves:
   $$\text{base} = 0.45(95) + 0.35(92) + 0.20(90) = 42.75 + 32.20 + 18.00 = 92.95$$
   Since $92.95 \gg 79.0$, this profile was labeled `APPROVE` regardless of whether their income was ₹3,50,000 or ₹1,00,000.
3. **Deterministic Rules Enforce Hard Limits:**  
   Current authoritative rules in Supabase specify:
   `ANNUAL_INCOME_CEILING`: $\text{annual\_income} \le 300,000$.  
   Any applicant earning $> ₹3,00,000$ strictly fails this rule.

---

## 5. Architectural Precedence & Advisory Policy

To ensure complete fairness, transparency, and regulatory compliance:

1. **Deterministic Rule Supremacy:**  
   The rule-based status (`ELIGIBLE`, `NEEDS_VERIFICATION`, `NOT_ELIGIBLE`) computed by `eligibility_service.py` is the single source of truth.
2. **Advisory Role of ML:**  
   The ML prediction is presented as an **"AI Model Assessment"** (historical classification signal), not as eligibility determination.
3. **Disagreement Handling:**  
   When the ML model predicts `APPROVE` but rule-based eligibility is `NOT_ELIGIBLE`, the system displays:
   > *"The AI model's prediction is an advisory signal based on historical training data. Current scholarship eligibility rules take precedence."*
4. **Confidence Formatting:**  
   Raw confidence is a probability $[0.0, 1.0]$. The interface displays it formatted as `XX.XX%` (e.g., `82.30%`, `72.60%`, `70.70%`) without double multiplication.
