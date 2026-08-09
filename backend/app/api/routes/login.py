from datetime import timedelta

from fastapi import APIRouter

from app.adapters import LocalAuthAdapter
from app.api.deps import CurrentUser, SessionDep
from app.core import security
from app.core.config import settings
from app.core.response import ok, raise_param, raise_unauthorized
from app.crud import get_pm_bound_version
from app.models import LoginReq, SecurityLog

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_payload(session, user) -> dict:
    """登录/me 返回的用户信息（含 PM 绑定版本，前端契约）"""
    version = get_pm_bound_version(session=session, user_id=user.id)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "bound_version_id": version.id if version else None,
        "bound_version_name": version.name if version else None,
    }


@router.post("/login")
def login(req: LoginReq, session: SessionDep):
    if not req.username or not req.password:
        raise_param("用户名和密码不能为空")
    user = LocalAuthAdapter(session).authenticate(req.username, req.password)
    if not user:
        session.add(SecurityLog(user_id=None, event="login_failed", ip="mock-ip"))
        session.commit()
        raise_unauthorized("用户名或密码错误")
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = security.create_access_token(user.id, expires_delta=expires)
    session.add(SecurityLog(user_id=user.id, event="login", ip="mock-ip"))
    session.commit()
    return ok({"token": token, "user": _user_payload(session, user)})


@router.post("/logout")
def logout(current_user: CurrentUser, session: SessionDep):
    session.add(SecurityLog(user_id=current_user.id, event="logout", ip="mock-ip"))
    session.commit()
    return ok()


@router.get("/me")
def me(current_user: CurrentUser, session: SessionDep):
    return ok(_user_payload(session, current_user))
