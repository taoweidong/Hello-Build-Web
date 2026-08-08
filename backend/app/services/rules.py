from datetime import datetime

def effective_start(strategy, ref_date: str) -> str:
    """变更生效日期：当日尚未开始构建 → 当日生效；已开始 → 次日起生效。
       ref_date 为 'YYYY-MM-DD'。返回生效日期字符串。"""
    if not strategy:
        return ""
    return ref_date