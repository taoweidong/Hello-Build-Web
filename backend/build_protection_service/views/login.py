"""登录/登出/当前用户。"""
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from ..api import ok
from ..models import RevokedToken
from . import authed_user, body_str, client_ip, fail_resp, json_resp, parse_body, security_log
from ..errors import (
    CODE_BAD_CREDENTIALS,
    CODE_FORBIDDEN,
    CODE_RATE_LIMITED,
    CODE_UNPROCESSABLE,
)

User = get_user_model()

# 登录防爆破：同一「用户名+来源 IP」失败满 5 次锁定（进程内 cache，单机部署足够）。
# 计数窗口为「自首次失败起 15 分钟」的固定窗口（R4-B18：add 仅在键不存在时写入
# 计数与 TTL，incr 原子自增且不续期；旧实现每次失败 set 续期实为滑动窗口，与
# 注释不符且读改写三步并发可稀释阈值，一并修正）；成功登录 delete 清零。
# 联合键防止攻击者用错误密码远程锁死任意账号（如 admin）；同源针对同一账号仍会锁定。
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
    # 方法守卫（R4-B6/B4-06）：登录是写路径（失败计数/审计日志副作用），仅 POST；
    # 此前 GET 落入「用户名与密码不能为空」语义错位
    if request.method != "POST":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    body = parse_body(request)
    # 类型守卫（R3-B2）：登录是未认证面，非字符串 username/password 此前会在
    # .strip()/check_password().encode() 处冒 AttributeError 变 500（B-P1-2）；
    # 统一经 body_str 归一为 ""，走下方"不能为空" 42201 分支。
    # 密码不做 strip（首尾空白是密码语义的一部分），保持既有口径。
    username = body_str(body, "username")
    password = body_str(body, "password", strip=False)
    if not username or not password:
        return fail_resp(CODE_UNPROCESSABLE, "用户名与密码不能为空")
    fail_key = f"login:fail:{username}:{client_ip(request)}"
    if cache.get(fail_key, 0) >= _LOGIN_MAX_ATTEMPTS:
        security_log("login_locked", username=username, request=request)
        return fail_resp(CODE_RATE_LIMITED, "失败次数过多，请 15 分钟后重试")
    user = User.objects.filter(username=username).first()
    if user is None or not user.check_password(password):
        # 原子自增（R4-B18/B4-18）：此前 cache.set(key, cache.get(key,0)+1)
        # 读改写三步，并发爆破可双双读到同一计数稀释 5 次阈值；add 仅在键不
        # 存在时初始化计数 1 与 TTL（原子），incr 由 cache 后端原子自增。
        if not cache.add(fail_key, 1, _LOGIN_LOCK_SECONDS):
            try:
                cache.incr(fail_key)
            except ValueError:
                # 键恰在 add 与 incr 之间过期：重开计数窗口
                cache.add(fail_key, 1, _LOGIN_LOCK_SECONDS)
        security_log("login_failed", username=username, request=request)
        return fail_resp(CODE_BAD_CREDENTIALS, "用户名或密码错误")
    if not user.is_active:
        # 凭据正确但账号停用：补审计行（R7-B7）——login_failed/locked/success
        # 均有留痕，唯独这一探测型事件此前零记录。不计入失败限流：密码已验证
        # 正确，锁定语义针对口令爆破而非停用账号的可达性探测。
        security_log("login_disabled", username=username, request=request)
        return fail_resp(CODE_FORBIDDEN, "账号已停用")
    cache.delete(fail_key)
    refresh = RefreshToken.for_user(user)
    security_log("login_success", username=username, request=request)
    return json_resp(ok({"token": str(refresh.access_token), "user": _user_payload(user)}))


def logout_view(request):
    """登出：将当前访问令牌加入黑名单即时失效，并清理已过期的黑名单记录。"""
    # 方法守卫（R4-B6/B4-06）：登出吊销 token 并写审计日志，是写操作，仅 POST；
    # 此前 GET /auth/logout 带 Bearer 头即误杀会话（预取/爬虫/地址栏访问）
    if request.method != "POST":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
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
    # 清理已过期记录；expires_at 可空且 null 行无法按时间自然失效，
    # 一并删除避免无限累积（R3-B11，2026-10-13 评估 B-P3-7）。
    RevokedToken.objects.filter(
        Q(expires_at__lt=datetime.now(tz=dt_timezone.utc)) | Q(expires_at__isnull=True)
    ).delete()
    # 审计条件化（R6-B9）：仅当 token 有效且解析出用户才落 logout 审计行——
    # 匿名/垃圾 token 调用此前每次都写 username="" 的噪音行，可被脚本灌审计。
    if username:
        security_log("logout", username=username, request=request)
    return json_resp(ok())


def me_view(request):
    # 方法守卫（R3-B16）：读端点仅 GET，禁止其他方法执行
    if request.method != "GET":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    # 普通 Django 视图不会自动执行 DRF JWT 认证，复用共享认证助手。
    user, resp = authed_user(request)
    if resp:
        return resp
    return json_resp(ok(_user_payload(user)))
