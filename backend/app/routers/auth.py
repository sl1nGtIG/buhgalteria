import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import accounts
from ..auth import auth_mode, current_user
from ..config import settings
from ..db import get_db
from ..models import User
from ..telegram_bot import TelegramClient
from .telegram import public_base_url, webhook_secret

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("auth")

_bot_username: str | None = None


async def _prepare_bot(request: Request) -> str:
    """Имя бота для ссылки; на Vercel заодно включает вебхук, если он ещё не настроен."""
    global _bot_username
    async with httpx.AsyncClient() as http:
        client = TelegramClient(settings.telegram_bot_token, http)
        if _bot_username is None:
            _bot_username = (await client.call("getMe"))["username"]
        if settings.telegram_mode == "webhook":
            url = f"{public_base_url(request)}/api/telegram/webhook"
            info = await client.call("getWebhookInfo")
            if info.get("url") != url:
                await client.call(
                    "setWebhook", url=url, secret_token=webhook_secret(),
                    allowed_updates=["message", "callback_query"],
                )
    return _bot_username


@router.post("/start")
async def start(request: Request, db: Session = Depends(get_db)):
    """Начать вход: вернуть ссылку на бота с одноразовым кодом."""
    if auth_mode() != "telegram":
        raise HTTPException(status_code=400, detail="Вход через Telegram не настроен: задайте TELEGRAM_BOT_TOKEN")
    try:
        username = await _prepare_bot(request)
    except Exception as e:
        log.warning("Telegram недоступен: %s", e)
        raise HTTPException(status_code=502, detail="Не удалось связаться с Telegram. Проверьте токен бота.") from e
    code = accounts.new_code(db)
    return {"code": code, "url": f"https://t.me/{username}?start={accounts.START_PREFIX}{code}"}


@router.get("/poll")
def poll(code: str, db: Session = Depends(get_db)):
    """Сайт/приложение опрашивает, подтвердил ли пользователь вход в боте."""
    return accounts.poll(db, code)


@router.get("/me")
def me(user: User | None = Depends(current_user)):
    return {"mode": auth_mode(), "user": accounts.user_out(user) if user else None}


def _require_owner(user: User | None = Depends(current_user)) -> User:
    if user is None or not user.is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может управлять доступом")
    return user


@router.get("/users")
def list_users(_: User = Depends(_require_owner), db: Session = Depends(get_db)):
    return [accounts.user_out(u) for u in db.scalars(select(User).order_by(User.created_at))]


@router.post("/users/{user_id}/approve")
def approve(user_id: int, _: User = Depends(_require_owner), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.approved = True
    db.commit()
    return accounts.user_out(user)


@router.delete("/users/{user_id}", status_code=204)
def remove(user_id: int, me_: User = Depends(_require_owner), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == me_.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")
    db.delete(user)
    db.commit()
