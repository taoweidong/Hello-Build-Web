"""登录/登出/当前用户。"""
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from ..api import err, ok
from ..models import RevokedToken
from . import authed_user, fail_resp, json_resp, parse_body, security_log
from ..errors import CODE_BAD_CREDENTIALS, CODE_FORBIDDEN, CODE_RATE_LIMITED, CODE_UNPROCESSABLE

User = get_user_model()

# 登录防爆破：同一「用户名+来源 IP」连续失败 5 次锁定 15 分钟（进程内 cache，单机部署足够）。
# 联合键防止攻击者用错误密码远程锁死任意账号（如 admin）；同源针对同一账号仍会锁定。
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCK_SECONDS = 15 * 60


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return request.META.get("REMOTE_ADDR", "") or forwarded.split(",")[0].strip()


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
        return fail_resp(CODE_UNPROCESSABLE, "用户名与密码不能为空")
    fail_key = f"login:fail:{username}:{_client_ip(request)}"
    if cache.get(fail_key, 0) >= _LOGIN_MAX_ATTEMPTS:
        security_log("login_locked", username=username, request=request)
        return fail_resp(CODE_RATE_LIMITED, "失败次数过多，请 15 分钟后重试")
    user = User.objects.filter(username=username).first()
    if user is None or not user.check_password(password):
        cache.set(fail_key, cache.get(fail_key, 0) + 1, _LOGIN_LOCK_SECONDS)
        security_log("login_failed", username=username, request=request)
        return fail_resp(CODE_BAD_CREDENTIALS, "用户名或密码错误")
    if not user.is_active:
        return fail_resp(CODE_FORBIDDEN, "账号已停用")
    cache.delete(fail_key)
    refresh = RefreshToken.for_user(user)
    security_log("login_success", username=username, request=request)
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
    security_log("logout", username=username, request=request)
    return json_resp(ok())


def me_view(request):
    # 普通 Django 视图不会自动执行 DRF JWT 认证，复用共享认证助手。
    user, resp = authed_user(request)
    if resp:
        return resp
    return json_resp(ok(_user_payload(user)))
