import sys
from pathlib import Path

# Add project root only
root_dir = str(Path(__file__).resolve().parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.app import app
from backend.auth_service import login
from test_evaluator_workflow_restructure import classify_application
from backend.supabase_client import supabase

def run_document_matrix():
    client = app.test_client()

    admin_auth = login("jannititestadmin@gmail.com", "AdminTest@123")
    admin_token = admin_auth.session.access_token
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    student_auth = login("ayushi1219jain@gmail.com", "JanNitiTest@2026")
    student_token = student_auth.session.access_token
    student_headers = {"Authorization": f"Bearer {student_token}"}

    print("Fetching all applications from /admin/applications...")
    res = client.get("/admin/applications", headers=admin_headers)
    assert res.status_code == 200
    apps = res.get_json().get("applications", [])
    print(f"Loaded {len(apps)} applications.")

    # Categorize all applications
    by_category = {
        "APPROVED": [],
        "REJECTED": [],
        "LIKELY_APPROVED": [],
        "LIKELY_REJECTED": [],
        "REQUIRES_REVIEW": [],
        "APPEAL_PENDING": [],
    }

    for a in apps:
        c = classify_application(a)
        if c["top"] == "DECISION_MADE":
            if c["sub"] == "APPROVED":
                by_category["APPROVED"].append(a)
            elif c["sub"] == "REJECTED":
                by_category["REJECTED"].append(a)
        elif c["top"] == "PENDING_DECISIONS":
            if c["sub"] == "LIKELY_APPROVED":
                by_category["LIKELY_APPROVED"].append(a)
            elif c["sub"] == "LIKELY_REJECTED":
                by_category["LIKELY_REJECTED"].append(a)
            elif c["sub"] == "REQUIRES_REVIEW":
                by_category["REQUIRES_REVIEW"].append(a)
        elif c["top"] == "APPEAL_PENDING":
            by_category["APPEAL_PENDING"].append(a)

    print("\n--- Current Application Distribution across 6 States ---")
    for k, v in by_category.items():
        print(f"  {k}: {len(v)} applications")

    # Verify that Likely to Get Rejected now has applications!
    assert len(by_category["LIKELY_REJECTED"]) > 0, "Likely to Get Rejected must not be 0!"

    # Test Matrix: Test document access for each of the 6 categories
    target_states = [
        ("APPROVED", "1. Decision Made by Admin -> Approved"),
        ("REJECTED", "2. Decision Made by Admin -> Rejected"),
        ("LIKELY_APPROVED", "3. Pending Decisions -> Likely to Get Approved"),
        ("LIKELY_REJECTED", "4. Pending Decisions -> Likely to Get Rejected"),
        ("REQUIRES_REVIEW", "5. Pending Decisions -> Requires Human Review"),
        ("APPEAL_PENDING", "6. Appeal Pending"),
    ]

    for key, label in target_states:
        print(f"\n=======================================================")
        print(f"Testing Matrix State: {label}")
        print(f"=======================================================")
        candidate_apps = by_category[key]
        assert len(candidate_apps) > 0, f"No candidates found for {key}"

        found_with_docs = False
        for app_item in candidate_apps:
            full_res = client.get(f"/admin/applications/{app_item['id']}", headers=admin_headers)
            assert full_res.status_code == 200
            full_data = full_res.get_json()
            docs = full_data.get("documents", [])

            if docs:
                found_with_docs = True
                print(f"Found app {app_item['id']} with {len(docs)} documents.")
                for d in docs:
                    doc_id = d["id"]
                    doc_name = d.get("file_name") or d.get("document_type")
                    print(f"  Testing Doc: {doc_name} ({doc_id})")

                    # 1. View / Open
                    v_res = client.get(f"/admin/applications/{app_item['id']}/documents/{doc_id}/view?token={admin_token}")
                    assert v_res.status_code == 200, f"View failed with {v_res.status_code}"
                    assert len(v_res.data) > 0, "View returned 0 bytes"
                    assert "inline" in v_res.headers.get("Content-Disposition", "inline"), "View must be inline"
                    print(f"    View OK (HTTP 200, {len(v_res.data)} bytes, {v_res.headers.get('Content-Type')})")

                    # 2. Download
                    dl_res = client.get(f"/admin/applications/{app_item['id']}/documents/{doc_id}/download?token={admin_token}")
                    assert dl_res.status_code == 200, f"Download failed with {dl_res.status_code}"
                    assert len(dl_res.data) > 0, "Download returned 0 bytes"
                    assert "attachment" in dl_res.headers.get("Content-Disposition", ""), "Download must be attachment"
                    print(f"    Download OK (HTTP 200, {len(dl_res.data)} bytes, {dl_res.headers.get('Content-Disposition')})")
                break

        assert found_with_docs, f"Expected at least one application in {key} to have documents attached"

    print("\n=======================================================")
    print("ALL 6 EVALUATOR MATRIX STATES PASSED DOCUMENT TESTING!")
    print("=======================================================")

if __name__ == "__main__":
    run_document_matrix()
