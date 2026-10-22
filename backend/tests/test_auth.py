import asyncio

import pytest

from app.config import settings
from app.routers import auth as auth_router
from app.telegram_bot import Bot
from tests.test_telegram import FakeClient

OWNER = {"id": 1001, "first_name": "Игорь", "username": "igor"}
STAFF = {"id": 2002, "first_name": "Анна", "last_name": "Бух"}


@pytest.fixture()
def tg(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123:ABC")

    async def fake_prepare(request):
        return "buh_bot"

    monkeypatch.setattr(auth_router, "_prepare_bot", fake_prepare)
    return Bot(FakeClient(), allowed_chats=set())


def press_start(bot, user, code):
    update = {"message": {"message_id": 1, "chat": {"id": user["id"]}, "from": user,
                          "text": f"/start login_{code}"}}
    asyncio.run(bot.handle(update))


def login(client, bot, user):
    start = client.post("/api/auth/start").json()
    assert start["url"] == f"https://t.me/buh_bot?start=login_{start['code']}"
    assert client.get("/api/auth/poll", params={"code": start["code"]}).json()["status"] == "waiting"
    press_start(bot, user, start["code"])
    return start["code"], client.get("/api/auth/poll", params={"code": start["code"]}).json()


def test_api_closed_until_login_and_first_user_is_owner(client, tg):
    assert client.get("/api/students").status_code == 401
    _, r = login(client, tg, OWNER)
    assert r["status"] == "ok" and r["user"]["is_owner"]
    headers = {"Authorization": f"Bearer {r['token']}"}
    assert client.get("/api/students", headers=headers).status_code == 200
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["user"]["name"] == "Игорь" and me["mode"] == "telegram"
    assert tg.client.sent()[-1]["text"].startswith("✅ Вход выполнен")


def test_second_user_waits_for_owner_approval(client, tg):
    _, owner = login(client, tg, OWNER)
    code, r = login(client, tg, STAFF)
    assert r["status"] == "pending"

    # Владельцу пришёл запрос с кнопкой «Разрешить».
    request = next(p for p in tg.client.sent() if p["chat_id"] == OWNER["id"] and "reply_markup" in p)
    button = request["reply_markup"]["inline_keyboard"][0][0]
    cq = {"id": "cb", "data": button["callback_data"], "from": STAFF,
          "message": {"message_id": 9, "chat": {"id": OWNER["id"]}}}
    asyncio.run(tg.handle({"callback_query": cq}))  # нажал не владелец — ничего не меняется
    assert client.get("/api/auth/poll", params={"code": code}).json()["status"] == "pending"

    cq["from"] = OWNER
    asyncio.run(tg.handle({"callback_query": cq}))
    r = client.get("/api/auth/poll", params={"code": code}).json()
    assert r["status"] == "ok" and not r["user"]["is_owner"]

    staff_headers = {"Authorization": f"Bearer {r['token']}"}
    owner_headers = {"Authorization": f"Bearer {owner['token']}"}
    assert client.get("/api/auth/users", headers=staff_headers).status_code == 403
    users = client.get("/api/auth/users", headers=owner_headers).json()
    assert [u["name"] for u in users] == ["Игорь", "Анна Бух"]


def test_code_is_single_use_and_tampered_token_rejected(client, tg):
    code, r = login(client, tg, OWNER)
    assert client.get("/api/auth/poll", params={"code": code}).json()["status"] == "expired"
    bad = r["token"][:-2] + ("AA" if not r["token"].endswith("AA") else "BB")
    assert client.get("/api/students", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_approved_user_can_send_receipts_to_bot(client, tg):
    login(client, tg, OWNER)
    msg = {"message": {"message_id": 2, "chat": {"id": OWNER["id"]}, "from": OWNER, "text": "Петров 500"}}
    asyncio.run(tg.handle(msg))
    assert not tg.client.sent()[-1]["text"].startswith("Нет доступа")
