from datetime import date, datetime

from sqlalchemy import BigInteger, Column, Date, DateTime, Float, ForeignKey, LargeBinary, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

parent_student = Table(
    "parent_student",
    Base.metadata,
    Column("parent_id", ForeignKey("parents.id", ondelete="CASCADE"), primary_key=True),
    Column("student_id", ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    group_name: Mapped[str | None] = mapped_column(String(100))
    monthly_fee: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)

    parents: Mapped[list["Parent"]] = relationship(
        secondary=parent_student, back_populates="students"
    )


class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    students: Mapped[list[Student]] = relationship(
        secondary=parent_student, back_populates="parents"
    )


class PayerAlias(Base):
    """Запомненное написание плательщика из чеков → кому относится оплата.

    Создаётся, когда человек вручную подтверждает оплату, чтобы в следующий раз
    такой же чек распознавался автоматически.
    """

    __tablename__ = "payer_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("parents.id", ondelete="CASCADE"))
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))


class Attachment(Base):
    """Файл чека. Хранится в базе, чтобы работать и на серверах без постоянного диска (Vercel)."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_type: Mapped[str] = mapped_column(String(50))
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)  # не тянуть файл в списки оплат
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    paid_at: Mapped[date | None] = mapped_column(Date, index=True)
    payer_name: Mapped[str | None] = mapped_column(String(200))
    payer_phone: Mapped[str | None] = mapped_column(String(50))
    purpose: Mapped[str | None] = mapped_column(Text)
    bank: Mapped[str | None] = mapped_column(String(100))
    operation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    # photo | text | manual
    source: Mapped[str] = mapped_column(String(20))
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachments.id", ondelete="SET NULL"), index=True
    )
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id", ondelete="SET NULL"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("parents.id", ondelete="SET NULL"))
    # confirmed | needs_review
    status: Mapped[str] = mapped_column(String(20), default="needs_review", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    student: Mapped[Student | None] = relationship()
    parent: Mapped[Parent | None] = relationship()
    attachment_file: Mapped[Attachment | None] = relationship()


class User(Base):
    """Пользователь, вошедший через Telegram. Первый вошедший становится владельцем."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    username: Mapped[str | None] = mapped_column(String(100))
    is_owner: Mapped[bool] = mapped_column(default=False)
    # Владелец разрешает доступ остальным.
    approved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LoginCode(Base):
    """Одноразовый код входа: сайт показывает ссылку на бота, бот подтверждает код."""

    __tablename__ = "login_codes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
