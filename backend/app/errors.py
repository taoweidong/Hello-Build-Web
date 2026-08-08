from fastapi import HTTPException

class BizError(Exception):
    def __init__(self, code: int, message: str, detail=None):
        self.code = code
        self.message = message
        self.detail = detail

def raise_unauthorized(msg="未登录或登录已过期"):  # 40101
    raise HTTPException(status_code=401, detail={"code": 40101, "message": msg})
def raise_forbidden(msg="无权限执行该操作"):        # 40301
    raise HTTPException(status_code=403, detail={"code": 40301, "message": msg})
def raise_conflict(msg, detail=None):              # 40901 策略冲突
    raise HTTPException(status_code=409, detail={"code": 40901, "message": msg, "conflicts": detail})
def raise_duplicate(msg="当前结论已录入，请勿重复提交"):  # 40902
    raise HTTPException(status_code=409, detail={"code": 40902, "message": msg})
def raise_param(msg="参数校验失败"):               # 42201
    raise HTTPException(status_code=422, detail={"code": 42201, "message": msg})

# 统一响应包装
def ok(data=None):
    return {"code": 0, "message": "ok", "data": data}