"""JWT 认证适配：Authorization: Bearer <token>。"""
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # 复用父类 get_header + get_raw_token 解析 Authorization header，
        # 正确处理大小写、缺失 header 及空 token 等边界情况。
        header = self.get_header(request)
        if header is None:
            return None
        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None
        validated = self.get_validated_token(raw_token)
        user = self.get_user(validated)
        if user is None or not user.is_active:
            return None
        return (user, validated)