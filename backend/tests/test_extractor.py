from datetime import date

from app.extractor import parse_text_locally

TODAY = date(2026, 10, 19)


def test_amount_with_currency_and_date():
    d = parse_text_locally("Иванов Петя 5 000 руб 15.10", TODAY)
    assert d.amount == 5000 and d.date == "2026-10-15"
    assert d.purpose == "Иванов Петя"


def test_bare_amount_and_relative_date():
    d = parse_text_locally("вчера Маша Кузнецова 4500", TODAY)
    assert d.amount == 4500 and d.date == "2026-10-18"


def test_rubles_sign_and_decimal():
    d = parse_text_locally("Сидоров 3500,50₽", TODAY)
    assert d.amount == 3500.5


def test_no_amount():
    d = parse_text_locally("просто сообщение", TODAY)
    assert d.amount is None and not d.is_payment
