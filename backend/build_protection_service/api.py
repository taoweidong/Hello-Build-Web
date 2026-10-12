"""统一响应封装，保持现有契约 {code,message,data}。"""
from .errors import CODE_OK


def ok(data=None, message="ok"):
    return {"code": CODE_OK, "message": message, "data": data}


def err(code, message, data=None):
    return {"code": code, "message": message, "data": data}
