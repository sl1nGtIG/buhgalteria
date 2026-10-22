"""Telegram-бот: присылаете фото/PDF чека или текст — бот фиксирует оплату и отвечает результатом.

Если система не уверена, бот присылает кнопки с вариантами «кому относится оплата».
Работает через long polling, отдельный адрес и вебхуки не нужны.
"""

import asyncio
import logging

import httpx

from . import accounts, intake, service
from .db import SessionLocal
from .extractor import SUPPORTED_TYPES
from .models import Payment, User
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

    def _is_allowed(self, chat_id: int) -> bool:
        if chat_id in self.allowed:
            return True
        with self.session_factory() as db:
            return chat_id in accounts.approved_telegram_ids(db)

    async def on_message(self, msg: dict) -> None:
        chat_id = msg["chat"]["id"]
        text = msg.get("text") or msg.get("caption") or ""
        if text.startswith(f"/start {accounts.START_PREFIX}") and msg.get("from"):
            await self.on_login(chat_id, text.split(accounts.START_PREFIX, 1)[1].strip(), msg["from"])
            return
        if text.startswith("/start") or text.startswith("/id"):
            await self.reply(
                chat_id,
                "Пришлите фото или PDF чека, скриншот выписки или текст вроде «Сидоров Саша 5000» — "
                f"я зафиксирую оплату.\n\nID этого чата: {chat_id}",
            )
            return
        if not await asyncio.to_thread(self._is_allowed, chat_id):
            await self.reply(
                chat_id,
                "Нет доступа. Войдите на сайте или в приложении через Telegram — "
                "владелец получит запрос и разрешит доступ.",
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

    async def on_login(self, chat_id: int, code: str, tg_user: dict) -> None:
        def run():
            with self.session_factory() as db:
                status, user = accounts.confirm(db, code, tg_user)
                boss = accounts.owner(db)
                return status, user and accounts.user_out(user), boss and boss.telegram_id

        status, user, owner_chat = await asyncio.to_thread(run)
        if status == "expired":
            await self.reply(chat_id, "Ссылка для входа устарела. Нажмите «Войти через Telegram» ещё раз.")
        elif status == "ok":
            await self.reply(chat_id, "✅ Вход выполнен. Вернитесь на сайт или в приложение.")
        else:
            await self.reply(chat_id, "⏳ Запрос на доступ отправлен владельцу. Как только он разрешит — вход завершится сам.")
            if owner_chat:
                who = user["name"] + (f" (@{user['username']})" if user["username"] else "")
                await self.reply(
                    owner_chat,
                    f"🔑 {who} просит доступ к бухгалтерии.",
                    {"inline_keyboard": [[{"text": "Разрешить", "callback_data": f"u:{user['id']}"}]]},
                )

    async def on_user_approve(self, cq: dict, user_id: int) -> None:
        def run():
            with self.session_factory() as db:
                boss = accounts.owner(db)
                if boss is None or boss.telegram_id != cq["from"]["id"]:
                    return None
                user = db.get(User, user_id)
                if user is None:
                    return None
                user.approved = True
                db.commit()
                return user.name, user.telegram_id

        result = await asyncio.to_thread(run)
        if result is None:
            await self.client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Нет прав")
            return
        name, tg_id = result
        await self.client.call("answerCallbackQuery", callback_query_id=cq["id"], text="Доступ разрешён")
        msg = cq.get("message") or {}
        await self.client.call(
            "editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
            text=f"✅ Доступ для {name} разрешён.",
        )
        await self.reply(tg_id, "✅ Владелец разрешил доступ. Вернитесь на сайт или в приложение.")

    async def on_callback(self, cq: dict) -> None:
        data = cq.get("data", "")
        if data.startswith("u:"):
            await self.on_user_approve(cq, int(data[2:]))
            return
        msg = cq.get("message") or {}
        chat_id = msg.get("chat", {}).get("id")
        if not await asyncio.to_thread(self._is_allowed, chat_id):
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
