"""Приём оплаты из любого канала (сайт, приложение, Telegram): файл и/или текст → оплаты."""

from sqlalchemy.orm import Session

from . import extractor, service
from .config import settings
from .extractor import ExtractionError
from .money import fmt_money
from .models import Attachment
from .schemas import RecognizeItem, RecognizeResult

class IntakeError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def process(
    db: Session,
    *,
    content: bytes | None = None,
    media_type: str | None = None,
    text: str | None = None,
    ocr_text: str | None = None,
    source: str | None = None,
) -> RecognizeResult:
    """text — то, что написал человек (оплата текстом или подпись к фото);
    ocr_text — текст чека, уже прочитанный на устройстве."""
    text = (text or "").strip()
    ocr_text = (ocr_text or "").strip()
    if not content and not text and not ocr_text:
        raise IntakeError("Пришлите фото чека или текст оплаты", 400)

    try:
        if content:
            if len(content) > settings.max_upload_bytes:
                mb = settings.max_upload_bytes // (1024 * 1024)
                raise IntakeError(f"Файл больше {mb} МБ", 413)
            media_type = media_type or "image/jpeg"
            found = extractor.extract_from_file(content, media_type, ocr_text)
            if text:
                # Подпись к фото (например, «за Машу») помогает найти ученика.
                for d in found:
                    d.purpose = " ".join(filter(None, [d.purpose, text]))
            source = source or "photo"
        elif ocr_text:
            found = extractor.extract_from_ocr_text(ocr_text)
            if text:
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

    attachment_id = None
    if content:
        attachment = Attachment(media_type=media_type, data=content)
        db.add(attachment)
        db.flush()
        attachment_id = attachment.id
    items = []
    for data in found:
        payment, cands, auto, duplicate = service.record_payment(
            db, data, source=source, raw_text=text or None, attachment_id=attachment_id
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

    if attachment_id and all(i.duplicate_of for i in items):
        service.delete_attachment_if_unused(db, attachment_id)
        db.commit()
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
