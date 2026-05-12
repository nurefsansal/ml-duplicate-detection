"""Manuel uçtan uca deneme (auth + canlı DB gerekir).

    python -m backend.tests.smoke_detect_admin

CI / şema doğrulama için: `pytest backend/tests/test_smoke_openapi_routes.py`
"""

from fastapi.testclient import TestClient

from backend.main import app


def main() -> None:
    client = TestClient(app)

    payload = {
        "records": [
            {
                "adSoyad": "Ahmet Yilmaz",
                "tcKimlikNo": "12345678901",
                "telefon": "05551234567",
                "email": "ahmet@test.com",
                "sehir": "Ankara",
            },
            {
                "adSoyad": "Ahmed Yilmaz",
                "tcKimlikNo": "12345678901",
                "telefon": "05551234567",
                "email": "ahmet+bagis@test.com",
                "sehir": "Ankara",
            },
            {
                "adSoyad": "Mehmet Yilmaz",
                "tcKimlikNo": "99999999999",
                "telefon": "05551230000",
                "email": "mehmet@test.com",
                "sehir": "Ankara",
            },
        ],
        "minRulesToMatch": 2,
        "saveToDb": True,
    }

    r_detect = client.post("/api/v1/detect", json=payload)
    print("detect", r_detect.status_code)
    detect_json = r_detect.json()
    print(
        "uploadId",
        detect_json.get("uploadId"),
        "insertedRows",
        detect_json.get("insertedRows"),
        "duplicatePairs",
        detect_json.get("duplicatePairs"),
    )

    upload_id = detect_json.get("uploadId")
    r_pending = client.get("/api/v1/admin/pending-matches", params={"upload_id": upload_id})
    pending_json = r_pending.json()
    print("pending", r_pending.status_code, "count", pending_json.get("count"))

    matches = pending_json.get("matches", [])
    match_id = matches[0]["id"] if matches else None
    print("match_id", match_id)

    if match_id is not None:
        r_approve = client.post(
            "/api/v1/admin/approve-match",
            json={
                "match_id": match_id,
                "approved_by": "test_admin",
                "merge_into_entity": True,
            },
        )
        print("approve", r_approve.status_code, "entity", r_approve.json().get("entity_id"))

    r_entities = client.get("/api/v1/admin/entities")
    entities_json = r_entities.json()
    print("entities", r_entities.status_code, "count", entities_json.get("count"))


if __name__ == "__main__":
    main()
