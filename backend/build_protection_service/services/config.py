"""运行期配置覆盖层：持久化到 RuntimeConfig 表 + 进程内缓存。

读取走进程内缓存。缓存无法感知其他进程的写入，单机部署场景
（SQLite + runserver）足够；跨进程强一致需求出现时再引入共享缓存。

2026-10-20 页面精简：写入入口（admin /admin/config）随系统管理页下线删除，
set_config 一并移除，运行期只读。注意：表内**并无种子初始值**（seed 与迁移均
不写 RuntimeConfig 行），get_config 实际恒回落 settings 默认值——本层是为
「admin 后台改配置不重启」预留的覆盖层。RuntimeConfig 已在 django-admin 注册
只读展示（R7-B12，核对手工覆盖行用），**写入口仍未开放**：如需启用覆盖面，
须同步评估多进程部署下的缓存一致性，不要默认建行即生效。
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
