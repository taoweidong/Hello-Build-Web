"""运行期配置覆盖层：持久化到 RuntimeConfig 表 + 进程内缓存。

admin 经 /admin/config 写入后落库（重启不丢、多进程一致视角以落库为准）；
读取走进程内缓存，写入时同步刷新缓存。缓存无法感知其他进程的写入，
单机部署场景（SQLite + runserver）足够；跨进程强一致需求出现时再引入共享缓存。
"""
from django.db import IntegrityError

from ..models import RuntimeConfig

_CACHE = {}


def get_config(key, default=None):
    if key in _CACHE:
        return _CACHE[key]
    row = RuntimeConfig.objects.filter(key=key).first()
    value = row.value if row else default
    _CACHE[key] = value
    return value


def set_config(key, value):
    value = int(value)
    try:
        RuntimeConfig.objects.update_or_create(key=key, defaults={"value": value})
    except IntegrityError:
        # 并发 get_or_create 竞态撞 key unique 约束兜底（R4-B9/B4-09）：
        # update_or_create 内部自带 savepoint，捕获后按 UPDATE 重试一次即可
        # 安全恢复；仍失败则任异常上抛（由调用方事务整体回滚）。
        RuntimeConfig.objects.filter(key=key).update(value=value)
    _CACHE[key] = value


def reset_config():
    """清空进程内缓存（测试基线用）；持久化数据保留。"""
    _CACHE.clear()
