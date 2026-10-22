from datetime import date

from app.receipt_parser import parse_receipt

TODAY = date(2026, 10, 19)

SBER = """СБЕР
Чек по операции
19 октября 2026 14:35:12 (МСК)
Операция Перевод клиенту СберБанка
ФИО получателя Мария Ивановна С.
Номер карты получателя **** 1234
ФИО отправителя Иван Петрович С.
Счёт отправителя **** 5678
Сумма перевода 5 000,00 ₽
Комиссия 0,00 ₽
Сообщение получателю за Сашу октябрь
Номер документа 1234567890
Код авторизации 123456
"""

TBANK_SCREENSHOT = """Т-Банк
Квитанция
18.10.2026 09:12:44
Итого
4 500 ₽
Перевод по номеру телефона
Статус Успешно
Сумма 4 500 ₽
Комиссия Без комиссии
Отправитель
Ольга Кузнецова
Телефон получателя +7 (912) 555-12-34
Получатель
Мария С.
Банк получателя Сбербанк
Квитанция № 1-2-345-678-901
"""

VTB_OCR_NOISE = """ВТБ
Перевод выполнен
Сумма: 3 5О0 Р
Дата операции: 15.10.26
Отправитель: Смирнов Алексей Игоревич
Телефон отправителя: +7 903 555-00-11
Назначение платежа: оплата рисование Соня
"""

HISTORY = """История
Сегодня
Иван Петрович С. +5 000 ₽
Входящий перевод
Ольга Викторовна К. +8 000 ₽
Пятёрочка −1 250,40 ₽
17 октября
Алексей Игоревич С. +3 500 ₽
"""


def test_sber_receipt():
    (r,) = parse_receipt(SBER, TODAY)
    assert r.amount == 5000
    assert r.date == "2026-10-19"
    assert r.payer_name == "Иван Петрович С"
    assert r.recipient_name.startswith("Мария Ивановна")
    assert r.purpose == "за Сашу октябрь"
    assert r.operation_id == "1234567890"
    assert r.bank == "Сбербанк"


def test_tbank_values_on_next_line():
    (r,) = parse_receipt(TBANK_SCREENSHOT, TODAY)
    assert r.amount == 4500
    assert r.date == "2026-10-18"
    assert r.payer_name == "Ольга Кузнецова"
    assert r.operation_id == "1-2-345-678-901"
    assert r.bank == "Т-Банк"
    assert r.payer_phone is None  # телефон получателя — это не плательщик


def test_ocr_noise_and_payer_phone():
    (r,) = parse_receipt(VTB_OCR_NOISE, TODAY)
    assert r.amount == 3500
    assert r.date == "2026-10-15"
    assert r.payer_name == "Смирнов Алексей Игоревич"
    assert r.payer_phone.endswith("00-11")
    assert r.purpose == "оплата рисование Соня"


def test_history_with_several_incoming_transfers():
    items = parse_receipt(HISTORY, TODAY)
    assert [(i.payer_name, i.amount, i.date) for i in items] == [
        ("Иван Петрович С", 5000, "2026-10-19"),
        ("Ольга Викторовна К", 8000, "2026-10-19"),
        ("Алексей Игоревич С", 3500, "2026-10-17"),
    ]


def test_unlabeled_amount_ignores_commission():
    (r,) = parse_receipt("Перевод выполнен\n2 000 ₽\nКомиссия 30 ₽", TODAY)
    assert r.amount == 2000


def test_empty_text():
    assert parse_receipt("   \n ", TODAY) == []
