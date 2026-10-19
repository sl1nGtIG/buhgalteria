import asyncio
import contextlib
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_token
from .config import settings
from .db import Base, engine
from .routers import payments, people, reports

logging.basicConfig(level=logging.INFO)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if settings.telegram_bot_token:
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
    if not settings.app_token:
        logging.getLogger("app").warning("APP_TOKEN не задан — API открыт без пароля!")
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
            "auth_required": bool(settings.app_token),
            "photo_recognition": settings.anthropic_enabled,
            "telegram_bot": bool(settings.telegram_bot_token),
        }

    protected = [Depends(require_token)]
    for r in (people.router, payments.router, reports.router):
        app.include_router(r, prefix="/api", dependencies=protected)

    dist = settings.frontend_dist
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = (dist / path).resolve()
            if path and file.is_file() and file.is_relative_to(dist.resolve()):
                return FileResponse(file)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
