"""Доступ к API.

- Telegram (если задан TELEGRAM_BOT_TOKEN): вход через бота, сессия подписывается секретом.
- Код доступа APP_TOKEN — по желанию, работает вместе с Telegram или вместо него.
- Если не задано ни то ни другое — доступ открыт (локальная разработка).
"""

import base64
import hashlib
import hmac
import time

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

SESSION_DAYS = 180


def auth_mode() -> str:
    if settings.telegram_bot_token:
        return "telegram"
    if settings.app_token:
        return "token"
    return "none"


def _secret() -> bytes:
    base = settings.session_secret or settings.telegram_bot_token or settings.app_token
    return hashlib.sha256(f"session:{base}".encode()).digest()


def _sign(payload: str) -> str:
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig[:24]).decode().rstrip("=")


def issue_session(user: User) -> str:
    """Токен вида «s.<id пользователя>.<срок>.<подпись>»; хранится на устройстве."""
    payload = f"{user.id}.{int(time.time()) + SESSION_DAYS * 86400}"
    return f"s.{payload}.{_sign(payload)}"


def user_from_session(db: Session, token: str) -> User | None:
    try:
        prefix, uid, exp, sig = token.split(".")
    except ValueError:
        return None
    payload = f"{uid}.{exp}"
    if prefix != "s" or not hmac.compare_digest(sig, _sign(payload)) or int(exp) < time.time():
        return None
    user = db.get(User, int(uid))
    return user if user and user.approved else None


def _supplied(authorization: str | None, token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:]
    return token or ""


def current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None, description="Для ссылок на картинки и выгрузку"),
    db: Session = Depends(get_db),
) -> User | None:
    """Проверяет доступ; возвращает пользователя Telegram (или None для входа по коду/без входа)."""
    mode = auth_mode()
    if mode == "none":
        return None
    supplied = _supplied(authorization, token)
    if settings.app_token and hmac.compare_digest(supplied.encode(), settings.app_token.encode()):
        return None
    if mode == "telegram" and supplied.startswith("s."):
        user = user_from_session(db, supplied)
        if user:
            return user
    raise HTTPException(status_code=401, detail="Нужно войти через Telegram" if mode == "telegram" else "Неверный код доступа")


# Совместимое имя: зависимость для защищённых маршрутов.
require_token = current_user
