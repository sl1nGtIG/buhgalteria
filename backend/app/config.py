import os
from pathlib import Path


def _database_url(default: str) -> str:
    """DATABASE_URL или POSTGRES_URL (так их называет интеграция Neon на Vercel)."""
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or default
    # SQLAlchemy по умолчанию ищет драйвер psycopg2, у нас psycopg 3.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    """Настройки из переменных окружения."""

    def __init__(self) -> None:
        # На Vercel файловая система доступна только в /tmp и не сохраняется между запусками.
        self.on_vercel = bool(os.getenv("VERCEL"))
        default_data = "/tmp/buhgalteria" if self.on_vercel else Path(__file__).resolve().parents[2] / "data"
        base = Path(os.getenv("DATA_DIR", default_data))
        self.data_dir = base
        self.database_url = _database_url(f"sqlite:///{base / 'buhgalteria.db'}")
        self.persistent_storage = not (self.on_vercel and self.database_url.startswith("sqlite"))
        # Код доступа к API. Пусто — авторизация выключена (только для локальной разработки).
        self.app_token = os.getenv("APP_TOKEN", "")
        # Секрет для подписи сессий входа через Telegram (по умолчанию выводится из токена бота).
        self.session_secret = os.getenv("SESSION_SECRET", "")
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
        self.anthropic_enabled = bool(
            os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        )
        # Порог уверенности, выше которого оплата фиксируется автоматически.
        self.auto_confirm_score = float(os.getenv("AUTO_CONFIRM_SCORE", "0.85"))
        # Vercel не принимает запросы больше 4,5 МБ.
        default_max_mb = 4 if self.on_vercel else 10
        self.max_upload_bytes = int(float(os.getenv("MAX_UPLOAD_MB", default_max_mb)) * 1024 * 1024)
        # Telegram-бот (необязательно): токен от @BotFather и ID чатов, которым разрешено присылать чеки.
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_allowed_chats = {
            int(x) for x in os.getenv("TELEGRAM_ALLOWED_CHATS", "").replace(";", ",").split(",") if x.strip()
        }
        # polling — бот сам опрашивает Telegram (обычный сервер); webhook — Telegram присылает
        # обновления на сайт (Vercel, где фоновые процессы не живут).
        self.telegram_mode = os.getenv("TELEGRAM_MODE", "webhook" if self.on_vercel else "polling")
        self.frontend_dist = Path(
            os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist")
        )


settings = Settings()
