"""登录/登出/当前用户。"""
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from ..api import err, ok
from ..models import RevokedToken
from . import authed_user, json_resp, parse_body, security_log

User = get_user_model()

# 登录防爆破：同一用户名连续失败 5 次锁定 15 分钟（进程内 cache，单机部署足够）。
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCK_SECONDS = 15 * 60


def _user_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "bound_version_id": getattr(user, "bound_version_id", None),
        "bound_version_name": getattr(getattr(user, "bound_version", None), "name", None),
    }


def login_view(request):
    body = parse_body(request)
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return json_resp(err(42201, "用户名与密码不能为空"), status=422)
    fail_key = f"login:fail:{username}"
    if cache.get(fail_key, 0) >= _LOGIN_MAX_ATTEMPTS:
        security_log("login_locked", username=username)
        return json_resp(err(42901, "失败次数过多，请 15 分钟后重试"), status=429)
    user = User.objects.filter(username=username).first()
    if user is None or not user.check_password(password):
        cache.set(fail_key, cache.get(fail_key, 0) + 1, _LOGIN_LOCK_SECONDS)
        security_log("login_failed", username=username)
        return json_resp(err(40101, "用户名或密码错误"), status=401)
    if not user.is_active:
        return json_resp(err(40301, "账号已停用"), status=403)
    cache.delete(fail_key)
    refresh = RefreshToken.for_user(user)
    security_log("login_success", username=username)
    return json_resp(ok({"token": str(refresh.access_token), "user": _user_payload(user)}))


def logout_view(request):
    """登出：将当前访问令牌加入黑名单即时失效，并清理已过期的黑名单记录。"""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    raw = header[7:].strip() if header.lower().startswith("bearer ") else ""
    username = ""
    if raw:
        try:
            token = AccessToken(raw)
            RevokedToken.objects.get_or_create(
                jti=token["jti"],
                defaults={"expires_at": datetime.fromtimestamp(token["exp"], tz=dt_timezone.utc)},
            )
            user_id = token.get("user_id")
            if user_id:
                username = User.objects.filter(id=user_id).values_list("username", flat=True).first() or ""
        except (TokenError, KeyError):
            username = ""
    RevokedToken.objects.filter(
        expires_at__lt=datetime.now(tz=dt_timezone.utc)
    ).delete()
    security_log("logout", username=username)
    return json_resp(ok())


def me_view(request):
    # 普通 Django 视图不会自动执行 DRF JWT 认证，复用共享认证助手。
    user, resp = authed_user(request)
    if resp:
        return resp
    return json_resp(ok(_user_payload(user)))
