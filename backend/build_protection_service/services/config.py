"""运行期配置覆盖层：admin 可改，未覆盖时回退 settings 默认值。"""
_RUNTIME_CONFIG = {}


def get_config(key, default=None):
    return _RUNTIME_CONFIG.get(key, default)


def set_config(key, value):
    _RUNTIME_CONFIG[key] = value


def reset_config():
    _RUNTIME_CONFIG.clear()