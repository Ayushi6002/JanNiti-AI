import sys
from pathlib import Path

# Add project root only
root_dir = str(Path(__file__).resolve().parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.app import app
from backend.auth_service import login

def test():
    client = app.test_client()
    auth = login("jannititestadmin@gmail.com", "AdminTest@123")
    token = auth.session.access_token
    headers = {"Authorization": f"Bearer {token}"}

    app_id = "3e446278-315a-4f02-8b74-8aa715c2ee4a"
    res = client.get(f"/admin/applications/{app_id}", headers=headers)
    print("Status code:", res.status_code)
    data = res.get_json()
    print("App:", data["application"]["id"], data["application"]["status"])
    print("Docs count:", len(data["documents"]))
    for d in data["documents"]:
        doc_id = d["id"]
        print(f"  Doc: {doc_id} {d['document_type']} {d['file_name']}")
        # Test view
        v_res = client.get(f"/admin/applications/{app_id}/documents/{doc_id}/view?token={token}")
        print(f"    View code: {v_res.status_code} Content-Type: {v_res.headers.get('Content-Type')} Bytes: {len(v_res.data)}")
        assert v_res.status_code == 200
        assert len(v_res.data) > 0

        # Test download
        dl_res = client.get(f"/admin/applications/{app_id}/documents/{doc_id}/download?token={token}")
        print(f"    Download code: {dl_res.status_code} Content-Disposition: {dl_res.headers.get('Content-Disposition')} Bytes: {len(dl_res.data)}")
        assert dl_res.status_code == 200
        assert "attachment" in dl_res.headers.get("Content-Disposition", "")
        assert len(dl_res.data) > 0

    print("\nALL DOCUMENTS ACCESSED AND VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    test()
