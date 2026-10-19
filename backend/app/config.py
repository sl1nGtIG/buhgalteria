import os
from pathlib import Path


class Settings:
    """Настройки из переменных окружения."""

    def __init__(self) -> None:
        base = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
        self.data_dir = base
        self.database_url = os.getenv("DATABASE_URL", f"sqlite:///{base / 'buhgalteria.db'}")
        self.upload_dir = Path(os.getenv("UPLOAD_DIR", base / "uploads"))
        # Код доступа к API. Пусто — авторизация выключена (только для локальной разработки).
        self.app_token = os.getenv("APP_TOKEN", "")
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
        self.anthropic_enabled = bool(
            os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        )
        # Порог уверенности, выше которого оплата фиксируется автоматически.
        self.auto_confirm_score = float(os.getenv("AUTO_CONFIRM_SCORE", "0.85"))
        self.frontend_dist = Path(
            os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist")
        )


settings = Settings()
