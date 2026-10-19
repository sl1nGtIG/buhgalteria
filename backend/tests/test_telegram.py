import asyncio

from app import extractor
from app.telegram_bot import Bot
from tests.test_api import receipt, seed

CHAT = 777


class FakeClient:
    def __init__(self):
        self.calls = []

    async def call(self, method, **params):
        self.calls.append((method, params))
        return {}

    async def download(self, file_id):
        return b"\xff\xd8fake"

    def sent(self):
        return [p for m, p in self.calls if m == "sendMessage"]


def run(bot, update):
    asyncio.run(bot.handle(update))


def message(**kw):
    return {"message": {"message_id": 1, "chat": {"id": CHAT}, **kw}}


def test_unknown_chat_is_rejected(client):
    bot = Bot(FakeClient(), allowed_chats=set())
    run(bot, message(text="Сидоров Саша 5000"))
    assert "Нет доступа" in bot.client.sent()[0]["text"]
    assert client.get("/api/payments").json() == []


def test_text_payment_confirmed(client):
    seed(client)
    bot = Bot(FakeClient(), allowed_chats={CHAT})
    run(bot, message(text="Сидоров Саша 5000"))
    reply = bot.client.sent()[0]["text"]
    assert reply.startswith("✅") and "Сидоров Александр" in reply
    assert client.get("/api/payments").json()[0]["source"] == "telegram"


def test_photo_needs_review_then_button(client, monkeypatch):
    _, masha = seed(client)
    rec = receipt(amount=4000, date="2026-10-10", purpose="Кузнецова", operation_id="T1")
    monkeypatch.setattr(extractor, "extract_from_file", lambda c, mt: [rec.model_copy()])
    bot = Bot(FakeClient(), allowed_chats={CHAT})
    run(bot, message(photo=[{"file_id": "small"}, {"file_id": "big"}], caption=""))

    sent = bot.client.sent()[0]
    assert sent["text"].startswith("⚠️")
    button = next(
        b[0] for b in sent["reply_markup"]["inline_keyboard"] if b[0]["text"] == "Кузнецова Мария"
    )
    run(bot, {"callback_query": {
        "id": "cb", "data": button["callback_data"],
        "message": {"message_id": 5, "chat": {"id": CHAT}},
    }})
    edited = [p for m, p in bot.client.calls if m == "editMessageText"][0]
    assert edited["text"].startswith("✅")
    payment = client.get("/api/payments").json()[0]
    assert payment["status"] == "confirmed" and payment["student"]["id"] == masha["id"]


def test_unreadable_text_reports_error(client):
    bot = Bot(FakeClient(), allowed_chats={CHAT})
    run(bot, message(text="привет"))
    assert bot.client.sent()[0]["text"].startswith("❌")


def test_client_download_uses_file_path():
    import httpx

    from app.telegram_bot import TelegramClient

    def handler(request: httpx.Request):
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "photos/1.jpg"}})
        assert request.url.path == "/file/botTOKEN/photos/1.jpg"
        return httpx.Response(200, content=b"jpeg")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await TelegramClient("TOKEN", http).download("abc")

    assert asyncio.run(go()) == b"jpeg"
