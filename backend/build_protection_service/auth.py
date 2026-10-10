"""JWT 认证适配：Authorization: Bearer <token>。"""
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
        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None
        # 非法/过期 token 视为未认证而非抛异常，避免普通 Django 视图冒泡成 500。
        try:
            validated = self.get_validated_token(raw_token)
        except InvalidToken:
            return None
        # 登出拉黑：jti 命中黑名单视为未认证（见 views/login.py logout_view）。
        jti = validated.get("jti")
        if jti and RevokedToken.objects.filter(jti=jti).exists():
            return None
        user = self.get_user(validated)
        if user is None or not user.is_active:
            return None
        return (user, validated)
