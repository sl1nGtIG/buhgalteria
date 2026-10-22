import asyncio
import contextlib
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import ocr
from .auth import auth_mode, require_token
from .config import settings
from .db import Base, engine
from .routers import auth, payments, people, reports, telegram

logging.basicConfig(level=logging.INFO)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if settings.telegram_bot_token and settings.telegram_mode == "polling":
        from . import telegram_bot

        task = asyncio.create_task(
            telegram_bot.start(settings.telegram_bot_token, settings.telegram_allowed_chats)
        )
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    if auth_mode() == "none":
        logging.getLogger("app").warning("Вход не настроен (нет TELEGRAM_BOT_TOKEN и APP_TOKEN) — API открыт всем!")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)

    app = FastAPI(title="Бухгалтерия оплат", version="0.2.0", lifespan=lifespan)
    # Приложение Android (Capacitor) и сайт ходят с разных origin; авторизация — по заголовку.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "auth_required": auth_mode() != "none",
            "auth_mode": auth_mode(),
            # Фото всегда можно распознать на устройстве; это — дополнительные способы на сервере.
            "ai_recognition": settings.anthropic_enabled,
            "server_ocr": ocr.tesseract_available(),
            "telegram_bot": bool(settings.telegram_bot_token),
            "telegram_mode": settings.telegram_mode,
            "persistent_storage": settings.persistent_storage,
            "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
        }

    protected = [Depends(require_token)]
    for r in (people.router, payments.router, reports.router):
        app.include_router(r, prefix="/api", dependencies=protected)
    # Вебхук проверяет собственный секрет Telegram, а /setup защищён кодом доступа внутри.
    app.include_router(telegram.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")

    dist = settings.frontend_dist
    if dist.is_dir():
        # Собранный сайт; на Vercel эти файлы раздаются прямо с CDN.
        app.frontend("/", directory=dist, fallback="index.html")

    return app


app = create_app()
