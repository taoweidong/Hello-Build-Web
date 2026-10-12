"""JWT 认证适配：Authorization: Bearer <token>。"""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import RevokedToken


class JWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # 复用父类 get_header + get_raw_token 解析 Authorization header，
        # 处理缺失 header 及空 token 等边界情况。
        header = self.get_header(request)
        if header is None:
            return None
        try:
            raw_token = self.get_raw_token(header)
        except AuthenticationFailed:
            # header 形态非法（如 "Bearer a b" 三段式）同样视为未认证，
            # 避免普通 Django 视图（authed_user 直调）冒泡成 500。
            return None
        if raw_token is None:
            return None
        # 非法/过期 token 视为未认证而非抛异常，避免普通 Django 视图冒泡成 500。
        # 注意 simplejwt 5.5.0 异常层级：InvalidToken 是 AuthenticationFailed 的子类。
        try:
            validated = self.get_validated_token(raw_token)
        except InvalidToken:
            return None
        # 登出拉黑：jti 命中黑名单视为未认证（见 views/login.py logout_view）。
        jti = validated.get("jti")
        if jti and RevokedToken.objects.filter(jti=jti).exists():
            return None
        # get_user 对「用户不存在 / is_active=False」抛 AuthenticationFailed
        # （2026-10-13 评估 B-P1-1：此前该调用在 try 之外，admin 停用用户后，
        # 被停用者存量 token 请求函数视图 → 裸 500，前端拿不到 40100 不跳登录）。
        # 统一归入"未认证"路径 → 40100。
        try:
            user = self.get_user(validated)
        except AuthenticationFailed:
            return None
        # 防御兜底：get_user 对合法 token 不会返回 None（inactive 在上方已抛异常），
        # 保留 None 判断以防子类行为变化。
        if user is None:
            return None
        return (user, validated)
