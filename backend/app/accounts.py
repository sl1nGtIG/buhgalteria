"""Вход через Telegram-бота: одноразовый код → пользователь нажимает Start в боте → сессия.

Работает одинаково на компьютере и в Android-приложении: никаких виджетов и всплывающих окон,
нужна только ссылка вида t.me/<бот>?start=login_<код>.
"""

import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import issue_session
from .models import LoginCode, User

CODE_TTL = timedelta(minutes=10)
START_PREFIX = "login_"


def new_code(db: Session) -> str:
    # Чистим старые коды, чтобы таблица не росла.
    db.query(LoginCode).filter(LoginCode.created_at < datetime.now() - CODE_TTL).delete()
    code = secrets.token_urlsafe(18)
    db.add(LoginCode(code=code))
    db.commit()
    return code


def _display_name(tg: dict) -> str:
    name = " ".join(filter(None, [tg.get("first_name"), tg.get("last_name")])).strip()
    return name or tg.get("username") or str(tg["id"])


def confirm(db: Session, code: str, tg: dict) -> tuple[str, User | None]:
    """Бот получил /start login_<код> от пользователя Telegram.

    Возвращает статус: ok — вошёл; pending — ждёт разрешения владельца; expired — код устарел.
    """
    row = db.get(LoginCode, code)
    if row is None or row.created_at < datetime.now() - CODE_TTL:
        return "expired", None
    user = db.scalar(select(User).where(User.telegram_id == tg["id"]))
    if user is None:
        is_first = db.scalar(select(func.count()).select_from(User)) == 0
        user = User(telegram_id=tg["id"], is_owner=is_first, approved=is_first)
        db.add(user)
    user.name = _display_name(tg)
    user.username = tg.get("username")
    db.flush()
    row.user_id = user.id
    db.commit()
    return ("ok" if user.approved else "pending"), user


def poll(db: Session, code: str) -> dict:
    row = db.get(LoginCode, code)
    if row is None or row.created_at < datetime.now() - CODE_TTL:
        return {"status": "expired"}
    if row.user_id is None:
        return {"status": "waiting"}
    user = db.get(User, row.user_id)
    if user is None or not user.approved:
        return {"status": "pending"}
    db.delete(row)  # код одноразовый
    db.commit()
    return {"status": "ok", "token": issue_session(user), "user": user_out(user)}


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "is_owner": user.is_owner,
        "approved": user.approved,
    }


def owner(db: Session) -> User | None:
    return db.scalar(select(User).where(User.is_owner))


def approved_telegram_ids(db: Session) -> set[int]:
    return set(db.scalars(select(User.telegram_id).where(User.approved)))
