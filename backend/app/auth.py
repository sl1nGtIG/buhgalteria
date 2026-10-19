import hmac

from fastapi import Header, HTTPException, Query

from .config import settings


def require_token(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None, description="Для ссылок на картинки"),
) -> None:
    if not settings.app_token:
        return
    supplied = token or ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:]
    if not hmac.compare_digest(supplied.encode(), settings.app_token.encode()):
        raise HTTPException(status_code=401, detail="Неверный код доступа")
