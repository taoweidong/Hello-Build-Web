"""系统管理 views（2026-10-20 页面精简后仅剩模板只读端点）。

原系统管理页下线，版本 / 用户 / 全局配置 / 日志查询 / 管理员策略 CRUD 等端点
整体删除；模板列表保留 GET 是因为策略配置页（PM）与全景编辑弹窗的下拉选项
仍消费它（GET 对 admin+pm 开放，写操作收敛到 seed / django-admin）。
"""
from ..api import ok
from ..errors import CODE_FORBIDDEN, CODE_UNPROCESSABLE
from ..models import StrategyTemplate
from . import authed_user, fail_resp, json_resp


def _template_payload(t):
    return {
        "id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
        "analysis_minutes": t.analysis_minutes, "description": t.description,
    }


def templates_view(request):
    """策略模板：列表（admin+pm 只读）。"""
    # 方法守卫（R7-B12，对齐全站「方法守卫先行」）：读端点仅 GET；此前排在
    # 认证+角色之后，builder 发 POST 会得到 40301「无权限」而非 42201「方法不支持」
    if request.method != "GET":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    if user.role not in ("admin", "pm"):
        return fail_resp(CODE_FORBIDDEN, "无权限操作模板")
    qs = StrategyTemplate.objects.all()
    return json_resp(ok([_template_payload(t) for t in qs]))
