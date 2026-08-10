"""视图辅助：统一 JSON 响应 + 安全日志。"""
from django.contrib.auth import get_user_model
from django.http import JsonResponse

from ..models import SecurityLog

User = get_user_model()


def json_resp(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def security_log(action, username=""):
    try:
        SecurityLog.objects.create(username=username, action=action)
    except Exception:
        pass