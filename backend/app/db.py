from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if not url.startswith("sqlite"):
        # pre_ping: соединения serverless-Postgres (Neon) закрываются при простое.
        return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=3)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(conn, _record):
        # SQLite по умолчанию не соблюдает внешние ключи — без этого не работают ON DELETE.
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
