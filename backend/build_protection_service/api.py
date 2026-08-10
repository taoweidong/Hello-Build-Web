"""统一响应封装，保持现有契约 {code,message,data}。"""


def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}


def err(code, message, data=None):
    return {"code": code, "message": message, "data": data}