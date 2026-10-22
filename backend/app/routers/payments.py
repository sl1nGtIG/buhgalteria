import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from .. import intake, service
from ..db import get_db
from ..models import Parent, Payment, Student
from ..schemas import CandidateOut, ManualPaymentIn, PaymentOut, PaymentUpdate, RecognizeResult

router = APIRouter(prefix="/payments", tags=["payments"])

def _get(db: Session, payment_id: int) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Оплата не найдена")
    return payment


@router.post("/recognize", response_model=RecognizeResult)
async def recognize(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    ocr_text: str | None = Form(default=None, description="Текст чека, прочитанный на устройстве"),
    db: Session = Depends(get_db),
):
    """Главный сценарий: прислали фото/PDF чека и/или текст — система сама фиксирует оплату."""
    content = await file.read() if file is not None else None
    try:
        return intake.process(
            db,
            content=content,
            media_type=file.content_type if file else None,
            text=text,
            ocr_text=ocr_text,
        )
    except intake.IntakeError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from e


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
    if payment.attachment_file is None:
        raise HTTPException(status_code=404, detail="У оплаты нет чека")
    return Response(
        content=payment.attachment_file.data,
        media_type=payment.attachment_file.media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.patch("/{payment_id}", response_model=PaymentOut)
def update_payment(payment_id: int, body: PaymentUpdate, db: Session = Depends(get_db)):
    payment = _get(db, payment_id)
    fields = body.model_dump(exclude_unset=True)
    remember = fields.pop("remember_payer", True)
    student_id = fields.pop("student_id", payment.student_id)
    parent_id = fields.pop("parent_id", payment.parent_id)
    reassigned = "student_id" in body.model_fields_set or "parent_id" in body.model_fields_set
    for key, value in fields.items():
        setattr(payment, key, value)
    payment.student_id, payment.parent_id = student_id, parent_id
    _check_refs(db, payment)
    if payment.status == "confirmed" and not (student_id or parent_id):
        raise HTTPException(status_code=400, detail="Нельзя подтвердить оплату без ученика или родителя")
    if reassigned and "status" not in fields:
        # Назначили ученика/родителя — оплата подтверждена, плательщик запомнен.
        return service.payment_out(service.assign_payment(db, payment, student_id, parent_id, remember))
    db.commit()
    db.refresh(payment)
    return service.payment_out(payment)


@router.delete("/{payment_id}", status_code=204)
def delete_payment(payment_id: int, db: Session = Depends(get_db)):
    payment = _get(db, payment_id)
    attachment_id = payment.attachment_id
    db.delete(payment)
    db.flush()
    service.delete_attachment_if_unused(db, attachment_id)
    db.commit()


def _check_refs(db: Session, payment: Payment) -> None:
    if payment.student_id and db.get(Student, payment.student_id) is None:
        raise HTTPException(status_code=400, detail="Ученик не найден")
    if payment.parent_id and db.get(Parent, payment.parent_id) is None:
        raise HTTPException(status_code=400, detail="Родитель не найден")

