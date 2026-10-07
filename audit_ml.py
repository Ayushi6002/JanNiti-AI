import sys
from pathlib import Path

# Add project root only
root_dir = str(Path(__file__).resolve().parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.supabase_client import supabase

def audit():
    res = supabase.table('applications').select('id, status, applicant_id').execute()
    apps = res.data or []
    print(f"Total applications in DB: {len(apps)}")

    preds_res = supabase.table('ai_predictions').select('application_id, prediction, probability').execute()
    preds_by_app = {}
    for p in (preds_res.data or []):
        preds_by_app[p['application_id']] = p

    decs_res = supabase.table('decisions').select('application_id, decision').execute()
    decs_by_app = {}
    for d in (decs_res.data or []):
        decs_by_app[d['application_id']] = d

    appeals_res = supabase.table('appeals').select('application_id, status').execute()
    appeals_by_app = {}
    for a in (appeals_res.data or []):
        if (a.get('status') or '').upper() == 'PENDING':
            appeals_by_app[a['application_id']] = a

    counts = {'APPROVE': 0, 'REJECT': 0, 'NEEDS_HUMAN_REVIEW': 0, 'MISSING': 0}
    reject_gte_70 = 0
    reject_lt_70 = 0
    reject_apps = []

    for app in apps:
        aid = app['id']
        pred_obj = preds_by_app.get(aid)
        if not pred_obj or not pred_obj.get('prediction'):
            counts['MISSING'] += 1
        else:
            p_name = (pred_obj.get('prediction') or '').upper()
            prob = pred_obj.get('probability')
            conf = 0
            if prob is not None:
                conf = round(prob * 100) if prob <= 1.0 else round(prob)
            if p_name in counts:
                counts[p_name] += 1
            else:
                counts['NEEDS_HUMAN_REVIEW'] += 1
            
            if p_name == 'REJECT':
                if conf >= 70:
                    reject_gte_70 += 1
                else:
                    reject_lt_70 += 1
                dec = decs_by_app.get(aid)
                app_status = app.get('status')
                has_appeal = aid in appeals_by_app
                reject_apps.append({
                    'id': aid,
                    'conf': conf,
                    'status': app_status,
                    'decision': dec.get('decision') if dec else None,
                    'has_appeal': has_appeal
                })

    print(f"APPROVE: {counts['APPROVE']}")
    print(f"REJECT: {counts['REJECT']}")
    print(f"NEEDS_HUMAN_REVIEW: {counts['NEEDS_HUMAN_REVIEW']}")
    print(f"Missing prediction: {counts['MISSING']}")
    print(f"REJECT with confidence >= 70: {reject_gte_70}")
    print(f"REJECT with confidence < 70: {reject_lt_70}")
    print("\nAll REJECT applications:")
    for r in reject_apps:
        print(r)

if __name__ == '__main__':
    audit()
