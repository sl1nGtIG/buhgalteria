"""Разбор текста чеков российских банков (результат OCR или текстовый слой PDF) без нейросети.

Поддерживает типичные чеки и скриншоты Сбербанка, Т-Банка, ВТБ, Альфа-Банка и переводов по СБП:
пары «подпись — значение» на одной строке или на соседних, суммы с ₽/руб, даты числами и
словами, а также списки входящих переводов из истории операций.
"""

import re
from datetime import date, timedelta

from .extractor import ReceiptData

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7,
    "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "июн": 6, "июл": 7, "авг": 8, "сен": 9,
    "сент": 9, "окт": 10, "ноя": 11, "нояб": 11, "дек": 12,
}

BANKS = [
    (r"сбер", "Сбербанк"),
    (r"т-?\s?банк|тинькофф|tinkoff|t-?bank", "Т-Банк"),
    (r"\bвтб\b|vtb", "ВТБ"),
    (r"альфа|alfa", "Альфа-Банк"),
    (r"газпромбанк", "Газпромбанк"),
    (r"озон\s?банк|ozon", "Озон Банк"),
    (r"яндекс\s?банк|yandex", "Яндекс Банк"),
    (r"райффайзен|raiffeisen", "Райффайзенбанк"),
    (r"почта\s?банк", "Почта Банк"),
    (r"мтс\s?банк", "МТС Банк"),
    (r"совкомбанк|халва", "Совкомбанк"),
    (r"открытие", "Банк Открытие"),
    (r"росбанк", "Росбанк"),
    (r"россельхоз", "Россельхозбанк"),
]

# Подписи полей. Порядок важен: более конкретные варианты раньше общих.
LABELS = {
    "amount": [
        "сумма перевода", "сумма платежа", "сумма операции", "сумма зачисления", "сумма в валюте",
        "сумма", "итого", "зачислено", "списано", "к оплате",
    ],
    "payer_name": [
        "фио отправителя", "фио плательщика", "имя отправителя", "отправитель", "плательщик",
        "от кого",
    ],
    "recipient_name": ["фио получателя", "имя получателя", "получатель", "кому"],
    "payer_phone": ["телефон отправителя", "номер телефона отправителя"],
    "purpose": [
        "сообщение получателю", "назначение платежа", "назначение", "комментарий", "сообщение",
        "цель перевода",
    ],
    "operation_id": [
        "номер документа", "номер операции", "идентификатор операции", "id операции",
        "номер квитанции", "квитанция №", "квитанция", "№ операции", "№ документа",
        "код операции", "номер транзакции", "идентификатор",
    ],
    "date": ["дата и время операции", "дата операции", "дата и время", "дата платежа", "дата"],
}
SKIP_LABELS = [
    "комиссия", "кэшбэк", "кешбэк", "бонус", "баланс", "остаток", "доступно", "лимит",
    "телефон получателя", "счёт получателя", "счет получателя", "карта получателя",
    "номер карты", "счёт отправителя", "счет отправителя", "карта отправителя", "бик", "инн",
    "кпп", "банк получателя", "банк отправителя", "статус", "код авторизации", "тип операции",
]

CURRENCY = r"(?:₽|руб(?:лей|ля|ль)?\.?|р\.|rub\b|rur\b|Р\b|P\b)"
NUM = r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
AMOUNT_RE = re.compile(rf"([+\-−–]?)\s*({NUM})\s*{CURRENCY}", re.IGNORECASE)
DATE_NUM_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b")
DATE_WORD_RE = re.compile(r"\b(\d{1,2})\s+([а-яё]+)\.?(?:\s+(\d{4}))?", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+7|\b8)[\s(\-]*[\d*•]{3}[\s)\-]*[\d*•]{3}[\s\-]*[\d*•]{2}[\s\-]*\d{2}")
NAME_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё.\- ]+")


def _clean(text: str) -> str:
    text = text.replace("\r", "").replace("\t", " ")
    # Типичные ошибки OCR в числах: буква О вместо нуля внутри суммы.
    text = re.sub(r"(?<=\d)[ОоOo](?=[\d\s.,])", "0", text)
    text = re.sub(r"(?<=\d[\s.,])[ОоOo](?=\d)", "0", text)
    return "\n".join(re.sub(r"[   ]{2,}", " ", line).strip(" :|") for line in text.split("\n"))


def _to_float(raw: str) -> float:
    return float(re.sub(r"[   ]", "", raw).replace(",", "."))


def _amount_in(line: str) -> float | None:
    m = AMOUNT_RE.search(line)
    return _to_float(m.group(2)) if m else None


def _parse_date(text: str, today: date) -> date | None:
    low = text.lower()
    if "сегодня" in low:
        return today
    if "вчера" in low:
        return today - timedelta(days=1)
    m = DATE_NUM_RE.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y += 2000 if y < 100 else 0
        try:
            return date(y, mo, d)
        except ValueError:
            pass
    for m in DATE_WORD_RE.finditer(text):
        month = MONTHS.get(m.group(2).lower().replace("ё", "е"))
        if not month:
            continue
        y = int(m.group(3)) if m.group(3) else today.year
        try:
            found = date(y, month, int(m.group(1)))
        except ValueError:
            continue
        # «28 декабря» без года в январе — это прошлый год.
        if not m.group(3) and found > today + timedelta(days=1):
            found = found.replace(year=y - 1)
        return found
    return None


def _label_match(line: str, labels: list[str]) -> str | None:
    """Если строка начинается с подписи — вернуть остаток строки (значение, может быть пустым)."""
    low = line.lower().replace("ё", "е")
    for label in labels:
        lab = label.replace("ё", "е")
        if low.startswith(lab):
            rest = line[len(lab):]
            if rest and rest[0].isalnum() and lab[-1].isalnum():
                continue  # «сумма» не должна совпасть с «суммарно»
            return rest.strip(" :—-–")
    return None


def _is_skip(line: str) -> bool:
    low = line.lower().replace("ё", "е")
    return any(low.startswith(s.replace("ё", "е")) for s in SKIP_LABELS)


def _clean_name(value: str) -> str | None:
    value = PHONE_RE.sub("", value)
    m = NAME_RE.search(value)
    if not m:
        return None
    name = re.sub(r"\s+", " ", m.group(0)).strip(" .-")
    letters = re.sub(r"[^A-Za-zА-Яа-яЁё]", "", name)
    return name if len(letters) >= 3 else None


def _plausible(field: str, value: str) -> bool:
    if field == "operation_id":
        # Номер операции содержит цифры и не является датой («Квитанция» над датой в Т-Банке).
        return bool(re.search(r"\d", value)) and not DATE_NUM_RE.search(value)
    if field == "amount":
        return bool(re.search(r"\d", value))
    return True


def _fields(lines: list[str]) -> dict[str, str]:
    """Пары «подпись — значение»: значение на той же строке или на следующей."""
    found: dict[str, str] = {}
    for i, line in enumerate(lines):
        if _is_skip(line):
            continue
        for field, labels in LABELS.items():
            if field in found:
                continue
            rest = _label_match(line, labels)
            if rest is None:
                continue
            if not rest and i + 1 < len(lines) and not _is_skip(lines[i + 1]):
                rest = lines[i + 1]
            if rest and _plausible(field, rest):
                found[field] = rest
            break
    return found


def _bank(lines: list[str]) -> str | None:
    """Банк отправителя: первое упоминание банка, кроме строк про получателя."""
    for line in lines:
        low = line.lower()
        if "получател" in low:
            continue
        for pattern, name in BANKS:
            if re.search(pattern, low):
                return name
    return None


def parse_receipt(text: str, today: date | None = None) -> list[ReceiptData]:
    """Текст чека → список оплат (обычно одна; для истории переводов — несколько)."""
    today = today or date.today()
    text = _clean(text)
    lines = [line for line in text.split("\n") if line]
    if not lines:
        return []

    history = _parse_history(lines, today)
    if len(history) >= 2:
        return history

    f = _fields(lines)
    amount = _amount_in(f["amount"]) if "amount" in f else None
    if amount is None and "amount" in f:
        nums = re.findall(NUM, f["amount"])
        amount = _to_float(nums[0]) if nums else None
    if amount is None:
        # Без подписи берём самую крупную сумму с валютой, кроме строк комиссии/баланса.
        candidates = [_amount_in(line) for line in lines if not _is_skip(line)]
        candidates = [a for a in candidates if a]
        amount = max(candidates) if candidates else None

    paid_at = _parse_date(f["date"], today) if "date" in f else None
    if paid_at is None:
        for line in lines:
            paid_at = _parse_date(line, today)
            if paid_at:
                break

    payer_phone = None
    if "payer_phone" in f:
        pm = PHONE_RE.search(f["payer_phone"])
        payer_phone = pm.group(0) if pm else None

    operation_id = None
    if "operation_id" in f:
        om = re.search(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9\-/]{3,}", f["operation_id"])
        operation_id = om.group(0) if om else None

    purpose = f.get("purpose")
    return [
        ReceiptData(
            is_payment=amount is not None,
            amount=amount,
            currency="RUB",
            date=paid_at.isoformat() if paid_at else None,
            payer_name=_clean_name(f["payer_name"]) if "payer_name" in f else None,
            payer_phone=payer_phone,
            recipient_name=_clean_name(f["recipient_name"]) if "recipient_name" in f else None,
            purpose=purpose.strip() if purpose else None,
            student_name=None,
            bank=_bank(lines),
            operation_id=operation_id,
        )
    ]


INCOMING_RE = re.compile(rf"^(.*?)\s*\+\s*({NUM})\s*{CURRENCY}", re.IGNORECASE)


def _parse_history(lines: list[str], today: date) -> list[ReceiptData]:
    """История операций: строки вида «Иван Петрович С. +5 000 ₽» под заголовками дат."""
    result = []
    current_date: date | None = None
    for i, line in enumerate(lines):
        if not AMOUNT_RE.search(line):
            d = _parse_date(line, today)
            if d and len(line) <= 30:
                current_date = d
                continue
        m = INCOMING_RE.match(line)
        if not m:
            continue
        name = _clean_name(m.group(1))
        if not name and i > 0 and not AMOUNT_RE.search(lines[i - 1]):
            name = _clean_name(lines[i - 1])
        result.append(
            ReceiptData(
                is_payment=True,
                amount=_to_float(m.group(2)),
                currency="RUB",
                date=(current_date or today).isoformat(),
                payer_name=name,
                payer_phone=None,
                recipient_name=None,
                purpose=None,
                student_name=None,
                bank=None,
                operation_id=None,
            )
        )
    return result
