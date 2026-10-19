from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Parent, Payment, Student
from ..schemas import MonthReport, ParentBrief, ParentUnassigned, ReportRow, StudentBrief
from .payments import _parse_month

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/month", response_model=MonthReport)
def month_report(month: str | None = None, db: Session = Depends(get_db)):
    """Сколько заплатил каждый ученик за месяц и сколько остался должен."""
    month = month or f"{date.today():%Y-%m}"
    year, mon = _parse_month(month)
    in_month = (
        extract("year", Payment.paid_at) == year,
        extract("month", Payment.paid_at) == mon,
        Payment.status == "confirmed",
    )
    paid_by_student: dict[int, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    for sid, total, count in db.execute(
        select(Payment.student_id, func.sum(Payment.amount), func.count())
        .where(*in_month, Payment.student_id.is_not(None))
        .group_by(Payment.student_id)
    ):
        paid_by_student[sid] = (total or 0.0, count)

    rows = []
    for s in db.scalars(select(Student).where(Student.active).order_by(Student.full_name)):
        paid, count = paid_by_student.get(s.id, (0.0, 0))
        rows.append(
            ReportRow(
                student=StudentBrief.model_validate(s),
                monthly_fee=s.monthly_fee,
                paid=paid,
                debt=max(0.0, s.monthly_fee - paid),
                payments=count,
            )
        )

    parent_only = [
        ParentUnassigned(parent=ParentBrief.model_validate(db.get(Parent, pid)), paid=total or 0.0)
        for pid, total in db.execute(
            select(Payment.parent_id, func.sum(Payment.amount))
            .where(*in_month, Payment.student_id.is_(None), Payment.parent_id.is_not(None))
            .group_by(Payment.parent_id)
        )
    ]

    total = db.scalar(select(func.sum(Payment.amount)).where(*in_month)) or 0.0
    needs_review = db.scalar(
        select(func.count()).select_from(Payment).where(Payment.status == "needs_review")
    )
    return MonthReport(
        month=month, total=total, rows=rows, parent_only=parent_only, needs_review=needs_review
    )
