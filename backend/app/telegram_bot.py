"""Telegram-бот: присылаете фото/PDF чека или текст — бот фиксирует оплату и отвечает результатом.

Если система не уверена, бот присылает кнопки с вариантами «кому относится оплата».
Работает через long polling, отдельный адрес и вебхуки не нужны.
"""

import asyncio
import logging

import httpx

from . import intake, service
from .db import SessionLocal
from .extractor import SUPPORTED_TYPES
from .models import Payment
from .money import fmt_money
from .schemas import PaymentOut, RecognizeItem

log = logging.getLogger("telegram")


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(self, token: str, http: httpx.AsyncClient):
        self.base = f"https://api.telegram.org/bot{token}"
        self.files = f"https://api.telegram.org/file/bot{token}"
        self.http = http

    async def call(self, method: str, **params):
        r = await self.http.post(f"{self.base}/{method}", json=params, timeout=70)
        data = r.json()
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description')}")
        return data["result"]

    async def download(self, file_id: str) -> bytes:
        info = await self.call("getFile", file_id=file_id)
        r = await self.http.get(f"{self.files}/{info['file_path']}", timeout=60)
        r.raise_for_status()
        return r.content


def describe(p: PaymentOut) -> str:
    date = p.paid_at.strftime("%d.%m.%Y") if p.paid_at else "без даты"
    lines = [f"{fmt_money(p.amount)} · {date}"]
    if p.student:
        lines.append(p.student.full_name + (f" (родитель: {p.parent.full_name})" if p.parent else ""))
    elif p.parent:
        lines.append(f"{p.parent.full_name} (родитель)")
    if p.payer_name:
        lines.append(f"Плательщик: {p.payer_name}")
    return "\n".join(lines)


def item_reply(item: RecognizeItem) -> tuple[str, dict | None]:
    p = item.payment
    if item.duplicate_of:
        return f"↩️ Уже была загружена ранее\n{describe(p)}", None
    if p.status == "confirmed":
        return f"✅ Оплата зафиксирована\n{describe(p)}", None
    buttons = []
    for c in item.candidates[:5]:
        label = c.student.full_name if c.student else f"{c.parent.full_name} (родитель)"
        sid = c.student.id if c.student else 0
        pid = c.parent.id if c.parent else 0
        buttons.append([{"text": label, "callback_data": f"a:{p.id}:{sid}:{pid}"}])
    hint = "Кому относится оплата?" if buttons else "Плательщик не найден — привяжите оплату в приложении."
    keyboard = {"inline_keyboard": buttons} if buttons else None
    return f"⚠️ Нужно подтвердить\n{describe(p)}\n\n{hint}", keyboard


class Bot:
    def __init__(self, client: TelegramClient, allowed_chats: set[int], session_factory=SessionLocal):
        self.client = client
        self.allowed = allowed_chats
        self.session_factory = session_factory
        self.offset = 0

    async def run(self) -> None:
        log.info("Telegram-бот запущен")
        delay = 1
        while True:
            try:
                updates = await self.client.call(
                    "getUpdates", offset=self.offset, timeout=50, allowed_updates=["message", "callback_query"]
                )
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as e:  # сеть, неверный токен и т.п. — пробуем снова с паузой
                log.warning("Telegram getUpdates: %s", e)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            for update in updates:
                self.offset = update["update_id"] + 1
                try:
                    await self.handle(update)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Ошибка обработки сообщения Telegram")

    async def handle(self, update: dict) -> None:
        if "callback_query" in update:
            await self.on_callback(update["callback_query"])
        elif "message" in update:
            await self.on_message(update["message"])

    async def reply(self, chat_id: int, text: str, keyboard: dict | None = None, reply_to: int | None = None):
        params = {"chat_id": chat_id, "text": text}
        if keyboard:
            params["reply_markup"] = keyboard
        if reply_to:
            params["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        await self.client.call("sendMessage", **params)

    async def on_message(self, msg: dict) -> None:
        chat_id = msg["chat"]["id"]
        text = msg.get("text") or msg.get("caption") or ""
        if text.startswith("/start") or text.startswith("/id"):
            await self.reply(
                chat_id,
                "Пришлите фото или PDF чека, скриншот выписки или текст вроде «Сидоров Саша 5000» — "
                f"я зафиксирую оплату.\n\nID этого чата: {chat_id}",
            )
            return
        if chat_id not in self.allowed:
            await self.reply(
                chat_id,
                f"Нет доступа. Попросите администратора добавить ID чата {chat_id} "
                "в настройку TELEGRAM_ALLOWED_CHATS.",
            )
            return

        file_id, media_type = None, None
        if msg.get("photo"):
            file_id, media_type = msg["photo"][-1]["file_id"], "image/jpeg"
        elif msg.get("document"):
            doc = msg["document"]
            if doc.get("mime_type") not in SUPPORTED_TYPES:
                await self.reply(chat_id, "Пришлите фото, скриншот или PDF.", reply_to=msg["message_id"])
                return
            file_id, media_type = doc["file_id"], doc["mime_type"]
        elif not text:
            return

        await self.client.call("sendChatAction", chat_id=chat_id, action="typing")
        content = await self.client.download(file_id) if file_id else None
        try:
            replies = await asyncio.to_thread(self._process, content, media_type, text)
        except intake.IntakeError as e:
            await self.reply(chat_id, f"❌ {e}", reply_to=msg["message_id"])
            return
        for reply_text, keyboard in replies:
            await self.reply(chat_id, reply_text, keyboard, reply_to=msg["message_id"])

    def _process(self, content, media_type, text) -> list[tuple[str, dict | None]]:
        with self.session_factory() as db:
            result = intake.process(db, content=content, media_type=media_type, text=text, source="telegram")
            replies = [item_reply(i) for i in result.items]
        if len(result.items) > 1:
            replies.insert(0, (result.message, None))
        return replies

    async def on_callback(self, cq: dict) -> None:
        msg = cq.get("message") or {}
        chat_id = msg.get("chat", {}).get("id")
        if chat_id not in self.allowed:
            await self.client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Нет доступа")
            return
        try:
            _, payment_id, student_id, parent_id = cq.get("data", "").split(":")
            text = await asyncio.to_thread(
                self._assign, int(payment_id), int(student_id) or None, int(parent_id) or None
            )
        except (ValueError, LookupError) as e:
            await self.client.call("answerCallbackQuery", callback_query_id=cq["id"], text=str(e) or "Ошибка")
            return
        await self.client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Готово")
        await self.client.call("editMessageText", chat_id=chat_id, message_id=msg["message_id"], text=text)

    def _assign(self, payment_id: int, student_id: int | None, parent_id: int | None) -> str:
        with self.session_factory() as db:
            payment = db.get(Payment, payment_id)
            if payment is None:
                raise LookupError("Оплата уже удалена")
            payment = service.assign_payment(db, payment, student_id, parent_id)
            return f"✅ Оплата зафиксирована\n{describe(service.payment_out(payment))}"


async def start(token: str, allowed_chats: set[int]) -> None:
    async with httpx.AsyncClient() as http:
        await Bot(TelegramClient(token, http), allowed_chats).run()
