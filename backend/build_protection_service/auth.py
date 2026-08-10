"""JWT 认证适配：Authorization: Bearer <token>。"""
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith("Bearer "):
            return None
        token = header.split(" ")[1]
        validated = self.get_validated_token(token)
        user = self.get_user(validated)
        if user is None or not user.is_active:
            return None
        return (user, token)