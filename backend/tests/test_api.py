from app.extractor import ReceiptData
from app.routers import payments as payments_router


def seed(client):
    r = client.post("/api/students", json={
        "full_name": "Сидоров Александр", "group_name": "Робототехника", "monthly_fee": 5000,
        "new_parents": [{"full_name": "Сидоров Иван Петрович", "phone": "+79125551234"}],
    })
    assert r.status_code == 201, r.text
    sasha = r.json()
    r = client.post("/api/students", json={"full_name": "Кузнецова Мария", "monthly_fee": 4000})
    masha = r.json()
    return sasha, masha


def test_text_payment_auto_confirmed(client):
    sasha, _ = seed(client)
    r = client.post("/api/payments/recognize", data={"text": "Сидоров Саша 5000 15.10.2026"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auto_confirmed"] is True
    assert body["payment"]["student"]["id"] == sasha["id"]
    assert body["payment"]["amount"] == 5000

    report = client.get("/api/reports/month", params={"month": "2026-10"}).json()
    row = next(x for x in report["rows"] if x["student"]["id"] == sasha["id"])
    assert row["paid"] == 5000 and row["debt"] == 0


def test_photo_payment_and_learning(client, monkeypatch):
    sasha, masha = seed(client)
    receipt = ReceiptData(
        is_payment=True, amount=4000, currency="RUB", date="2026-10-10",
        payer_name="Елена Сергеевна К.", payer_phone=None, recipient_name=None,
        purpose=None, student_name=None, bank="Сбербанк", operation_id="OP-1",
    )
    monkeypatch.setattr(payments_router, "extract_from_image", lambda content, mt: receipt)
    files = {"file": ("check.jpg", b"\xff\xd8fake", "image/jpeg")}

    r = client.post("/api/payments/recognize", files=files)
    body = r.json()
    assert body["auto_confirmed"] is False
    assert body["payment"]["status"] == "needs_review"
    assert body["payment"]["has_image"] is True
    pid = body["payment"]["id"]

    # Бухгалтер вручную указывает ученицу — система запоминает плательщика.
    r = client.patch(f"/api/payments/{pid}", json={"student_id": masha["id"]})
    assert r.json()["status"] == "confirmed"
    assert client.get(f"/api/payments/{pid}/image").status_code == 200

    # Тот же чек повторно — распознаётся как дубль.
    r = client.post("/api/payments/recognize", files=files)
    assert r.json()["duplicate_of"] == pid

    # Новый чек от того же плательщика — привязывается автоматически.
    receipt.operation_id, receipt.date = "OP-2", "2026-11-10"
    r = client.post("/api/payments/recognize", files=files)
    body = r.json()
    assert body["auto_confirmed"] is True
    assert body["payment"]["student"]["id"] == masha["id"]


def test_text_without_amount_rejected(client):
    seed(client)
    r = client.post("/api/payments/recognize", data={"text": "Сидоров Саша"})
    assert r.status_code == 422


def test_export_csv(client):
    sasha, _ = seed(client)
    client.post("/api/payments/manual", json={"amount": 5000, "paid_at": "2026-10-01", "student_id": sasha["id"]})
    r = client.get("/api/payments/export.csv", params={"month": "2026-10"})
    assert r.status_code == 200
    assert "Сидоров Александр" in r.content.decode("utf-8-sig")


def test_token_required(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "app_token", "secret")
    assert client.get("/api/students").status_code == 401
    assert client.get("/api/students", headers={"Authorization": "Bearer secret"}).status_code == 200
    assert client.get("/api/health").status_code == 200


def test_same_text_twice_is_duplicate(client):
    seed(client)
    first = client.post("/api/payments/recognize", data={"text": "Кузнецовы 3000 15.10.2026"}).json()
    second = client.post("/api/payments/recognize", data={"text": "Кузнецовы 3000 15.10.2026"}).json()
    assert second["duplicate_of"] == first["payment"]["id"]
