from app import extractor
from app.extractor import ReceiptData


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


def receipt(**kw):
    base = dict(
        is_payment=True, amount=None, currency="RUB", date=None, payer_name=None, payer_phone=None,
        recipient_name=None, purpose=None, student_name=None, bank=None, operation_id=None,
    )
    return ReceiptData(**{**base, **kw})


def test_text_payment_auto_confirmed(client):
    sasha, _ = seed(client)
    r = client.post("/api/payments/recognize", data={"text": "Сидоров Саша 5000 15.10.2026"})
    assert r.status_code == 200, r.text
    body = r.json()["items"][0]
    assert body["auto_confirmed"] is True
    assert body["payment"]["student"]["id"] == sasha["id"]
    assert body["payment"]["amount"] == 5000

    report = client.get("/api/reports/month", params={"month": "2026-10"}).json()
    row = next(x for x in report["rows"] if x["student"]["id"] == sasha["id"])
    assert row["paid"] == 5000 and row["debt"] == 0


def test_photo_payment_and_learning(client, monkeypatch):
    sasha, masha = seed(client)
    rec = receipt(amount=4000, date="2026-10-10", payer_name="Елена Сергеевна К.",
                  bank="Сбербанк", operation_id="OP-1")
    monkeypatch.setattr(extractor, "extract_from_file", lambda *a: [rec.model_copy()])
    files = {"file": ("check.jpg", b"\xff\xd8fake", "image/jpeg")}

    r = client.post("/api/payments/recognize", files=files)
    body = r.json()["items"][0]
    assert body["auto_confirmed"] is False
    assert body["payment"]["status"] == "needs_review"
    assert body["payment"]["attachment"] == "image"
    pid = body["payment"]["id"]

    # Бухгалтер вручную указывает ученицу — система запоминает плательщика.
    r = client.patch(f"/api/payments/{pid}", json={"student_id": masha["id"]})
    assert r.json()["status"] == "confirmed"
    assert client.get(f"/api/payments/{pid}/image").status_code == 200

    # Тот же чек повторно — распознаётся как дубль.
    r = client.post("/api/payments/recognize", files=files)
    assert r.json()["items"][0]["duplicate_of"] == pid

    # Новый чек от того же плательщика — привязывается автоматически.
    rec.operation_id, rec.date = "OP-2", "2026-11-10"
    r = client.post("/api/payments/recognize", files=files)
    body = r.json()["items"][0]
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
    assert second["items"][0]["duplicate_of"] == first["items"][0]["payment"]["id"]


def test_statement_with_several_payments(client, monkeypatch):
    sasha, masha = seed(client)
    found = [
        receipt(amount=5000, date="2026-10-03", payer_name="Иван Петрович С.", operation_id="A"),
        receipt(amount=4000, date="2026-10-04", payer_name="Неизвестный Н.", operation_id="B"),
    ]
    monkeypatch.setattr(extractor, "extract_from_file", lambda *a: [f.model_copy() for f in found])
    r = client.post("/api/payments/recognize", files={"file": ("st.pdf", b"%PDF-1.4", "application/pdf")})
    body = r.json()
    assert [i["auto_confirmed"] for i in body["items"]] == [True, False]
    assert body["items"][0]["payment"]["student"]["id"] == sasha["id"]
    assert body["items"][0]["payment"]["attachment"] == "pdf"
    assert "Найдено оплат: 2" in body["message"]

    # Общий файл удаляется только вместе с последней оплатой.
    first, second = (i["payment"]["id"] for i in body["items"])
    client.delete(f"/api/payments/{first}")
    assert client.get(f"/api/payments/{second}/image").status_code == 200


def test_several_lines_of_text(client):
    seed(client)
    r = client.post("/api/payments/recognize", data={"text": "Сидоров Саша 5000\nКузнецова Маша 4000"})
    items = r.json()["items"]
    assert [i["payment"]["amount"] for i in items] == [5000, 4000]
    assert all(i["auto_confirmed"] for i in items)


def test_edit_amount_keeps_assignment(client):
    sasha, _ = seed(client)
    item = client.post("/api/payments/recognize", data={"text": "Сидоров Саша 500"}).json()["items"][0]
    r = client.patch(f"/api/payments/{item['payment']['id']}", json={"amount": 5000})
    assert r.json()["amount"] == 5000 and r.json()["student"]["id"] == sasha["id"]


def test_deleting_student_unlinks_payments_and_forgets_payer(client, monkeypatch):
    sasha, masha = seed(client)
    rec = receipt(amount=4000, date="2026-10-10", payer_name="Елена Сергеевна К.", operation_id="X1")
    monkeypatch.setattr(extractor, "extract_from_file", lambda *a: [rec.model_copy()])
    files = {"file": ("c.jpg", b"\xff\xd8", "image/jpeg")}
    pid = client.post("/api/payments/recognize", files=files).json()["items"][0]["payment"]["id"]
    client.patch(f"/api/payments/{pid}", json={"student_id": masha["id"]})

    assert client.delete(f"/api/students/{masha['id']}").status_code == 204
    assert client.get(f"/api/payments/{pid}").json()["student"] is None

    rec.operation_id, rec.date = "X2", "2026-11-10"
    item = client.post("/api/payments/recognize", files=files).json()["items"][0]
    assert item["auto_confirmed"] is False


SBER_TEXT = """СБЕР
Чек по операции
19 октября 2026 14:35:12 (МСК)
ФИО отправителя Иван Петрович С.
Сумма перевода 5 000,00 ₽
Комиссия 0,00 ₽
Номер документа 777000111
"""


def test_photo_read_on_device_is_parsed_without_ai(client):
    sasha, _ = seed(client)
    files = {"file": ("check.jpg", b"\xff\xd8fake", "image/jpeg")}
    r = client.post("/api/payments/recognize", files=files, data={"ocr_text": SBER_TEXT})
    item = r.json()["items"][0]
    assert item["auto_confirmed"] is True
    assert item["payment"]["student"]["id"] == sasha["id"]
    assert item["payment"]["operation_id"] == "777000111"
    assert item["payment"]["attachment"] == "image"


def test_ocr_text_without_file(client):
    sasha, _ = seed(client)
    r = client.post("/api/payments/recognize", data={"ocr_text": SBER_TEXT, "text": "за октябрь"})
    item = r.json()["items"][0]
    assert item["payment"]["amount"] == 5000
    assert item["payment"]["student"]["id"] == sasha["id"]


def test_photo_without_text_and_without_server_ocr(client, monkeypatch):
    from app import ocr

    monkeypatch.setattr(ocr, "tesseract_available", lambda: False)
    r = client.post("/api/payments/recognize", files={"file": ("c.jpg", b"\xff\xd8", "image/jpeg")})
    assert r.status_code == 422
    assert "текстом" in r.json()["detail"]


def test_pdf_without_text_layer_is_reported(client):
    import io

    from pypdf import PdfWriter

    seed(client)
    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(100, 100)
    writer.write(buf)
    r = client.post("/api/payments/recognize", files={"file": ("c.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 422
