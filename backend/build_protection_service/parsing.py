"""请求参数解析工具（views 与 services 两层共用，避免重复实现）。

原先 views.parse_int 与 services.slot_booking._safe_int 是逐字符相同的两份，
服务层不能反向依赖视图层，故收敛到本中立模块；views 包 re-export 保持既有
`from . import parse_int` 用法不变。
"""


def parse_int(value):
    """安全转 int；None/非数字返回 None，供 id 过滤前兜底（避免 ValueError 500）。

    Django 对 ``filter(id="abc")`` 会抛 ValueError（未捕获即 500，破坏统一响应契约），
    因此所有来自 query/body 的 ID 参数必须先经本函数转换。

    仅接受 ASCII 十进制数字：``int()`` 会接受全角数字（"０"）与 Unicode 数字，
    这些值不该进入 ID 过滤，故先用 str.isascii() 拦掉。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.isascii() or not text.lstrip("-").isdigit():
            return None
        return int(text)
    return None
