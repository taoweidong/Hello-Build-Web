"""运行期配置覆盖层：持久化到 RuntimeConfig 表 + 进程内缓存。

读取走进程内缓存。缓存无法感知其他进程的写入，单机部署场景
（SQLite + runserver）足够；跨进程强一致需求出现时再引入共享缓存。

2026-10-20 页面精简：写入入口（admin /admin/config）随系统管理页下线删除，
set_config 一并移除；配置初始值由 seed / 迁移保证，运行期只读。
"""
from ..models import RuntimeConfig

_CACHE = {}


def get_config(key, default=None):
    if key in _CACHE:
        return _CACHE[key]
    row = RuntimeConfig.objects.filter(key=key).first()
    value = row.value if row else default
    _CACHE[key] = value
    return value


def reset_config():
    """清空进程内缓存（测试基线用）；持久化数据保留。"""
    _CACHE.clear()
