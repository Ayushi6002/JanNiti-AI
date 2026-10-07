import sys
from pathlib import Path

# Add project root only
root_dir = str(Path(__file__).resolve().parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.app import app
from backend.auth_service import login
from backend.supabase_client import supabase

def audit_pending():
    client = app.test_client()
    admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
    admin_token = admin_auth.session.access_token
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = client.get("/admin/applications", headers=admin_headers)
    assert res.status_code == 200
    all_apps = res.get_json().get("applications", [])
    print(f"Total applications returned by /admin/applications: {len(all_apps)}")

    # Also query Supabase directly to get raw table contents
    raw_apps_res = supabase.table("applications").select("*").execute()
    raw_apps_by_id = {a["id"]: a for a in (raw_apps_res.data or [])}

    raw_preds_res = supabase.table("ai_predictions").select("*").execute()
    # Group predictions by application_id
    raw_preds_by_id = {}
    for p in (raw_preds_res.data or []):
        aid = p["application_id"]
        if aid not in raw_preds_by_id:
            raw_preds_by_id[aid] = []
        raw_preds_by_id[aid].append(p)

    raw_decs_res = supabase.table("decisions").select("*").execute()
    raw_decs_by_id = {}
    for d in (raw_decs_res.data or []):
        aid = d["application_id"]
        if aid not in raw_decs_by_id:
            raw_decs_by_id[aid] = []
        raw_decs_by_id[aid].append(d)

    raw_appeals_res = supabase.table("appeals").select("*").execute()
    raw_appeals_by_id = {}
    for ap in (raw_appeals_res.data or []):
        aid = ap["application_id"]
        if aid not in raw_appeals_by_id:
            raw_appeals_by_id[aid] = []
        raw_appeals_by_id[aid].append(ap)

    # Let's inspect how frontend classifyApplication(app) categorizes them
    def classify_app_frontend(app):
        status_upper = (app.get("status") or "").upper()
        appeal_obj = app.get("appeal") or {}
        appeal_status_upper = (appeal_obj.get("status") or "").upper()
        has_active_appeal = status_upper == "APPEAL_PENDING" or appeal_status_upper == "PENDING"

        if has_active_appeal:
            orig_dec = (
                app.get("admin_final_decision")
                or app.get("final_decision")
                or (app.get("decision") or {}).get("decision")
                or "REJECTED"
            ).upper()
            return {"top": "APPEAL_PENDING", "sub": "APPEAL_PENDING", "label": "Appeal Pending"}

        human_dec = (
            app.get("admin_final_decision")
            or app.get("final_decision")
            or (app.get("decision") or {}).get("decision")
            or ""
        ).upper()

        if human_dec in ("APPROVED", "APPROVE"):
            return {"top": "DECISION_MADE", "sub": "APPROVED", "label": "Approved"}
        if human_dec in ("REJECTED", "REJECT"):
            return {"top": "DECISION_MADE", "sub": "REJECTED", "label": "Rejected"}

        # Pending decisions:
        pred = (
            app.get("model_decision")
            or (app.get("ai_prediction") or {}).get("prediction")
            or app.get("prediction")
            or ""
        ).upper()

        raw_conf = None
        if isinstance(app.get("confidence"), (int, float)):
            raw_conf = app["confidence"]
        elif app.get("ai_prediction") and isinstance(app["ai_prediction"].get("probability"), (int, float)):
            raw_conf = app["ai_prediction"]["probability"]

        conf = 0
        if raw_conf is not None:
            try:
                val = float(raw_conf)
                conf = round(val * 100) if val <= 1.0 else round(val)
            except Exception:
                conf = 0

        if pred == "APPROVE" and conf >= 70:
            return {"top": "PENDING_DECISIONS", "sub": "LIKELY_APPROVED", "pred": pred, "conf": conf, "raw_conf": raw_conf}
        elif pred == "REJECT" and conf >= 70:
            return {"top": "PENDING_DECISIONS", "sub": "LIKELY_REJECTED", "pred": pred, "conf": conf, "raw_conf": raw_conf}
        else:
            return {"top": "PENDING_DECISIONS", "sub": "REQUIRES_REVIEW", "pred": pred, "conf": conf, "raw_conf": raw_conf}

    # Separate into top buckets
    bucket_counts = {"DECISION_MADE": 0, "PENDING_DECISIONS": 0, "APPEAL_PENDING": 0}
    pending_sub_counts = {"LIKELY_APPROVED": 0, "LIKELY_REJECTED": 0, "REQUIRES_REVIEW": 0}

    pending_apps = []

    for a in all_apps:
        c = classify_app_frontend(a)
        bucket_counts[c["top"]] += 1
        if c["top"] == "PENDING_DECISIONS":
            pending_sub_counts[c["sub"]] += 1
            pending_apps.append((a, c))

    print(f"\nTop Buckets across all {len(all_apps)} applications:")
    print(f"  Decision Made: {bucket_counts['DECISION_MADE']}")
    print(f"  Pending Decisions: {bucket_counts['PENDING_DECISIONS']}")
    print(f"  Appeal Pending: {bucket_counts['APPEAL_PENDING']}")

    print(f"\nPending Decisions Sub-Buckets ({len(pending_apps)} total):")
    for sub, cnt in pending_sub_counts.items():
        print(f"  {sub}: {cnt}")

    # Now let's analyze the REQUIRES_REVIEW applications specifically
    requires_review = [item for item in pending_apps if item[1]["sub"] == "REQUIRES_REVIEW"]
    print(f"\nTotal in REQUIRES_REVIEW: {len(requires_review)}")

    # Audit categories A to I
    # A. APPROVE prediction with confidence >= 70 (should be 0, else they'd be in LIKELY_APPROVED)
    # B. APPROVE prediction with confidence < 70
    # C. REJECT prediction with confidence >= 70 (should be 0, else they'd be in LIKELY_REJECTED)
    # D. REJECT prediction with confidence < 70
    # E. NEEDS_HUMAN_REVIEW prediction
    # F. Missing AI prediction
    # G. Confidence = 0
    # H. Invalid/null/non-numeric confidence
    # I. Any other classification reason

    breakdown = {
        "A_approve_gte_70": [],
        "B_approve_lt_70": [],
        "C_reject_gte_70": [],
        "D_reject_lt_70": [],
        "E_needs_human_review": [],
        "F_missing_prediction": [],
        "G_confidence_zero": [],
        "H_invalid_null_confidence": [],
        "I_other": [],
    }

    # Detailed inspection of each of the review applications
    for app_item, c_info in requires_review:
        aid = app_item["id"]
        pred = c_info["pred"]
        conf = c_info["conf"]
        raw_conf = c_info["raw_conf"]

        # Check raw predictions in DB for this aid
        db_preds = raw_preds_by_id.get(aid, [])
        db_app = raw_apps_by_id.get(aid, {})

        # Categorize
        if pred == "APPROVE" and conf >= 70:
            breakdown["A_approve_gte_70"].append(app_item)
        elif pred == "APPROVE" and 0 < conf < 70:
            breakdown["B_approve_lt_70"].append(app_item)
        elif pred == "REJECT" and conf >= 70:
            breakdown["C_reject_gte_70"].append(app_item)
        elif pred == "REJECT" and 0 < conf < 70:
            breakdown["D_reject_lt_70"].append(app_item)
        elif pred == "NEEDS_HUMAN_REVIEW" and conf > 0:
            breakdown["E_needs_human_review"].append(app_item)
        elif not pred or pred == "":
            breakdown["F_missing_prediction"].append(app_item)
        elif conf == 0:
            breakdown["G_confidence_zero"].append((app_item, pred, raw_conf, db_preds))
        else:
            breakdown["I_other"].append((app_item, pred, conf, raw_conf))

    print("\n--- Breakdown of REQUIRES_REVIEW Applications ---")
    print(f"A. APPROVE >= 70%: {len(breakdown['A_approve_gte_70'])}")
    print(f"B. APPROVE < 70%: {len(breakdown['B_approve_lt_70'])}")
    print(f"C. REJECT >= 70%: {len(breakdown['C_reject_gte_70'])}")
    print(f"D. REJECT < 70%: {len(breakdown['D_reject_lt_70'])}")
    print(f"E. NEEDS_HUMAN_REVIEW (with conf > 0): {len(breakdown['E_needs_human_review'])}")
    print(f"F. Missing AI prediction: {len(breakdown['F_missing_prediction'])}")
    print(f"G. Confidence = 0%: {len(breakdown['G_confidence_zero'])}")
    print(f"H. Invalid / null confidence: {len(breakdown['H_invalid_null_confidence'])}")
    print(f"I. Other: {len(breakdown['I_other'])}")

    total_sum = sum(len(v) for v in breakdown.values())
    print(f"\nSum of breakdown items: {total_sum} (Expected: {len(requires_review)})")

    # Let's inspect the 0% confidence applications in depth
    zero_conf_items = breakdown["G_confidence_zero"]
    print(f"\n--- Investigating the {len(zero_conf_items)} Confidence = 0% Applications ---")
    
    # Sub-classify what the 0% items actually have in DB
    zero_preds_summary = {}
    has_db_pred_count = 0
    no_db_pred_count = 0
    
    sample_zero_apps = []
    for item in zero_conf_items:
        app_obj, pred_str, raw_conf_val, db_pred_list = item
        aid = app_obj["id"]
        
        # Check if ai_prediction exists in DB table
        if len(db_pred_list) > 0:
            has_db_pred_count += 1
            latest_db_p = db_pred_list[-1]
            p_val = latest_db_p.get("prediction")
            prob_val = latest_db_p.get("probability")
            key = f"DB pred={p_val}, prob={prob_val}"
        else:
            no_db_pred_count += 1
            key = f"NO ai_predictions record in DB (app.status={app_obj.get('status')})"

        zero_preds_summary[key] = zero_preds_summary.get(key, 0) + 1
        if len(sample_zero_apps) < 10:
            sample_zero_apps.append({
                "app_id": aid,
                "app_number": app_obj.get("application_number"),
                "status": app_obj.get("status"),
                "app_model_decision": app_obj.get("model_decision"),
                "app_confidence": app_obj.get("confidence"),
                "app_ai_pred_obj": app_obj.get("ai_prediction"),
                "db_preds_count": len(db_pred_list),
                "db_preds": db_pred_list,
            })

    print(f"Has ai_predictions record in DB: {has_db_pred_count}")
    print(f"No ai_predictions record in DB: {no_db_pred_count}")
    print("\nBreakdown of 0% confidence records:")
    for k, v in zero_preds_summary.items():
        print(f"  [{v}] {k}")

    print("\nSamples of 0% confidence applications:")
    for s in sample_zero_apps[:5]:
        print(s)

if __name__ == "__main__":
    audit_pending()
