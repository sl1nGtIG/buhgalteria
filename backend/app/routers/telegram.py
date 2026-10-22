"""Telegram-бот в режиме вебхука: Telegram сам присылает сообщения на сайт.

Нужен там, где фоновый процесс с опросом Telegram жить не может (Vercel).
"""

import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..auth import require_token
from ..config import settings
from ..telegram_bot import Bot, TelegramClient

router = APIRouter(prefix="/telegram", tags=["telegram"])
log = logging.getLogger("telegram")


def webhook_secret() -> str:
    # Секрет выводится из токена бота: отдельная настройка не нужна, подделать запрос нельзя.
    return hashlib.sha256(f"webhook:{settings.telegram_bot_token}".encode()).hexdigest()[:48]


def _require_bot() -> None:
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=404, detail="Telegram-бот не настроен: задайте TELEGRAM_BOT_TOKEN")


@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    _require_bot()
    if not hmac.compare_digest((x_telegram_bot_api_secret_token or "").encode(), webhook_secret().encode()):
        raise HTTPException(status_code=403, detail="Неверный секрет вебхука")
    update = await request.json()
    async with httpx.AsyncClient() as http:
        bot = Bot(TelegramClient(settings.telegram_bot_token, http), settings.telegram_allowed_chats)
        try:
            await bot.handle(update)
        except Exception:
            # Отвечаем 200 в любом случае, иначе Telegram будет бесконечно повторять сообщение.
            log.exception("Ошибка обработки сообщения Telegram")
    return {"ok": True}


@router.post("/setup", dependencies=[Depends(require_token)])
async def setup(request: Request):
    """Подключить вебхук к адресу этого сайта (нажимается из «Настроек»)."""
    _require_bot()
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://") and not base.startswith("http://localhost"):
        base = "https://" + base[len("http://"):]  # за прокси Vercel запрос приходит как http
    url = f"{base}/api/telegram/webhook"
    async with httpx.AsyncClient() as http:
        client = TelegramClient(settings.telegram_bot_token, http)
        try:
            await client.call(
                "setWebhook", url=url, secret_token=webhook_secret(),
                allowed_updates=["message", "callback_query"], drop_pending_updates=False,
            )
            me = await client.call("getMe")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Telegram не принял вебхук: {e}") from e
    return {"ok": True, "url": url, "bot": me.get("username")}
