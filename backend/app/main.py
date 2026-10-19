from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_token
from .config import settings
from .db import Base, engine
from .routers import payments, people, reports


def create_app() -> FastAPI:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)

    app = FastAPI(title="Бухгалтерия оплат", version="0.1.0")
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
