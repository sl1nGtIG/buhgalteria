"""Извлечение данных об оплате из фото чека или произвольного текста."""

import base64
import re
from datetime import date, timedelta

import anthropic
from pydantic import BaseModel, Field

from .config import settings


class ReceiptData(BaseModel):
    is_payment: bool = Field(description="Похоже ли это на оплату/перевод денег")
    amount: float | None = Field(description="Сумма оплаты в рублях, без комиссии")
    currency: str | None = Field(description="Код валюты, обычно RUB")
    date: str | None = Field(description="Дата оплаты в формате YYYY-MM-DD")
    payer_name: str | None = Field(description="ФИО отправителя (плательщика) как в чеке")
    payer_phone: str | None = Field(description="Телефон отправителя, если указан")
    recipient_name: str | None = Field(description="ФИО или название получателя")
    purpose: str | None = Field(
        description="Назначение платежа / сообщение получателю / комментарий целиком"
    )
    student_name: str | None = Field(
        description="Имя ученика (ребёнка), если оно упомянуто в назначении или тексте"
    )
    bank: str | None = Field(description="Банк отправителя")
    operation_id: str | None = Field(description="Номер операции / документа / квитанции")


class ReceiptBatch(BaseModel):
    payments: list[ReceiptData] = Field(
        description="Все оплаты, найденные в источнике (обычно одна; в выписке может быть несколько)"
    )


class ExtractionError(Exception):
    pass


SYSTEM_PROMPT = """Ты помогаешь бухгалтеру учебного центра вести учёт оплат за обучение.
Тебе присылают скриншот или фото банковского чека (Сбербанк, Т-Банк, ВТБ, СБП и др.)
или короткое сообщение вроде «Иванов Петя 5000 за октябрь».

Также бывают PDF-квитанции и скриншоты истории операций / выписки, где видно сразу несколько
переводов, — тогда верни каждый перевод отдельной записью в payments. Бери только переводы
за обучение: чек об отправке денег от родителя или входящие поступления в выписке получателя.
Пропускай покупки, списания, комиссии и прочие не относящиеся операции.

Извлеки поля каждой оплаты. Правила:
- amount — сумма перевода в рублях числом (без комиссии). «5 000,00 ₽» → 5000.
- date — дата операции в формате YYYY-MM-DD. Если год не указан, считай текущий год.
- payer_name — отправитель так, как написано в чеке (банки часто сокращают: «Иван Петрович С.»).
- student_name — ребёнок/ученик, за которого платят, если он упомянут где угодно.
- purpose — назначение платежа или сообщение получателю дословно.
- Если поля нет в источнике — верни null, ничего не придумывай.
Сегодняшняя дата: {today}."""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
SUPPORTED_TYPES = IMAGE_TYPES + ("application/pdf",)


def _ask_claude(content: list[dict]) -> list[ReceiptData]:
    try:
        response = _client().beta.messages.parse(
            model=settings.claude_model,
            max_tokens=16000,
            system=SYSTEM_PROMPT.format(today=date.today().isoformat()),
            messages=[{"role": "user", "content": content}],
            output_format=ReceiptBatch,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APIConnectionError as e:
        raise ExtractionError(f"Нет связи с сервисом распознавания: {e}") from e
    except anthropic.RateLimitError as e:
        raise ExtractionError("Сервис распознавания перегружен, попробуйте позже") from e
    except anthropic.APIStatusError as e:
        raise ExtractionError(f"Ошибка сервиса распознавания ({e.status_code})") from e

    if response.stop_reason == "refusal":
        raise ExtractionError("Сервис распознавания отказался обрабатывать файл")
    if response.parsed_output is None:
        raise ExtractionError("Не удалось разобрать ответ сервиса распознавания")
    return [p for p in response.parsed_output.payments if p.is_payment or p.amount is not None]


def extract_from_file(content: bytes, media_type: str, ocr_text: str | None = None) -> list[ReceiptData]:
    """Фото, скриншот или PDF-квитанция → список оплат.

    По умолчанию работает без внешних API: текст чека читается на устройстве (ocr_text) или на
    сервере (текстовый слой PDF, Tesseract) и разбирается парсером чеков. Если задан ключ
    Claude API, распознавание выполняет модель — так точнее на плохих фото.
    """
    if media_type not in SUPPORTED_TYPES:
        raise ExtractionError(f"Неподдерживаемый формат файла: {media_type}")
    if settings.anthropic_enabled:
        data = base64.standard_b64encode(content).decode("utf-8")
        source = {"type": "base64", "media_type": media_type, "data": data}
        kind = "document" if media_type == "application/pdf" else "image"
        try:
            return _ask_claude([{"type": kind, "source": source},
                                {"type": "text", "text": "Извлеки данные оплаты из этого чека."}])
        except ExtractionError:
            if not ocr_text:
                raise

    from . import ocr
    from .receipt_parser import parse_receipt

    text = (ocr_text or "").strip() or ocr.file_text(content, media_type)
    if not text:
        raise ExtractionError(
            "Не удалось прочитать чек на сервере. Загрузите его через сайт или приложение "
            "(там чек читается прямо на устройстве) или напишите оплату текстом."
        )
    return parse_receipt(text)


def extract_from_ocr_text(ocr_text: str) -> list[ReceiptData]:
    """Чек уже прочитан на устройстве, а сам файл не прислан (например, слишком большой PDF)."""
    from .receipt_parser import parse_receipt

    return parse_receipt(ocr_text)


def extract_from_text(text: str) -> list[ReceiptData]:
    if settings.anthropic_enabled:
        try:
            return _ask_claude([{"type": "text", "text": text}])
        except ExtractionError:
            pass  # для текста есть запасной разбор без нейросети
    return parse_text_locally_multi(text)


# --- Разбор текста без нейросети -------------------------------------------------

_NUM = r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_AMOUNT_WITH_CURRENCY = re.compile(
    rf"({_NUM})\s*(?:₽|руб(?:лей|ля|ль)?\.?|р\.?(?=\s|$|[,;])|rub\b|rur\b)", re.IGNORECASE
)
_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b")
_BARE_NUMBER = re.compile(rf"(?<![\d.,])({_NUM})(?![\d.,]*\d)")
_PHONE = re.compile(r"(?:\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")


def _to_float(raw: str) -> float:
    return float(raw.replace(" ", "").replace(" ", "").replace(",", "."))


def _parse_date(text: str, today: date) -> tuple[date | None, str]:
    lowered = text.lower()
    if "позавчера" in lowered:
        return today - timedelta(days=2), re.sub("позавчера", " ", text, flags=re.I)
    if "вчера" in lowered:
        return today - timedelta(days=1), re.sub("вчера", " ", text, flags=re.I)
    if "сегодня" in lowered:
        return today, re.sub("сегодня", " ", text, flags=re.I)
    m = _DATE.search(text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
        y = today.year if not year else int(year) + (2000 if len(year) == 2 else 0)
        try:
            return date(y, month, day), text[: m.start()] + " " + text[m.end() :]
        except ValueError:
            pass
    return None, text


def parse_text_locally_multi(text: str, today: date | None = None) -> list[ReceiptData]:
    """Несколько строк, в каждой своя сумма («Сидоров 5000\nКузнецова 4000») → несколько оплат."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        parsed = [parse_text_locally(line, today) for line in lines]
        if all(p.amount is not None for p in parsed):
            return parsed
    return [parse_text_locally(text, today)]


def parse_text_locally(text: str, today: date | None = None) -> ReceiptData:
    today = today or date.today()
    rest = text

    phone = None
    pm = _PHONE.search(rest)
    if pm:
        phone = pm.group(0)
        rest = rest[: pm.start()] + " " + rest[pm.end() :]

    paid_at, rest = _parse_date(rest, today)

    amount = None
    m = _AMOUNT_WITH_CURRENCY.search(rest)
    if m:
        amount = _to_float(m.group(1))
        rest = rest[: m.start()] + " " + rest[m.end() :]
    else:
        # Берём самое большое отдельное число — обычно это сумма.
        candidates = [(mm, _to_float(mm.group(1))) for mm in _BARE_NUMBER.finditer(rest)]
        candidates = [(mm, v) for mm, v in candidates if v >= 50]
        if candidates:
            mm, amount = max(candidates, key=lambda c: c[1])
            rest = rest[: mm.start()] + " " + rest[mm.end() :]

    purpose = re.sub(r"\s+", " ", rest).strip(" ,.;:-") or None
    return ReceiptData(
        is_payment=amount is not None,
        amount=amount,
        currency="RUB",
        date=paid_at.isoformat() if paid_at else None,
        payer_name=None,
        payer_phone=phone,
        recipient_name=None,
        purpose=purpose,
        student_name=None,
        bank=None,
        operation_id=None,
    )
