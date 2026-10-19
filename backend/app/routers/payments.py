import csv
import io
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from .. import service
from ..config import settings
from ..db import get_db
from ..extractor import ExtractionError, extract_from_image, extract_from_text
from ..models import Parent, Payment, Student
from ..schemas import CandidateOut, ManualPaymentIn, PaymentOut, PaymentUpdate, RecognizeResult

router = APIRouter(prefix="/payments", tags=["payments"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def _get(db: Session, payment_id: int) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Оплата не найдена")
    return payment


@router.post("/recognize", response_model=RecognizeResult)
async def recognize(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Главный сценарий: прислали фото чека и/или текст — система сама фиксирует оплату."""
    text = (text or "").strip()
    if file is None and not text:
        raise HTTPException(status_code=400, detail="Пришлите фото чека или текст оплаты")

    image_path = None
    try:
        if file is not None:
            content = await file.read()
            if len(content) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="Фото больше 10 МБ")
            media_type = file.content_type or "image/jpeg"
            data = extract_from_image(content, media_type)
            if text:
                # Подпись к фото (например, «за Машу») помогает найти ученика.
                data.purpose = " ".join(filter(None, [data.purpose, text]))
            image_path = _save_image(content, media_type)
            source = "photo"
        else:
            data = extract_from_text(text)
            source = "text"
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if not data.is_payment and data.amount is None:
        raise HTTPException(status_code=422, detail="Не удалось найти оплату: нет суммы")

    payment, cands, auto, duplicate = service.record_payment(
        db, data, source=source, raw_text=text or None, image_path=image_path
    )
    if duplicate is not None:
        if image_path:
            (settings.upload_dir / image_path).unlink(missing_ok=True)
        message = "Эта оплата уже была загружена ранее"
    elif auto:
        who = payment.student.full_name if payment.student else payment.parent.full_name
        message = f"Оплата зафиксирована: {who}"
    elif cands:
        message = "Нужно подтвердить, кому относится оплата"
    else:
        message = "Плательщик не найден — выберите ученика или родителя вручную"

    return RecognizeResult(
        payment=service.payment_out(payment),
        candidates=service.candidates_out(db, cands),
        auto_confirmed=auto,
        duplicate_of=duplicate.id if duplicate else None,
        message=message,
    )


def _save_image(content: bytes, media_type: str) -> str:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    name = f"{date.today():%Y-%m}/{uuid.uuid4().hex}{EXTENSIONS.get(media_type, '.jpg')}"
    path = settings.upload_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return name


@router.post("/manual", response_model=PaymentOut, status_code=201)
def create_manual(body: ManualPaymentIn, db: Session = Depends(get_db)):
    if not body.student_id and not body.parent_id:
        raise HTTPException(status_code=400, detail="Укажите ученика или родителя")
    payment = Payment(
        amount=body.amount,
        paid_at=body.paid_at,
        student_id=body.student_id,
        parent_id=body.parent_id,
        purpose=body.purpose,
        source="manual",
        status="confirmed",
        confidence=1.0,
    )
    _check_refs(db, payment)
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return service.payment_out(payment)


def _payments_query(status, month, student_id, parent_id):
    q = select(Payment).order_by(Payment.paid_at.desc(), Payment.id.desc())
    if status:
        q = q.where(Payment.status == status)
    if month:
        year, mon = _parse_month(month)
        q = q.where(extract("year", Payment.paid_at) == year, extract("month", Payment.paid_at) == mon)
    if student_id:
        q = q.where(Payment.student_id == student_id)
    if parent_id:
        q = q.where(Payment.parent_id == parent_id)
    return q


def _parse_month(month: str) -> tuple[int, int]:
    try:
        year, mon = month.split("-")
        return int(year), int(mon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Месяц в формате ГГГГ-ММ") from e


@router.get("", response_model=list[PaymentOut])
def list_payments(
    status: str | None = None,
    month: str | None = None,
    student_id: int | None = None,
    parent_id: int | None = None,
    db: Session = Depends(get_db),
):
    rows = db.scalars(_payments_query(status, month, student_id, parent_id)).all()
    return [service.payment_out(p) for p in rows]


@router.get("/export.csv")
def export_csv(month: str | None = None, db: Session = Depends(get_db)):
    rows = db.scalars(_payments_query(None, month, None, None)).all()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Дата", "Сумма", "Ученик", "Родитель", "Плательщик", "Назначение", "Статус", "Источник"])
    for p in rows:
        w.writerow([
            p.paid_at.isoformat() if p.paid_at else "",
            f"{p.amount:.2f}".replace(".", ",") if p.amount is not None else "",
            p.student.full_name if p.student else "",
            p.parent.full_name if p.parent else "",
            p.payer_name or "",
            p.purpose or "",
            "подтверждена" if p.status == "confirmed" else "на проверке",
            p.source,
        ])
    # BOM, чтобы Excel правильно открыл кириллицу.
    data = "﻿" + buf.getvalue()
    filename = f"payments-{month or 'all'}.csv"
    return StreamingResponse(
        iter([data.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: int, db: Session = Depends(get_db)):
    return service.payment_out(_get(db, payment_id))


@router.get("/{payment_id}/candidates", response_model=list[CandidateOut])
def get_candidates(payment_id: int, db: Session = Depends(get_db)):
    payment = _get(db, payment_id)
    return service.candidates_out(db, service.candidates_for(db, payment))


@router.get("/{payment_id}/image")
def get_image(payment_id: int, db: Session = Depends(get_db)):
    payment = _get(db, payment_id)
    if not payment.image_path:
        raise HTTPException(status_code=404, detail="У оплаты нет фото")
    path = (settings.upload_dir / payment.image_path).resolve()
    if not path.is_relative_to(settings.upload_dir.resolve()) or not path.exists():
        raise HTTPException(status_code=404, detail="Фото не найдено")
    return FileResponse(path)


@router.patch("/{payment_id}", response_model=PaymentOut)
def update_payment(payment_id: int, body: PaymentUpdate, db: Session = Depends(get_db)):
    payment = _get(db, payment_id)
    fields = body.model_dump(exclude_unset=True)
    remember = fields.pop("remember_payer", True)
    for key, value in fields.items():
        setattr(payment, key, value)
    _check_refs(db, payment)
    # Если назначили ученика/родителя и статус явно не задан — считаем оплату подтверждённой.
    if ("student_id" in fields or "parent_id" in fields) and "status" not in fields:
        if payment.student_id or payment.parent_id:
            payment.status = "confirmed"
            payment.confidence = 1.0
    if payment.status == "confirmed" and not (payment.student_id or payment.parent_id):
        raise HTTPException(status_code=400, detail="Нельзя подтвердить оплату без ученика или родителя")
    if remember and payment.status == "confirmed":
        db.flush()
        service.remember_payer(db, payment)
    db.commit()
    db.refresh(payment)
    return service.payment_out(payment)


@router.delete("/{payment_id}", status_code=204)
def delete_payment(payment_id: int, db: Session = Depends(get_db)):
    payment = _get(db, payment_id)
    if payment.image_path:
        (settings.upload_dir / payment.image_path).unlink(missing_ok=True)
    db.delete(payment)
    db.commit()


def _check_refs(db: Session, payment: Payment) -> None:
    if payment.student_id and db.get(Student, payment.student_id) is None:
        raise HTTPException(status_code=400, detail="Ученик не найден")
    if payment.parent_id and db.get(Parent, payment.parent_id) is None:
        raise HTTPException(status_code=400, detail="Родитель не найден")

