import os
import tempfile

import pytest

# Настройки читаются при импорте, поэтому окружение задаём до импорта приложения.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="buh-test-")
os.environ["FRONTEND_DIST"] = "/nonexistent"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
os.environ.pop("APP_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
