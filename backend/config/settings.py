"""Django 主配置。保留现有契约：API 前缀 /api、JWT、统一响应。"""
import os
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# 安全默认值：DEBUG 与 CORS 默认关闭/收紧，本地开发通过 backend/.env 打开（见 .env.example）。
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]

# SECRET_KEY：回退开发密钥随仓库公开，生产（DEBUG=false）静默回退等于任何人可伪造
# JWT。因此生产缺失 env 配置时拒绝启动；测试进程（manage.py test）豁免以便无 .env 运行。
_ENV_SECRET_KEY = os.getenv("SECRET_KEY")
_IS_TESTING = "test" in sys.argv
if _ENV_SECRET_KEY:
    SECRET_KEY = _ENV_SECRET_KEY
elif DEBUG or _IS_TESTING:
    SECRET_KEY = "dev-only-insecure-secret-key-do-not-use-in-production-0123456789abcdef"
else:
    raise ImproperlyConfigured(
        "缺少 SECRET_KEY 环境变量：生产环境禁止回退到仓库内置开发密钥，"
        "请在 backend/.env 中配置（模板见 backend/.env.example）"
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "build_protection_service",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # CSRF 仅保护 django-admin 的会话认证面；业务 API 走 JWT 头认证，
    # 已在 views/urls.py 统一 csrf_exempt（DRF ViewSet 自带豁免）。
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "build_strategy.db",
        # 事务以 BEGIN IMMEDIATE 打开：进入事务即取写锁，杜绝
        # 「校验读发生在他人提交前、写入发生在他人提交后」的
        # check-then-act 竞态（影响策略互斥/时段抢占等全部写路径）。
        # 注意：测试库为 Django 默认的独立内存库（未配置 TEST 项），
        # 其并发写行为与生产文件库不同，并发用例按内存库语义设计。
        # 迁移 PostgreSQL/MySQL 时删除本项，改在服务层用 select_for_update
        # （见 docs/superpowers/specs/2026-10-11-strategy-concurrency-guard-design.md）。
        "OPTIONS": {"transaction_mode": "IMMEDIATE"},
    }
}

AUTH_USER_MODEL = "build_protection_service.User"

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- 业务配置（与现有 Settings 对齐，可在运行时调整）----
BUILD_MINUTES = int(os.getenv("BUILD_MINUTES", "30"))
PUSH_MINUTES = int(os.getenv("PUSH_MINUTES", "20"))
SYNC_BUFFER_MINUTES = int(os.getenv("SYNC_BUFFER_MINUTES", "20"))
SLOT_BOOKING_HORIZON_DAYS = int(os.getenv("SLOT_BOOKING_HORIZON_DAYS", "60"))
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
FIRST_SUPERUSER = os.getenv("FIRST_SUPERUSER", "admin")
FIRST_SUPERUSER_PASSWORD = os.getenv("FIRST_SUPERUSER_PASSWORD", "123456")

# ---- DRF / JWT ----
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "build_protection_service.auth.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": None,
    # 异常也走 {code,message,data} 信封（非法 JSON body 等 DRF 异常默认返回
    # {"detail": ...} 无 code 字段，会破坏前端契约）
    "EXCEPTION_HANDLER": "build_protection_service.exception_handlers.contract_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    "ALGORITHM": "HS256",
    # JWT 签名密钥独立于 SECRET_KEY；未配置时回退 SECRET_KEY（生产必须单独设置）。
    "SIGNING_KEY": os.getenv("JWT_SIGNING_KEY", SECRET_KEY),
}

# 前后端直连：默认白名单放行本地开发端口；需要全开时设 CORS_ALLOW_ALL_ORIGINS=true，
# 生产通过 CORS_ALLOWED_ORIGINS 配置实际来源。
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "false").lower() in ("1", "true", "yes")
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:8848,http://127.0.0.1:8848",
    ).split(",") if o.strip()
]

# ---- 日志：业务日志输出到控制台（含发布模拟推送等联调用途日志）----
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "build_protection_service": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}