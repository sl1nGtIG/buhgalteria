"""Приём оплаты из любого канала (сайт, приложение, Telegram): файл и/или текст → оплаты."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from . import extractor, service
from .config import settings
from .extractor import ExtractionError
from .money import fmt_money
from .schemas import RecognizeItem, RecognizeResult

MAX_FILE_BYTES = 10 * 1024 * 1024
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}


class IntakeError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _save_file(content: bytes, media_type: str) -> str:
    name = f"{date.today():%Y-%m}/{uuid.uuid4().hex}{EXTENSIONS.get(media_type, '.bin')}"
    path = settings.upload_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return name


def process(
    db: Session,
    *,
    content: bytes | None = None,
    media_type: str | None = None,
    text: str | None = None,
    source: str | None = None,
) -> RecognizeResult:
    text = (text or "").strip()
    if not content and not text:
        raise IntakeError("Пришлите фото чека или текст оплаты", 400)

    try:
        if content:
            if len(content) > MAX_FILE_BYTES:
                raise IntakeError("Файл больше 10 МБ", 413)
            media_type = media_type or "image/jpeg"
            found = extractor.extract_from_file(content, media_type)
            if text:
                # Подпись к фото (например, «за Машу») помогает найти ученика.
                for d in found:
                    d.purpose = " ".join(filter(None, [d.purpose, text]))
            source = source or "photo"
        else:
            found = extractor.extract_from_text(text)
            source = source or "text"
    except ExtractionError as e:
        raise IntakeError(str(e)) from e

    found = [d for d in found if d.amount is not None]
    if not found:
        raise IntakeError("Не удалось найти оплату: не видно суммы")

    file_path = _save_file(content, media_type) if content else None
    items = []
    for data in found:
        payment, cands, auto, duplicate = service.record_payment(
            db, data, source=source, raw_text=text or None, image_path=file_path
        )
        if duplicate is not None:
            message = "Уже была загружена ранее"
        elif auto:
            who = payment.student.full_name if payment.student else payment.parent.full_name
            message = f"Зафиксирована: {who}"
        elif cands:
            message = "Нужно подтвердить, кому относится оплата"
        else:
            message = "Плательщик не найден — выберите ученика или родителя"
        items.append(
            RecognizeItem(
                payment=service.payment_out(payment),
                candidates=service.candidates_out(db, cands),
                auto_confirmed=auto,
                duplicate_of=duplicate.id if duplicate else None,
                message=message,
            )
        )

    if file_path and all(i.duplicate_of for i in items):
        service.delete_attachment_if_unused(db, file_path)
    return RecognizeResult(items=items, message=summary(items))


def summary(items: list[RecognizeItem]) -> str:
    if len(items) == 1:
        return items[0].message
    auto = sum(i.auto_confirmed for i in items)
    dup = sum(i.duplicate_of is not None for i in items)
    review = len(items) - auto - dup
    total = sum(i.payment.amount or 0 for i in items if i.duplicate_of is None)
    parts = [f"Найдено оплат: {len(items)} на {fmt_money(total)}"]
    if auto:
        parts.append(f"зафиксировано {auto}")
    if review:
        parts.append(f"на проверку {review}")
    if dup:
        parts.append(f"дублей {dup}")
    return ", ".join(parts)
