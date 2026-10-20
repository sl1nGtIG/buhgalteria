"""Фиксация распознанной оплаты: сопоставление, проверка дублей, обучение на подтверждениях."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import matcher
from .config import settings
from .extractor import ReceiptData
from .models import Attachment, Parent, PayerAlias, Payment, Student
from .schemas import CandidateOut, ParentBrief, PaymentOut, StudentBrief


def payment_out(p: Payment) -> PaymentOut:
    out = PaymentOut.model_validate(p)
    if p.attachment_id:
        out.attachment = "pdf" if p.attachment_file.media_type == "application/pdf" else "image"
    return out


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def load_people(db: Session):
    students = db.scalars(
        select(Student).options(selectinload(Student.parents).selectinload(Parent.students))
    ).all()
    parents = db.scalars(select(Parent).options(selectinload(Parent.students))).all()
    aliases = db.scalars(select(PayerAlias)).all()
    return students, parents, aliases


def candidates_for(db: Session, payment: Payment, student_name: str | None = None) -> list[matcher.Candidate]:
    students, parents, aliases = load_people(db)
    data = matcher.MatchInput(
        payer_name=payment.payer_name,
        payer_phone=payment.payer_phone,
        purpose=payment.purpose,
        student_name=student_name,
        amount=payment.amount,
    )
    return matcher.find_candidates(data, students, parents, aliases)


def candidates_out(db: Session, cands: list[matcher.Candidate], limit: int = 5) -> list[CandidateOut]:
    result = []
    for c in cands[:limit]:
        s = db.get(Student, c.student_id) if c.student_id else None
        p = db.get(Parent, c.parent_id) if c.parent_id else None
        result.append(
            CandidateOut(
                student=StudentBrief.model_validate(s) if s else None,
                parent=ParentBrief.model_validate(p) if p else None,
                score=c.score,
                reasons=c.reasons,
            )
        )
    return result


def find_duplicate(db: Session, data: ReceiptData, paid_at: date | None) -> Payment | None:
    if data.operation_id:
        dup = db.scalar(select(Payment).where(Payment.operation_id == data.operation_id))
        if dup:
            return dup
    # Без номера операции сравниваем сумму, дату и плательщика (или текст, если плательщика нет).
    who = matcher.normalize(data.payer_name or data.purpose)
    if data.amount and paid_at and who:
        rows = db.scalars(
            select(Payment).where(Payment.amount == data.amount, Payment.paid_at == paid_at)
        ).all()
        for row in rows:
            if matcher.normalize(row.payer_name or row.purpose) == who:
                return row
    return None


def record_payment(
    db: Session,
    data: ReceiptData,
    *,
    source: str,
    raw_text: str | None = None,
    attachment_id: int | None = None,
):
    """Создаёт оплату и пытается сама привязать её к ученику/родителю.

    Возвращает (payment, candidates, auto_confirmed, duplicate).
    """
    paid_at = _parse_date(data.date) or date.today()
    duplicate = find_duplicate(db, data, paid_at)
    if duplicate:
        return duplicate, [], False, duplicate

    payment = Payment(
        amount=data.amount,
        currency=data.currency or "RUB",
        paid_at=paid_at,
        payer_name=data.payer_name,
        payer_phone=data.payer_phone,
        purpose=data.purpose,
        bank=data.bank,
        operation_id=data.operation_id,
        raw_text=raw_text,
        source=source,
        attachment_id=attachment_id,
        status="needs_review",
    )
    cands = candidates_for(db, payment, data.student_name)
    chosen = matcher.decide(cands, settings.auto_confirm_score) if data.amount else None
    if chosen:
        payment.student_id = chosen.student_id
        payment.parent_id = chosen.parent_id
        payment.status = "confirmed"
        payment.confidence = chosen.score
    elif cands:
        payment.confidence = cands[0].score

    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment, cands, chosen is not None, None


def remember_payer(db: Session, payment: Payment) -> None:
    """Запоминает написание плательщика, чтобы в следующий раз привязать автоматически."""
    alias = matcher.normalize(payment.payer_name)
    if not alias or not (payment.student_id or payment.parent_id):
        return
    row = db.scalar(select(PayerAlias).where(PayerAlias.alias == alias))
    if row is None:
        row = PayerAlias(alias=alias)
        db.add(row)
    row.student_id = payment.student_id
    row.parent_id = payment.parent_id
    # Родитель платит за нескольких детей — по одному плательщику ребёнка не угадать.
    parent = db.get(Parent, payment.parent_id) if payment.parent_id else None
    if parent and len(parent.students) > 1:
        row.student_id = None


def assign_payment(
    db: Session, payment: Payment, student_id: int | None, parent_id: int | None, remember: bool = True
) -> Payment:
    """Ручная привязка оплаты: подтверждает её и запоминает плательщика."""
    payment.student_id = student_id
    payment.parent_id = parent_id
    if student_id or parent_id:
        payment.status = "confirmed"
        payment.confidence = 1.0
        if remember:
            db.flush()
            remember_payer(db, payment)
    else:
        payment.status = "needs_review"
    db.commit()
    db.refresh(payment)
    return payment


def delete_attachment_if_unused(db: Session, attachment_id: int | None, except_id: int | None = None) -> None:
    """Один файл может принадлежать нескольким оплатам (выписка) — удаляем, когда он больше не нужен."""
    if not attachment_id:
        return
    q = select(Payment.id).where(Payment.attachment_id == attachment_id)
    if except_id is not None:
        q = q.where(Payment.id != except_id)
    if db.scalar(q.limit(1)) is None:
        attachment = db.get(Attachment, attachment_id)
        if attachment is not None:
            db.delete(attachment)
