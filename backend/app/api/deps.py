from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.core.response import raise_forbidden, raise_unauthorized
from app.models import TokenPayload, User

# 前端契约：Authorization: Bearer <token>
reusable_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[HTTPAuthorizationCredentials | None, Depends(reusable_bearer)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    if token is None:
        raise_unauthorized()
    try:
        payload = jwt.decode(
            token.credentials, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except InvalidTokenError:
        raise_unauthorized()
    user = session.get(User, int(token_data.sub)) if token_data.sub else None
    if not user:
        raise_unauthorized()
    if not user.is_active:
        raise_unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_admin(current_user: CurrentUser) -> User:
    if current_user.role != "admin":
        raise_forbidden("仅管理员可执行该操作")
    return current_user


AdminUser = Annotated[User, Depends(get_current_active_admin)]
