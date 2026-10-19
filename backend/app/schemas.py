from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ParentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    phone: str | None = None


class StudentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    group_name: str | None = None


class ParentIn(BaseModel):
    full_name: str = Field(min_length=2)
    phone: str | None = None
    notes: str | None = None
    student_ids: list[int] = []


class ParentOut(ParentBrief):
    notes: str | None = None
    students: list[StudentBrief] = []


class StudentIn(BaseModel):
    full_name: str = Field(min_length=2)
    group_name: str | None = None
    monthly_fee: float = 0
    notes: str | None = None
    active: bool = True
    parent_ids: list[int] = []
    # Новых родителей можно создать сразу вместе с учеником.
    new_parents: list[ParentIn] = []


class StudentOut(StudentBrief):
    monthly_fee: float
    notes: str | None = None
    active: bool
    parents: list[ParentBrief] = []


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: float | None
    currency: str
    paid_at: date | None
    payer_name: str | None
    payer_phone: str | None
    purpose: str | None
    bank: str | None
    operation_id: str | None
    raw_text: str | None
    source: str
    # Вложение чека: "image", "pdf" или None
    attachment: str | None = None
    status: str
    confidence: float
    created_at: datetime
    student: StudentBrief | None
    parent: ParentBrief | None


class CandidateOut(BaseModel):
    student: StudentBrief | None
    parent: ParentBrief | None
    score: float
    reasons: list[str]


class RecognizeItem(BaseModel):
    payment: PaymentOut
    candidates: list[CandidateOut]
    auto_confirmed: bool
    duplicate_of: int | None = None
    message: str


class RecognizeResult(BaseModel):
    items: list[RecognizeItem]
    message: str


class PaymentUpdate(BaseModel):
    amount: float | None = None
    paid_at: date | None = None
    student_id: int | None = None
    parent_id: int | None = None
    purpose: str | None = None
    status: str | None = Field(default=None, pattern="^(confirmed|needs_review)$")
    # Запомнить плательщика для автоматического распознавания в будущем.
    remember_payer: bool = True


class ManualPaymentIn(BaseModel):
    amount: float
    paid_at: date
    student_id: int | None = None
    parent_id: int | None = None
    purpose: str | None = None


class ReportRow(BaseModel):
    student: StudentBrief
    monthly_fee: float
    paid: float
    debt: float
    payments: int


class ParentUnassigned(BaseModel):
    parent: ParentBrief
    paid: float


class MonthReport(BaseModel):
    month: str
    total: float
    rows: list[ReportRow]
    parent_only: list[ParentUnassigned]
    needs_review: int
