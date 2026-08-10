# Django 后端迁移 + 周视图等前端增强 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将后端从 FastAPI/SQLModel 完全替换为 Django REST Framework，并实现前端 5 项需求变更（计划页详情、周视图、系统策略配置、推送时间任意化、互斥策略）。

**Architecture:** 后端在 `backend/` 新建 Django 项目 + 核心 app `build_protection_service`，保持现有 API 契约 `{code,message,data}` 与 `Authorization: Bearer` 不变；继承 `AbstractUser` 扩展 `role` 字段；用 DRF 序列化器 + 自定义视图实现全部接口。前端在 `frontend/src/` 优化计划页、新增周视图页面、系统管理新增策略配置 Tab，并扩展 api 层字段。

**Tech Stack:** Django 5.x、Django REST Framework、djangorestframework-simplejwt、Django TestCase；前端 Vue3 + Element Plus + vue-ganttastic + CSS Grid（周视图自研）。

---

## 文件结构总览

**新建（后端，`backend/` 下）：**
- `manage.py`
- `config/settings.py`、`config/urls.py`、`config/wsgi.py`、`config/asgi.py`
- `build_protection_service/__init__.py`
- `build_protection_service/models.py`
- `build_protection_service/serializers.py`
- `build_protection_service/api.py`（统一响应封装）
- `build_protection_service/auth.py`（JWT 认证适配）
- `build_protection_service/permissions.py`（角色权限）
- `build_protection_service/services/__init__.py`
- `build_protection_service/services/timeline.py`
- `build_protection_service/services/conflict.py`
- `build_protection_service/services/mutex.py`
- `build_protection_service/views/__init__.py`
- `build_protection_service/views/login.py`
- `build_protection_service/views/strategies.py`
- `build_protection_service/views/plan.py`
- `build_protection_service/views/weekly.py`
- `build_protection_service/views/executions.py`
- `build_protection_service/views/admin.py`
- `build_protection_service/views/logs.py`
- `build_protection_service/admin.py`
- `build_protection_service/apps.py`
- `seed/seed_data.py`
- `seed/__init__.py`

**修改（后端）：** `backend/pyproject.toml`、`backend/.env`、`backend/scripts/prestart.ps1`、`backend/scripts/test.ps1`

**新建（前端，`frontend/src/` 下）：**
- `views/weekly/index.vue`
- `components/weekly/WeeklyGrid.vue`（可选，若逻辑内联则省略）

**修改（前端）：**
- `api/strategy.ts`、`api/plan.ts`、`api/types.ts`、`api/admin.ts`、`api/http.ts`（适配 token 校验）
- `views/plan/index.vue`（详情面板 + 修复报错）
- `views/admin/index.vue`（策略配置 Tab）
- `views/strategy/index.vue`（新增 push_start_time 字段）
- `router/asyncRoutes.ts`（新增周视图菜单）
- `api/panorama.ts`（若复用详情则确认字段）

**测试（后端）：** `build_protection_service/tests.py`（Django TestCase，覆盖登录/JWT、策略 CRUD、互斥、阶段冲突、推送推导、权限、周视图）

---

### Task 1: Django 项目脚手架与环境

**Files:**
- Create: `backend/manage.py`
- Create: `backend/config/__init__.py`
- Create: `backend/config/settings.py`
- Create: `backend/config/urls.py`
- Create: `backend/config/wsgi.py`
- Create: `backend/config/asgi.py`
- Create: `backend/build_protection_service/__init__.py`
- Create: `backend/build_protection_service/apps.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/.env`
- Modify: `backend/scripts/prestart.ps1`

- [ ] **Step 1: 更新 pyproject.toml 依赖（Flash→Django）**

将 `backend/pyproject.toml` 内容替换为：

```toml
[project]
name = "build-protection-backend"
version = "1.0.0"
description = "构建策略配置系统后端（Django）"
requires-python = ">=3.11"
dependencies = [
    "django>=5.0,<6.0",
    "djangorestframework>=3.15",
    "djangorestframework-simplejwt>=5.3",
    "django-cors-headers>=4.3",
    "python-dotenv>=1.0",
    "tzdata>=2024.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-django>=4.8",
]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
python_files = ["tests.py", "test_*.py", "*_tests.py"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: 创建 manage.py**

```python
#!/usr/bin/env python
"""Django 的命令行工具。"""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 创建 config/settings.py**

```python
"""Django 主配置。保留现有契约：API 前缀 /api、JWT、统一响应。"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.getenv("DEBUG", "true").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = ["*"]

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
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
}

CORS_ALLOW_ALL_ORIGINS = True
```

- [ ] **Step 4: 创建 config/urls.py、wsgi.py、asgi.py**

`config/urls.py`：

```python
"""根路由。全部业务接口挂载在 /api 下。"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/", include("build_protection_service.views.urls")),
]
```

`config/wsgi.py`：

```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
```

`config/asgi.py`：

```python
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()
```

- [ ] **Step 5: 创建 app 及其 apps.py**

`backend/build_protection_service/__init__.py`（空文件）。

`backend/build_protection_service/apps.py`：

```python
from django.apps import AppConfig


class BuildProtectionServiceConfig(AppConfig):
    name = "build_protection_service"
    verbose_name = "构建策略服务"
```

- [ ] **Step 6: 更新 .env**

`backend/.env` 内容：

```
DEBUG=true
SECRET_KEY=dev-secret-key-change-me
DATABASE_URL=sqlite:///./build_strategy.db
BUILD_MINUTES=30
PUSH_MINUTES=20
SYNC_BUFFER_MINUTES=20
ACCESS_TOKEN_EXPIRE_MINUTES=480
FIRST_SUPERUSER=admin
FIRST_SUPERUSER_PASSWORD=123456
```

- [ ] **Step 7: 更新 scripts/prestart.ps1**

```powershell
# 迁移数据库并创建超级用户
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
python manage.py makemigrations build_protection_service
python manage.py migrate
python manage.py seed
```

- [ ] **Step 8: 冒烟验证**

Run: `cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e . ; python -c "import django; print(django.get_version())"`
Expected: 打印 Django 版本号（5.x），无 ImportError。

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/manage.py backend/config backend/build_protection_service backend/.env backend/scripts/prestart.ps1
git commit -m "build(backend): 创建 Django 项目脚手架替换 FastAPI"
```

---

### Task 2: 数据模型与迁移

**Files:**
- Create: `backend/build_protection_service/models.py`
- Create: `backend/build_protection_service/admin.py`
- Test: `backend/build_protection_service/tests.py`

- [ ] **Step 1: 写失败测试（模型创建 + 唯一约束 + push_start_time）**

在 `backend/build_protection_service/tests.py` 追加：

```python
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from .models import Branch, Strategy, StrategyTemplate, Version

User = get_user_model()


class ModelTests(TestCase):
    def setUp(self):
        self.pm = User.objects.create_user(
            username="pm1", password="123456", role="pm"
        )
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120
        )

    def test_strategy_push_start_time_nullable(self):
        s = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="27A-master-晚间",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        self.assertIsNone(s.push_start_time)

    def test_strategy_push_start_time_settable(self):
        s = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="27A-master-晚间",
            build_start_time="22:00", push_start_time="20:00",
            push_mode="normal", created_by=self.pm,
        )
        self.assertEqual(s.push_start_time, "20:00")

    def test_branch_unique_per_version(self):
        Branch.objects.create(version=self.version, name="master")
        with self.assertRaises(IntegrityError):
            Branch.objects.create(version=self.version, name="master")

    def test_version_pm_unique(self):
        Version.objects.create(name="27B", pm_user=self.pm, status="active")
        with self.assertRaises(IntegrityError):
            Version.objects.create(name="27C", pm_user=self.pm, status="active")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.ModelTests -v 2`
Expected: FAIL（`ModuleNotFoundError` / 表不存在）。

- [ ] **Step 3: 实现 models.py**

```python
"""全部数据模型。对应原 FastAPI 表结构，用 Django ORM 重建。"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """扩展用户：继承 Django 默认认证，新增业务角色字段。"""
    ROLE_CHOICES = (
        ("admin", "管理员"),
        ("pm", "版本负责人"),
        ("builder", "构建人员"),
        ("tester", "测试人员"),
        ("integrator", "集成人员"),
    )
    role = models.CharField("角色", max_length=20, choices=ROLE_CHOICES, default="builder")
    display_name = models.CharField("显示名", max_length=100, blank=True, default="")

    def __str__(self):
        return self.username


class Version(models.Model):
    name = models.CharField("版本号", max_length=100, unique=True)
    pm_user = models.OneToOneField(
        User, on_delete=models.PROTECT, related_name="bound_version", verbose_name="PM"
    )
    status = models.CharField("状态", max_length=20, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Branch(models.Model):
    version = models.ForeignKey(
        Version, on_delete=models.CASCADE, related_name="branches"
    )
    name = models.CharField("分支名", max_length=100)

    class Meta:
        unique_together = ("version", "name")

    def __str__(self):
        return f"{self.version.name}/{self.name}"


class StrategyTemplate(models.Model):
    name = models.CharField("模板名", max_length=100)
    smoke_minutes = models.PositiveIntegerField(default=0)
    analysis_minutes = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True, default="")

    def __str__(self):
        return self.name


class Strategy(models.Model):
    PUSH_MODE_CHOICES = (("normal", "正常流程推送"), ("sync", "同步推送冒烟"))
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="strategies")
    template = models.ForeignKey(
        StrategyTemplate, on_delete=models.PROTECT, related_name="strategies"
    )
    name = models.CharField("策略名", max_length=200)
    build_start_time = models.CharField("构建开始时间", max_length=5)  # "HH:MM"
    push_start_time = models.CharField("推送开始时间", max_length=5, null=True, blank=True)  # "HH:MM" 可空
    push_mode = models.CharField("推送模式", max_length=10, choices=PUSH_MODE_CHOICES, default="normal")
    enabled = models.BooleanField("启用", default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_strategies", null=True, blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["build_start_time"]

    def __str__(self):
        return self.name


class ExecutionRound(models.Model):
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="rounds")
    exec_date = models.DateField()
    build_start_at = models.DateTimeField(null=True, blank=True)
    build_end_at = models.DateTimeField(null=True, blank=True)
    smoke_start_at = models.DateTimeField(null=True, blank=True)
    smoke_end_at = models.DateTimeField(null=True, blank=True)
    analysis_start_at = models.DateTimeField(null=True, blank=True)
    analysis_end_at = models.DateTimeField(null=True, blank=True)
    push_start_at = models.DateTimeField(null=True, blank=True)
    push_end_at = models.DateTimeField(null=True, blank=True)
    conclusion = models.CharField("结论", max_length=20, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    push_status = models.CharField("推送状态", max_length=20, null=True, blank=True)
    release_approved = models.BooleanField(default=False)

    class Meta:
        unique_together = ("strategy", "exec_date")

    def __str__(self):
        return f"{self.strategy.name}@{self.exec_date}"


class ExecutionLog(models.Model):
    round = models.ForeignKey(ExecutionRound, on_delete=models.CASCADE, related_name="logs")
    stage = models.CharField(max_length=20)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class StrategyChangeLog(models.Model):
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name="change_logs")
    operator = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    change_desc = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class AdminOpLog(models.Model):
    operator = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=50, blank=True, default="")
    target_id = models.CharField(max_length=50, blank=True, default="")
    detail = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)


class SecurityLog(models.Model):
    username = models.CharField(max_length=100, blank=True, default="")
    action = models.CharField(max_length=100)
    detail = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
```

- [ ] **Step 4: 注册 admin**

`backend/build_protection_service/admin.py`：

```python
from django.contrib import admin

from .models import (
    AdminOpLog, Branch, ExecutionLog, ExecutionRound, SecurityLog,
    Strategy, StrategyChangeLog, StrategyTemplate, User, Version,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "role", "display_name", "is_active")


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    list_display = ("name", "pm_user", "status")


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "template", "build_start_time", "push_start_time", "enabled")


admin.site.register(Branch)
admin.site.register(StrategyTemplate)
admin.site.register(ExecutionRound)
admin.site.register(ExecutionLog)
admin.site.register(StrategyChangeLog)
admin.site.register(AdminOpLog)
admin.site.register(SecurityLog)
```

- [ ] **Step 5: 生成并应用迁移**

Run: `cd backend; python manage.py makemigrations build_protection_service; python manage.py migrate`
Expected: 输出迁移 `0001_initial` 并成功建表。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service.tests.ModelTests -v 2`
Expected: PASS（4 个测试）。

- [ ] **Step 7: Commit**

```bash
git add backend/build_protection_service/models.py backend/build_protection_service/admin.py backend/build_protection_service/tests.py
git commit -m "feat(model): Django 数据模型与迁移，含 push_start_time 字段"
```

---

### Task 3: 统一响应封装 + JWT 认证

**Files:**
- Create: `backend/build_protection_service/api.py`
- Create: `backend/build_protection_service/auth.py`
- Create: `backend/build_protection_service/permissions.py`

- [ ] **Step 1: 实现 api.py（统一响应）**

```python
"""统一响应封装，保持现有契约 {code,message,data}。"""
def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}


def err(code, message, data=None):
    return {"code": code, "message": message, "data": data}
```

- [ ] **Step 2: 实现 auth.py（JWT 认证适配）**

```python
"""JWT 认证适配：Authorization: Bearer <token>。"""
from rest_framework_simplejwt.authentication import JWTAuthentication


class JWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith("Bearer "):
            return None
        token = header.split(" ")[1]
        validated = self.get_validated_token(token)
        user = self.get_user(validated)
        if user is None or not user.is_active:
            return None
        return (user, token)
```

- [ ] **Step 3: 实现 permissions.py（角色权限）**

```python
"""角色权限：基于 user.role 字段。"""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    message = "仅管理员可操作"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "admin")


class IsPmOrAdmin(BasePermission):
    message = "仅版本负责人或管理员可操作"

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in ("pm", "admin")
        )
```

- [ ] **Step 4: 创建 views 包与空路由**

创建 `backend/build_protection_service/views/__init__.py`（空文件）和 `backend/build_protection_service/views/urls.py`：

```python
from django.urls import path

app_name = "build_protection_service"

urlpatterns = []
```

- [ ] **Step 5: 冒烟验证导入**

Run: `cd backend; python -c "from build_protection_service import api, auth, permissions; print('ok')"`
Expected: 输出 `ok`，无 ImportError。

- [ ] **Step 6: Commit**

```bash
git add backend/build_protection_service/api.py backend/build_protection_service/auth.py backend/build_protection_service/permissions.py backend/build_protection_service/views/urls.py
git commit -m "feat(auth): 统一响应封装与 JWT 认证、角色权限"
```

---

### Task 4: 业务服务（timeline / conflict / mutex）

**Files:**
- Create: `backend/build_protection_service/services/__init__.py`
- Create: `backend/build_protection_service/services/timeline.py`
- Create: `backend/build_protection_service/services/conflict.py`
- Create: `backend/build_protection_service/services/mutex.py`

- [ ] **Step 1: 写失败测试**

在 `tests.py` 追加：

```python
from datetime import datetime

from .services import conflict, mutex, timeline


class TimelineTests(TestCase):
    def test_build_timeline_normal_push_null(self):
        tl = timeline.build_timeline("2026-08-10", "22:00", 480, 120, 30, 20, 20, "normal", push_start_time=None)
        self.assertIsNone(tl["push"])
        self.assertEqual(tl["build"]["start"], "2026-08-10T22:00:00")

    def test_build_timeline_fixed_push(self):
        tl = timeline.build_timeline("2026-08-10", "22:00", 480, 120, 30, 20, 20, "normal", push_start_time="20:00")
        self.assertIsNotNone(tl["push"])
        self.assertEqual(tl["push"]["start"], "2026-08-10T20:00:00")
        self.assertEqual(tl["push"]["end"], "2026-08-10T20:20:00")

    def test_mutex_same_version_diff_branch_overlap(self):
        intervals = [
            {"label": "A", "start": datetime(2026, 8, 10, 22, 0), "end": datetime(2026, 8, 10, 22, 30)},
            {"label": "B", "start": datetime(2026, 8, 10, 22, 10), "end": datetime(2026, 8, 10, 22, 40)},
        ]
        hits = mutex.find_overlaps(intervals)
        self.assertEqual(len(hits), 1)

    def test_mutex_no_overlap(self):
        intervals = [
            {"label": "A", "start": datetime(2026, 8, 10, 22, 0), "end": datetime(2026, 8, 10, 22, 30)},
            {"label": "B", "start": datetime(2026, 8, 10, 23, 0), "end": datetime(2026, 8, 10, 23, 30)},
        ]
        self.assertEqual(mutex.find_overlaps(intervals), [])


class ConflictTests(TestCase):
    def test_stage_conflict_same_overlap(self):
        from types import SimpleNamespace
        tmpl = SimpleNamespace(smoke_minutes=120, analysis_minutes=60)
        cand = [{"build_start_time": "22:00", "template": tmpl, "push_mode": "sync", "strategy_name": "A"}]
        existing = [{"build_start_time": "22:10", "template": tmpl, "push_mode": "sync", "strategy_name": "B"}]
        hits = conflict.detect_conflicts("2026-08-10", cand, existing, 30, 20, 20)
        self.assertGreaterEqual(len(hits), 1)

    def test_stage_no_conflict(self):
        from types import SimpleNamespace
        tmpl = SimpleNamespace(smoke_minutes=120, analysis_minutes=60)
        cand = [{"build_start_time": "22:00", "template": tmpl, "push_mode": "sync", "strategy_name": "A"}]
        existing = [{"build_start_time": "12:00", "template": tmpl, "push_mode": "sync", "strategy_name": "B"}]
        hits = conflict.detect_conflicts("2026-08-10", cand, existing, 30, 20, 20)
        self.assertEqual(hits, [])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.TimelineTests build_protection_service.tests.ConflictTests -v 2`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 services/timeline.py**

```python
"""时间线推导：构建/冒烟/分析/推送各阶段起止。

有 push_start_time → 推送固定为 push_start_time ~ +push_minutes；
空 → normal 模式推送为 null；sync 模式推送在构建前预留 sync_buffer。
"""
from datetime import date, datetime, timedelta


def parse_cd(ds: str) -> date:
    return datetime.strptime(ds, "%Y-%m-%d").date()


def parse_hhmm(base: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(base, datetime.min.time().replace(hour=h, minute=m))


def build_timeline(ds, build_start_time, smoke_min, analysis_min,
                   build_min, push_min, sync_buffer, push_mode, push_start_time=None):
    base = parse_cd(ds)
    build_start = parse_hhmm(base, build_start_time)
    build_end = build_start + timedelta(minutes=build_min)
    smoke_start = build_end
    smoke_end = smoke_start + timedelta(minutes=smoke_min)
    analysis_start = smoke_end
    analysis_end = analysis_start + timedelta(minutes=analysis_min)

    push = None
    if push_start_time:
        push_start = parse_hhmm(base, push_start_time)
        push_end = push_start + timedelta(minutes=push_min)
        push = {"start": _iso(push_start), "end": _iso(push_end)}
    elif push_mode == "sync":
        push_start = build_start - timedelta(minutes=push_min + sync_buffer)
        push_end = build_start - timedelta(minutes=sync_buffer)
        push = {"start": _iso(push_start), "end": _iso(push_end)}

    return {
        "push": push,
        "build": {"start": _iso(build_start), "end": _iso(build_end)},
        "smoke": {"start": _iso(smoke_start), "end": _iso(smoke_end)},
        "analysis": {"start": _iso(analysis_start), "end": _iso(analysis_end)},
    }


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")
```

- [ ] **Step 4: 实现 services/mutex.py**

```python
"""互斥检测：同版本跨分支构建阶段时间重叠。"""
from datetime import datetime, timedelta


def find_overlaps(intervals):
    """intervals: [{label,start,end}]，返回重叠对列表。"""
    hits = []
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            a, b = intervals[i], intervals[j]
            if a["start"] < b["end"] and b["start"] < a["end"]:
                hits.append({
                    "first": a["label"],
                    "second": b["label"],
                    "overlap_start": max(a["start"], b["start"]).strftime("%Y-%m-%dT%H:%M:%S"),
                    "overlap_end": min(a["end"], b["end"]).strftime("%Y-%m-%dT%H:%M:%S"),
                })
    return hits


def check_build_mutex(version_id, build_start_time, build_min,
                      exclude_strategy_id=None):
    """校验同版本其它启用策略的构建阶段是否与目标构建区间重叠。返回命中列表。"""
    from django.conf import settings
    from .models import Strategy
    from .timeline import build_timeline, parse_cd, parse_hhmm

    base = parse_cd("2026-08-10")
    target_start = parse_hhmm(base, build_start_time)
    target_end = target_start + timedelta(minutes=build_min)

    query = Strategy.objects.select_related("branch", "template").filter(
        branch__version_id=version_id, enabled=True
    )
    if exclude_strategy_id:
        query = query.exclude(id=exclude_strategy_id)

    hits = []
    for s in query:
        try:
            tl = build_timeline(
                "2026-08-10", s.build_start_time,
                s.template.smoke_minutes, s.template.analysis_minutes,
                settings.BUILD_MINUTES, settings.PUSH_MINUTES,
                settings.SYNC_BUFFER_MINUTES, s.push_mode,
                push_start_time=s.push_start_time,
            )
        except Exception:
            continue
        s_start = _parse_iso(tl["build"]["start"])
        s_end = _parse_iso(tl["build"]["end"])
        if s_start < target_end and target_start < s_end:
            hits.append({
                "strategy": f"{s.branch.name}/{s.name}",
                "overlap_start": max(s_start, target_start).strftime("%Y-%m-%dT%H:%M:%S"),
                "overlap_end": min(s_end, target_end).strftime("%Y-%m-%dT%H:%M:%S"),
            })
    return hits


def _parse_iso(iso_str):
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S")
```

- [ ] **Step 5: 实现 services/conflict.py**

```python
"""阶段冲突检测：同分支内冒烟/分析阶段与其它策略重叠（推送除外）。"""
from datetime import datetime

from .timeline import build_timeline


def detect_conflicts(ds, candidates, existing, build_min, push_min, sync_buffer):
    """candidates/existing: [{build_start_time, template, push_mode, strategy_name, push_start_time}]。

    返回 [{strategy_name, overlap_start, overlap_end}]（重叠的冒烟/分析阶段）。
    """
    def _stages(item):
        return build_timeline(
            ds, item["build_start_time"], item["template"].smoke_minutes,
            item["template"].analysis_minutes, build_min, push_min, sync_buffer,
            item["push_mode"], push_start_time=item.get("push_start_time"),
        )

    cand_stages = [{"name": c["strategy_name"], "tl": _stages(c)} for c in candidates]
    results = []
    for c in cand_stages:
        for e in existing:
            etl = _stages(e)
            for key in ("smoke", "analysis"):
                if not etl[key] or not c["tl"][key]:
                    continue
                a_s, a_e = _parse(c["tl"][key]["start"]), _parse(c["tl"][key]["end"])
                b_s, b_e = _parse(etl[key]["start"]), _parse(etl[key]["end"])
                if a_s < b_e and b_s < a_e:
                    results.append({
                        "strategy_name": e["strategy_name"],
                        "overlap_start": max(a_s, b_s).strftime("%Y-%m-%dT%H:%M:%S"),
                        "overlap_end": min(a_e, b_e).strftime("%Y-%m-%dT%H:%M:%S"),
                    })
    return results


def _parse(iso_str):
    return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S")
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service.tests.TimelineTests build_protection_service.tests.ConflictTests -v 2`
Expected: PASS（7 个测试）。

- [ ] **Step 7: Commit**

```bash
git add backend/build_protection_service/services backend/build_protection_service/tests.py
git commit -m "feat(service): timeline 推送推导、conflict 阶段冲突、mutex 互斥检测"
```

---

### Task 5: 登录视图 + 权限挂载

**Files:**
- Create: `backend/build_protection_service/views/login.py`
- Modify: `backend/build_protection_service/views/urls.py`

- [ ] **Step 1: 写失败测试（登录换 token、认证失败 401、角色权限）**

在 `tests.py` 追加：

```python
from rest_framework.test import APIClient


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")

    def test_login_returns_token_and_user(self):
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "123456"}, format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json().get("data", {})
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "pm")

    def test_login_wrong_password_401(self):
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "wrong"}, format="json")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40101)

    def test_me_requires_auth(self):
        resp = self.client.get("/api/auth/me")
        self.assertTrue(resp.status_code >= 400)

    def test_pm_cannot_access_admin_only(self):
        token = self._login("pm1")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/admin/users")
        self.assertEqual(resp.status_code, 403)

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.AuthTests -v 2`
Expected: FAIL（URL /api/admin/users 未注册，返回 404）。

- [ ] **Step 3: 实现视图辅助与 login 视图**

在 `backend/build_protection_service/views/__init__.py` 写入：

```python
"""视图辅助：统一 JSON 响应 + 安全日志。"""
from django.contrib.auth import get_user_model
from django.http import JsonResponse

from ..models import SecurityLog

User = get_user_model()


def json_resp(payload, status=200):
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def security_log(action, username=""):
    try:
        SecurityLog.objects.create(username=username, action=action)
    except Exception:
        pass
```

创建 `backend/build_protection_service/views/login.py`：

```python
"""登录/登出/当前用户。"""
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from ..api import ok
from . import json_resp, security_log

User = get_user_model()


def _user_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "bound_version_id": getattr(user, "bound_version_id", None),
        "bound_version_name": getattr(getattr(user, "bound_version", None), "name", None),
    }


def login_view(request):
    body = getattr(request, "data", None) or {}
    username = body.get("username", "")
    password = body.get("password", "")
    user = User.objects.filter(username=username).first()
    if user is None or not user.check_password(password):
        security_log("login_failed", username=username)
        return json_resp({"code": 40101, "message": "用户名或密码错误", "data": None}, status=401)
    if not user.is_active:
        return json_resp({"code": 40301, "message": "账号已停用", "data": None}, status=403)
    refresh = RefreshToken.for_user(user)
    security_log("login_success", username=username)
    return json_resp(ok({"token": str(refresh.access_token), "user": _user_payload(user)}))


def logout_view(request):
    security_log("logout", username=getattr(request.user, "username", "") or "")
    return json_resp(ok())


def me_view(request):
    return json_resp(ok(_user_payload(request.user)))
```

- [ ] **Step 4: 挂载登录路由**

将 `backend/build_protection_service/views/urls.py` 替换为：

```python
from django.urls import path

from . import login, plan, strategies, weekly

app_name = "build_protection_service"

urlpatterns = [
    path("auth/login", login.login_view, name="login"),
    path("auth/logout", login.logout_view, name="logout"),
    path("auth/me", login.me_view, name="me"),
]
```

> 说明：后续任务会向 `urlpatterns` 追加 `plan`/`strategies`/`weekly` 等路由；本步先保留占位导入，若对应模块尚未创建会报错，请在本步仅挂载已存在的 `login`，其余在各自任务追加。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service.tests.AuthTests -v 2`
Expected: `test_login_returns_token_and_user`、`test_login_wrong_password_401`、`test_me_requires_auth` 通过；`test_pm_cannot_access_admin_only` 因 `/api/admin/users` 未实现返回 404 而非 403，将在 Task 9 实现后通过。

- [ ] **Step 6: Commit**

```bash
git add backend/build_protection_service/views/login.py backend/build_protection_service/views/urls.py backend/build_protection_service/views/__init__.py backend/build_protection_service/tests.py
git commit -m "feat(auth): 登录/登出/当前用户接口，JWT 签发"
```

---

### Task 6: strategies 视图（含 push_start_time、互斥、admin CRUD）

**Files:**
- Create: `backend/build_protection_service/views/strategies.py`
- Modify: `backend/build_protection_service/views/urls.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests.py`：

```python
from types import SimpleNamespace

from .services import conflict


class StrategyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.b2 = Branch.objects.create(version=self.version, name="TR5")
        self.tmpl = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
        self.token = self._login("pm1")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_create_strategy_with_push_start_time(self):
        self._auth(self.token)
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "27A-master-晚间", "build_start_time": "22:00",
            "push_start_time": "20:00", "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)
        self.assertEqual(resp.json()["data"]["push_start_time"], "20:00")

    def test_mutex_conflict_40902(self):
        # 同版本两支不同分支，构建时间重叠 → 40902
        from datetime import datetime
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="existing",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        self._auth(self.token)
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b2.id, "template_id": self.tmpl.id,
            "name": "new", "build_start_time": "22:10",
            "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)

    def test_stage_conflict_40901(self):
        # 同分支内冒烟/分析重叠 → 40901
        self._auth(self.token)
        self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "A", "build_start_time": "22:00", "push_mode": "normal", "enabled": True,
        }, format="json")
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "B", "build_start_time": "22:30", "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40901)

    def test_admin_can_create_for_any_version(self):
        self._auth(self._login("admin"))
        resp = self.client.post("/api/strategies", {
            "branch_id": self.b1.id, "template_id": self.tmpl.id,
            "name": "admin-new", "build_start_time": "23:00", "push_mode": "normal", "enabled": True,
        }, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_get_strategies_includes_push_start_time(self):
        self._auth(self.token)
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="s1", build_start_time="22:00",
            push_start_time="20:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.get("/api/strategies", {"version_id": self.version.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"][0]["push_start_time"], "20:00")

    def test_delete_strategy(self):
        self._auth(self.token)
        s = Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="del", build_start_time="23:00",
            push_mode="normal", created_by=self.pm,
        )
        resp = self.client.delete(f"/api/strategies/{s.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Strategy.objects.filter(id=s.id).exists())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.StrategyApiTests -v 2`
Expected: FAIL（URL 未注册）。

- [ ] **Step 3: 实现 strategies 视图**

创建 `backend/build_protection_service/views/strategies.py`：

```python
"""策略 views：列表/预览/创建/更新/启停/删除，含互斥与阶段冲突校验。"""
from django.conf import settings
from django.contrib.auth import get_user_model

from ..api import ok, err
from ..models import Branch, Strategy, StrategyChangeLog, StrategyTemplate
from ..services.mutex import check_build_mutex
from . import json_resp

User = get_user_model()


def _strategy_payload(s):
    return {
        "id": s.id,
        "branch_id": s.branch_id,
        "branch_name": s.branch.name,
        "version_id": s.branch.version_id,
        "version_name": s.branch.version.name,
        "template_id": s.template_id,
        "template_name": s.template.name,
        "name": s.name,
        "build_start_time": s.build_start_time,
        "push_start_time": s.push_start_time,
        "push_mode": s.push_mode,
        "enabled": s.enabled,
    }


def _check_pm_bound(user, branch):
    """PM 仅可操作本版本分支；admin 放开。"""
    if user.role == "admin":
        return None
    if user.role != "pm":
        return {"code": 40301, "message": "无权限操作策略", "status": 403}
    if branch.version.pm_user_id != user.id:
        return {"code": 40301, "message": "仅可操作本版本分支", "status": 403}
    return None


def _validate(user, branch, template, build_start_time, push_start_time,
              exclude_id=None, is_preview=False):
    """互斥 + 阶段冲突校验，返回 (error, conflict_obj)。"""
    version_id = branch.version_id
    mutex_hits = check_build_mutex(version_id, build_start_time, settings.BUILD_MINUTES, exclude_id)
    if mutex_hits:
        return ({"code": 40902, "message": "同一时间节点仅允许一个分支构建（资源互斥）", "status": 409},
                {"mutex": mutex_hits}), None

    from django.db.models import Q
    same_branch = Strategy.objects.filter(branch=branch, enabled=True)
    if exclude_id:
        same_branch = same_branch.exclude(id=exclude_id)
    existing = [{
        "build_start_time": s.build_start_time,
        "template": SimpleNamespaceTpl(s.template.smoke_minutes, s.template.analysis_minutes),
        "push_mode": s.push_mode,
        "strategy_name": s.name,
        "push_start_time": s.push_start_time,
    } for s in same_branch]
    cand = [{
        "build_start_time": build_start_time,
        "template": SimpleNamespaceTpl(template.smoke_minutes, template.analysis_minutes),
        "push_mode": "normal",
        "strategy_name": "candidate",
        "push_start_time": push_start_time,
    }]
    from ..services.conflict import detect_conflicts
    hits = detect_conflicts("2026-08-10", cand, existing, settings.BUILD_MINUTES,
                            settings.PUSH_MINUTES, settings.SYNC_BUFFER_MINUTES)
    if hits:
        return ({"code": 40901, "message": "阶段时间冲突，请调整构建时间", "status": 409},
                {"conflicts": hits}), None
    return None, None


class SimpleNamespaceTpl:
    def __init__(self, smoke, analysis):
        self.smoke_minutes = smoke
        self.analysis_minutes = analysis


def list_strategies(request):
    qs = Strategy.objects.select_related("branch", "branch__version", "template").all()
    version_id = request.GET.get("version_id")
    branch_id = request.GET.get("branch_id")
    if version_id:
        qs = qs.filter(branch__version_id=version_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return json_resp(ok([_strategy_payload(s) for s in qs]))


def preview_strategy(request):
    # 预览：仅返回相遇的互斥/冲突提示，不落库
    body = request.data
    branch = Branch.objects.filter(id=body.get("branch_id")).first()
    template = StrategyTemplate.objects.filter(id=body.get("template_id")).first()
    if not branch or not template:
        return json_resp(err(42201, "分支或模板不存在"), status=422)
    err_resp, conflict_obj = _validate(
        request.user, branch, template, body.get("build_start_time", "22:00"),
        body.get("push_start_time"),
        exclude_id=body.get("id"))
    if err_resp:
        conflict_obj = conflict_obj or {}
        return json_resp(ok({"conflict": {**err_resp, **conflict_obj}}))
    return json_resp(ok({"conflict": None}))


def create_strategy(request):
    body = request.data
    branch = Branch.objects.filter(id=body.get("branch_id")).first()
    template = StrategyTemplate.objects.filter(id=body.get("template_id")).first()
    if not branch or not template:
        return json_resp(err(42201, "分支或模板不存在"), status=422)
    perr = _check_pm_bound(request.user, branch)
    if perr:
        return json_resp(err(perr["code"], perr["message"]), status=perr["status"])
    err_resp, _ = _validate(request.user, branch, template, body.get("build_start_time"),
                            body.get("push_start_time"))
    if err_resp:
        return json_resp(err(err_resp["code"], err_resp["message"]), status=err_resp["status"])
    s = Strategy.objects.create(
        branch=branch, template=template, name=body.get("name"),
        build_start_time=body.get("build_start_time", "22:00"),
        push_start_time=body.get("push_start_time") or None,
        push_mode=body.get("push_mode", "normal"),
        enabled=body.get("enabled", True),
        created_by=request.user,
    )
    return json_resp(ok(_strategy_payload(s)))


def update_strategy(request, sid):
    s = Strategy.objects.select_related("branch").filter(id=sid).first()
    if not s:
        return json_resp(err(40401, "策略不存在"), status=404)
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return json_resp(err(perr["code"], perr["message"]), status=perr["status"])
    body = request.data
    branch = s.branch
    template = s.template
    build_start_time = body.get("build_start_time", s.build_start_time)
    push_start_time = body.get("push_start_time", s.push_start_time)
    err_resp, _ = _validate(request.user, branch, template, build_start_time,
                            push_start_time, exclude_id=s.id)
    if err_resp:
        return json_resp(err(err_resp["code"], err_resp["message"]), status=err_resp["status"])
    old = _strategy_payload(s)
    s.name = body.get("name", s.name)
    s.build_start_time = build_start_time
    s.push_start_time = push_start_time or None
    s.push_mode = body.get("push_mode", s.push_mode)
    s.enabled = body.get("enabled", s.enabled)
    s.save()
    StrategyChangeLog.objects.create(strategy=s, operator=request.user,
                                     change_desc=f"更新策略: {old['name']}")
    return json_resp(ok(_strategy_payload(s)))


def toggle_strategy(request, sid):
    s = Strategy.objects.filter(id=sid).first()
    if not s:
        return json_resp(err(40401, "策略不存在"), status=404)
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return json_resp(err(perr["code"], perr["message"]), status=perr["status"])
    s.enabled = not s.enabled
    s.save()
    return json_resp(ok(_strategy_payload(s)))


def delete_strategy(request, sid):
    s = Strategy.objects.filter(id=sid).first()
    if not s:
        return json_resp(err(40401, "策略不存在"), status=404)
    perr = _check_pm_bound(request.user, s.branch)
    if perr:
        return json_resp(err(perr["code"], perr["message"]), status=perr["status"])
    s.delete()
    return json_resp(ok())
```

- [ ] **Step 4: 挂载 strategies 路由**

在 `views/urls.py` 的 `urlpatterns` 追加：

```python
from . import strategies

urlpatterns += [
    path("strategies", strategies.list_strategies, name="strategies_list"),
    path("strategies/preview", strategies.preview_strategy, name="strategies_preview"),
    path("strategies", strategies.create_strategy, name="strategies_create"),
    path("strategies/<int:sid>", strategies.update_strategy, name="strategies_update"),
    path("strategies/<int:sid>/toggle", strategies.toggle_strategy, name="strategies_toggle"),
    path("strategies/<int:sid>", strategies.delete_strategy, name="strategies_delete"),
]
```

> 说明：`strategies` 同路径不同方法，Django 路由按 method 分发需在视图中判断 request.method。将 `list_strategies`/`create_strategy` 合并为单视图 `strategies_view` 更佳，见 Step 5 修正。

- [ ] **Step 5: 修正 strategies 汇合视图**

用 SearchReplace 将 `views/urls.py` 的 strategies 段替换为：

```python
from django.urls import path

from . import login, strategies

app_name = "build_protection_service"

urlpatterns = [
    path("auth/login", login.login_view, name="login"),
    path("auth/logout", login.logout_view, name="logout"),
    path("auth/me", login.me_view, name="me"),

    path("strategies", strategies.strategies_view, name="strategies"),
    path("strategies/preview", strategies.preview_strategy, name="strategies_preview"),
    path("strategies/<int:sid>", strategies.strategy_detail_view, name="strategy_detail"),
    path("strategies/<int:sid>/toggle", strategies.toggle_strategy, name="strategies_toggle"),
]
```

并在 `strategies.py` 末尾追加汇合视图：

```python
def strategies_view(request):
    if request.method == "GET":
        return list_strategies(request)
    if request.method == "POST":
        return create_strategy(request)
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def strategy_detail_view(request, sid):
    if request.method == "PATCH":
        return update_strategy(request, sid)
    if request.method == "DELETE":
        return delete_strategy(request, sid)
    return json_resp(err(42201, "不支持的请求方法"), status=422)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service.tests.StrategyApiTests -v 2`
Expected: PASS（6 个测试）。

> 若 `test_mutex_conflict_40902` 失败，检查 `build_start_time` 22:00 与 22:10 的构建重叠（build_min=30，22:00~22:30 与 22:10~22:40 重叠）逻辑正确；若 `test_stage_conflict_40901` 失败，检查冒烟阶段重叠（22:30 构建的冒烟 22:30~次日07:30 与 22:00 策略的冒烟重叠）。

- [ ] **Step 7: Commit**

```bash
git add backend/build_protection_service/views/strategies.py backend/build_protection_service/views/urls.py backend/build_protection_service/tests.py
git commit -m "feat(strategy): 策略 CRUD + 互斥/阶段冲突校验 + push_start_time"
```

---

### Task 7: plan 视图（含 push_start_time）

**Files:**
- Create: `backend/build_protection_service/views/plan.py`
- Modify: `backend/build_protection_service/views/urls.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests.py`：

```python
class PlanApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
        self.token = self._login("pm1")

    def _login(self):
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_plan_returns_push_start_time_and_timeline(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login()}")
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="s1", build_start_time="22:00",
            push_start_time="20:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.get("/api/plan", {"date": "2026-08-10"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        ver = next(v for v in data if v["version_id"] == self.version.id)
        br = ver["branches"][0]
        st = br["strategies"][0]
        self.assertEqual(st["push_start_time"], "20:00")
        self.assertIsNotNone(st["timeline"]["push"])
        self.assertEqual(st["timeline"]["build"]["start"], "2026-08-10T22:00:00")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.PlanApiTests -v 2`
Expected: FAIL（URL 未注册）。

- [ ] **Step 3: 实现 plan 视图**

创建 `backend/build_protection_service/views/plan.py`：

```python
"""版本计划：版本→分支→策略→时间线。"""
from django.conf import settings
from django.db.models import Q

from ..api import ok
from ..models import Strategy, Version
from ..services.timeline import build_timeline
from . import json_resp


def plan_view(request):
    ds = request.GET.get("date", "2026-08-10")
    versions = Version.objects.select_related("pm_user").prefetch_related(
        "branches__strategies__template"
    ).all()
    result = []
    for v in versions:
        branches = []
        for b in v.branches.all():
            strategies = []
            for s in b.strategies.filter(enabled=True).select_related("template"):
                tl = build_timeline(
                    ds, s.build_start_time, s.template.smoke_minutes, s.template.analysis_minutes,
                    settings.BUILD_MINUTES, settings.PUSH_MINUTES, settings.SYNC_BUFFER_MINUTES,
                    s.push_mode, push_start_time=s.push_start_time,
                )
                strategies.append({
                    "id": s.id,
                    "name": s.name,
                    "push_mode": s.push_mode,
                    "build_start_time": s.build_start_time,
                    "push_start_time": s.push_start_time,
                    "enabled": s.enabled,
                    "conflict": False,
                    "timeline": tl,
                    "status": _round_status(s),
                })
            branches.append({
                "branch_id": b.id,
                "branch_name": b.name,
                "strategies": strategies,
            })
        result.append({
            "version_id": v.id,
            "version_name": v.name,
            "pm_name": v.pm_user.display_name or v.pm_user.username,
            "branches": branches,
        })
    return json_resp(ok(result))


def _round_status(s):
    """取最近一个执行轮次的结论作状态。"""
    r = s.rounds.order_by("-exec_date").first()
    if not r:
        return None
    return r.conclusion or "pending"
```

- [ ] **Step 4: 挂载 plan 路由**

在 `views/urls.py` 追加：

```python
from . import plan

urlpatterns += [
    path("plan", plan.plan_view, name="plan"),
]
```

并在 `urlpatterns` 顶部补齐导入（若已存在则跳过）。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service.tests.PlanApiTests -v 2`
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/build_protection_service/views/plan.py backend/build_protection_service/views/urls.py backend/build_protection_service/tests.py
git commit -m "feat(plan): 版本计划接口含 push_start_time 与时间线"
```

---

### Task 8: weekly 视图（新增）

**Files:**
- Create: `backend/build_protection_service/views/weekly.py`
- Modify: `backend/build_protection_service/views/urls.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests.py`：

```python
class WeeklyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.b2 = Branch.objects.create(version=self.version, name="TR5")
        self.tmpl = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
        self.token = self._login()

    def _login(self):
        resp = self.client.post("/api/auth/login", {"username": "pm1", "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_weekly_returns_week_info_and_days(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        Strategy.objects.create(
            branch=self.b1, template=self.tmpl, name="27A-master-晚间",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        Strategy.objects.create(
            branch=self.b2, template=self.tmpl, name="27A-TR5-晚间",
            build_start_time="23:00", push_mode="normal", created_by=self.pm,
        )
        resp = self.client.get("/api/weekly", {"week_start": "2026-08-10", "version_id": self.version.id})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual(data["days"][0]["date"], "2026-08-10")
        # 汇总所有策略
        self.assertGreaterEqual(len(data["branches"]), 2)
        self.assertGreaterEqual(len(data["strategies"]), 2)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.WeeklyApiTests -v 2`
Expected: FAIL（URL 未注册）。

- [ ] **Step 3: 实现 weekly 视图**

创建 `backend/build_protection_service/views/weekly.py`：

```python
"""周视图：指定周的开始日期 + 版本 → 分支策略排布。"""
from datetime import datetime, timedelta

from django.conf import settings

from ..api import ok
from ..models import Branch, Version
from ..services.timeline import build_timeline
from . import json_resp


def _weekdays(week_start):
    start = datetime.strptime(week_start, "%Y-%m-%d").date()
    return [
        {"date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
         "weekday": (start + timedelta(days=i)).strftime("%A")}
        for i in range(7)
    ]


def weekly_view(request):
    week_start = request.GET.get("week_start", _default_monday())
    version_id = request.GET.get("version_id")
    version = None
    versions = list(Version.objects.select_related("pm_user").all())
    if version_id:
        version = Version.objects.filter(id=version_id).first()
    branches = []
    strategies = []
    if version:
        for b in version.branches.all().order_by("name"):
            branches.append({"branch_id": b.id, "branch_name": b.name})
        for s in version.branches.values_list("id", flat=True):
            pass
        qs = Branch.objects.filter(version=version).prefetch_related("strategies__template")
        for b in qs:
            for s in b.strategies.filter(enabled=True).select_related("template").order_by("build_start_time"):
                strategies.append({
                    "strategy_id": s.id,
                    "strategy_name": s.name,
                    "branch_id": b.id,
                    "branch_name": b.name,
                    "build_start_time": s.build_start_time,
                    "push_start_time": s.push_start_time,
                    "template_name": s.template.name,
                })
    return json_resp(ok({
        "week_start": week_start,
        "days": _weekdays(week_start),
        "version": {"version_id": version.id, "version_name": version.name} if version else None,
        "versions": [{"version_id": v.id, "version_name": v.name} for v in versions],
        "branches": branches,
        "strategies": strategies,
    }))


def _default_monday():
    today = datetime.now().date()
    return (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
```

- [ ] **Step 4: 挂载 weekly 路由**

在 `views/urls.py` 追加：

```python
from . import weekly

urlpatterns += [
    path("weekly", weekly.weekly_view, name="weekly"),
]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service.tests.WeeklyApiTests -v 2`
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/build_protection_service/views/weekly.py backend/build_protection_service/views/urls.py backend/build_protection_service/tests.py
git commit -m "feat(weekly): 周视图接口"
```

---

### Task 9: admin 视图（版本/用户/模板/配置/日志 + 策略 CRUD）

**Files:**
- Create: `backend/build_protection_service/views/admin.py`
- Modify: `backend/build_protection_service/views/urls.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests.py`：

```python
class AdminApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.token = self._login("admin")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_create_version_and_branch(self):
        self._auth(self.token)
        resp = self.client.post("/api/admin/versions", {"name": "28A", "pm_user_id": self.pm.id, "status": "active"}, format="json")
        self.assertEqual(resp.status_code, 200)
        vid = resp.json()["data"]["id"]
        resp2 = self.client.post(f"/api/admin/versions/{vid}/branches", {"name": "master"}, format="json")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["data"]["name"], "master")

    def test_pm_cannot_access_admin_user_list(self):
        self._auth(self._login("pm1"))
        resp = self.client.get("/api/admin/users")
        self.assertEqual(resp.status_code, 403)

    def test_admin_config_update(self):
        self._auth(self.token)
        resp = self.client.put("/api/admin/config", {"build_minutes": 45}, format="json")
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.AdminApiTests -v 2`
Expected: FAIL（URL 未注册）。

- [ ] **Step 3: 实现 admin 视图**

创建 `backend/build_protection_service/views/admin.py`：

```python
"""系统管理：版本/分支/用户/模板/配置/日志。仅 admin。"""
from django.conf import settings
from django.contrib.auth import get_user_model

from ..api import ok, err
from ..models import AdminOpLog, Branch, StrategyTemplate, Version
from . import json_resp

User = get_user_model()


_VALID_ROLES = {"admin", "pm", "builder", "tester", "integrator"}


def _admin_log(user, action, target_type="", target_id="", detail=""):
    try:
        AdminOpLog.objects.create(operator=user, action=action, target_type=target_type,
                                  target_id=str(target_id), detail=detail)
    except Exception:
        pass


def extra_view(request):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    if request.method == "GET":
        return list_versions(request)
    if request.method == "POST":
        return create_version(request)
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def list_versions(request):
    data = [
        {"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status}
        for v in Version.objects.select_related("pm_user").all()
    ]
    return json_resp(ok(data))


def create_version(request):
    body = request.data
    name = body.get("name")
    pm = User.objects.filter(id=body.get("pm_user_id")).first()
    if not name or not pm:
        return json_resp(err(42201, "缺少版本名或PM"), status=422)
    if Version.objects.filter(name=name).exists():
        return json_resp(err(40902, "版本已存在"), status=409)
    v = Version.objects.create(name=name, pm_user=pm, status=body.get("status", "active"))
    _admin_log(request.user, "create_version", "version", v.id, name)
    return json_resp(ok({"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status}))


def update_version(request, vid):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    v = Version.objects.filter(id=vid).first()
    if not v:
        return json_resp(err(40401, "版本不存在"), status=404)
    body = request.data
    pm = User.objects.filter(id=body.get("pm_user_id", v.pm_user_id)).first()
    v.name = body.get("name", v.name)
    v.pm_user = pm
    v.status = body.get("status", v.status)
    v.save()
    _admin_log(request.user, "update_version", "version", v.id)
    return json_resp(ok({"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id, "status": v.status}))


def add_branch(request, vid):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    v = Version.objects.filter(id=vid).first()
    if not v:
        return json_resp(err(40401, "版本不存在"), status=404)
    name = request.data.get("name")
    if not name:
        return json_resp(err(42201, "缺少分支名"), status=422)
    if Branch.objects.filter(version=v, name=name).exists():
        return json_resp(err(40902, "分支已存在"), status=409)
    b = Branch.objects.create(version=v, name=name)
    _admin_log(request.user, "add_branch", "branch", b.id, name)
    return json_resp(ok({"id": b.id, "name": b.name, "version_id": v.id}))


def users_view(request):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    if request.method == "GET":
        data = [{"id": u.id, "username": u.username, "display_name": u.display_name or u.username,
                 "role": u.role, "is_active": u.is_active} for u in User.objects.all()]
        return json_resp(ok(data))
    if request.method == "POST":
        body = request.data
        username = body.get("username")
        if User.objects.filter(username=username).exists():
            return json_resp(err(40902, "用户名已存在"), status=409)
        role = body.get("role", "builder")
        if role not in _VALID_ROLES:
            return json_resp(err(42201, "非法角色"), status=422)
        u = User.objects.create_user(username=username, password=body.get("password", "123456"),
                                     role=role, display_name=body.get("display_name", username))
        _admin_log(request.user, "create_user", "user", u.id, username)
        return json_resp(ok({"id": u.id, "username": u.username, "role": u.role}))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def update_user(request, uid):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    u = User.objects.filter(id=uid).first()
    if not u:
        return json_resp(err(40401, "用户不存在"), status=404)
    body = request.data
    if body.get("password"):
        u.set_password(body["password"])
    u.role = body.get("role", u.role)
    u.display_name = body.get("display_name", u.display_name)
    u.is_active = body.get("is_active", u.is_active)
    u.save()
    _admin_log(request.user, "update_user", "user", u.id)
    return json_resp(ok({"id": u.id, "username": u.username, "role": u.role}))


def templates_view(request):
    if request.user.role not in ("admin", "pm"):
        return json_resp(err(40301, "无权限"), status=403)
    if request.method == "GET":
        data = [{"id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
                 "analysis_minutes": t.analysis_minutes, "description": t.description}
                for t in StrategyTemplate.objects.all()]
        return json_resp(ok(data))
    if request.method == "POST":
        if request.user.role != "admin":
            return json_resp(err(40301, "仅管理员可操作"), status=403)
        body = request.data
        t = StrategyTemplate.objects.create(
            name=body.get("name"), smoke_minutes=body.get("smoke_minutes", 0),
            analysis_minutes=body.get("analysis_minutes", 0), description=body.get("description", ""),
        )
        _admin_log(request.user, "create_template", "template", t.id)
        return json_resp(ok({"id": t.id, "name": t.name}))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def update_template(request, tid):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    t = StrategyTemplate.objects.filter(id=tid).first()
    if not t:
        return json_resp(err(40401, "模板不存在"), status=404)
    body = request.data
    t.name = body.get("name", t.name)
    t.smoke_minutes = body.get("smoke_minutes", t.smoke_minutes)
    t.analysis_minutes = body.get("analysis_minutes", t.analysis_minutes)
    t.description = body.get("description", t.description)
    t.save()
    _admin_log(request.user, "update_template", "template", t.id)
    return json_resp(ok({"id": t.id, "name": t.name}))


def delete_template(request, tid):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    t = StrategyTemplate.objects.filter(id=tid).first()
    if not t:
        return json_resp(err(40401, "模板不存在"), status=404)
    t.delete()
    _admin_log(request.user, "delete_template", "template", tid)
    return json_resp(ok())


def config_view(request):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    if request.method == "GET":
        return json_resp(ok({
            "build_minutes": settings.BUILD_MINUTES,
            "push_minutes": settings.PUSH_MINUTES,
            "sync_buffer_minutes": settings.SYNC_BUFFER_MINUTES,
        }))
    if request.method == "PUT":
        body = request.data
        if "build_minutes" in body and isinstance(body["build_minutes"], int):
            settings.BUILD_MINUTES = body["build_minutes"]
        if "push_minutes" in body and isinstance(body["push_minutes"], int):
            settings.PUSH_MINUTES = body["push_minutes"]
        if "sync_buffer_minutes" in body and isinstance(body["sync_buffer_minutes"], int):
            settings.SYNC_BUFFER_MINUTES = body["sync_buffer_minutes"]
        _admin_log(request.user, "update_config", "config", "", str(body))
        return json_resp(ok({"build_minutes": settings.BUILD_MINUTES}))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def logs_view(request, kind):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    if kind == "operations":
        qs = AdminOpLog.objects.select_related("operator").order_by("-id")[:200]
        data = [{"id": l.id, "operator": l.operator.username if l.operator else "",
                 "action": l.action, "target_type": l.target_type, "target_id": l.target_id,
                 "detail": l.detail, "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S")}
                for l in qs]
    else:
        from ..models import SecurityLog
        qs = SecurityLog.objects.order_by("-id")[:200]
        data = [{"id": l.id, "username": l.username, "action": l.action,
                 "detail": l.detail, "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S")}
                for l in qs]
    return json_resp(ok(data))
```

- [ ] **Step 4: 挂载 admin 路由**

在 `views/urls.py` 追加：

```python
from . import admin

urlpatterns += [
    path("admin/versions", admin.extra_view, name="admin_versions"),
    path("admin/versions/<int:vid>", admin.update_version, name="admin_version_update"),
    path("admin/versions/<int:vid>/branches", admin.add_branch, name="admin_branch_add"),
    path("admin/users", admin.users_view, name="admin_users"),
    path("admin/users/<int:uid>", admin.update_user, name="admin_user_update"),
    path("admin/templates", admin.templates_view, name="admin_templates"),
    path("admin/templates/<int:tid>", admin.update_template, name="admin_template_update"),
    path("admin/templates/<int:tid>", admin.delete_template, name="admin_template_delete"),
    path("admin/config", admin.config_view, name="admin_config"),
    path("admin/logs/<str:kind>", admin.logs_view, name="admin_logs"),
]
```

> 说明：`admin/templates/<int:tid>` 同路径不同 method，用单一汇合视图 `template_detail_view` 更佳，见 Step 5 修正。

- [ ] **Step 5: 修正模板汇合视图**

在 `admin.py` 追加：

```python
def template_detail_view(request, tid):
    if request.user.role != "admin":
        return json_resp(err(40301, "仅管理员可操作"), status=403)
    if request.method == "PATCH":
        return update_template(request, tid)
    if request.method == "DELETE":
        return delete_template(request, tid)
    return json_resp(err(42201, "不支持的请求方法"), status=422)
```

并在 `views/urls.py` 中将两条 `admin/templates/<int:tid>` 替换为一条：

```python
path("admin/templates/<int:tid>", admin.template_detail_view, name="admin_template_detail"),
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service.tests.AdminApiTests -v 2`
Expected: PASS（3 个测试）。同时重新运行 `AuthTests.test_pm_cannot_access_admin_only` 应通过（403）。

- [ ] **Step 7: Commit**

```bash
git add backend/build_protection_service/views/admin.py backend/build_protection_service/views/urls.py backend/build_protection_service/tests.py
git commit -m "feat(admin): 版本/用户/模板/配置/日志管理接口"
```

---

### Task 10: executions / logs 视图

**Files:**
- Create: `backend/build_protection_service/views/executions.py`
- Create: `backend/build_protection_service/views/logs.py`
- Modify: `backend/build_protection_service/views/urls.py`

- [ ] **Step 1: 写失败测试**

追加到 `tests.py`：

```python
class ExecutionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.tester = User.objects.create_user(username="tester", password="123456", role="tester")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.b1 = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="t", smoke_minutes=480, analysis_minutes=120)
        self.s = Strategy.objects.create(branch=self.b1, template=self.tmpl, name="s1",
                                         build_start_time="22:00", push_mode="normal", created_by=self.pm)
        self.round = ExecutionRound.objects.create(strategy=self.s, exec_date="2026-08-10")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def test_executions_list(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.get("/api/executions")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()["data"]), 1)

    def test_tester_submits_conclusion(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('tester')}")
        resp = self.client.post(f"/api/executions/rounds/{self.round.id}/conclusion",
                                {"conclusion": "pass", "note": "ok"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.round.refresh_from_db()
        self.assertEqual(self.round.conclusion, "pass")

    def test_logs_execution(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._login('pm1')}")
        resp = self.client.get("/api/logs/execution")
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.ExecutionApiTests -v 2`
Expected: FAIL（URL 未注册）。

- [ ] **Step 3: 实现 executions 视图**

创建 `backend/build_protection_service/views/executions.py`：

```python
"""执行记录：轮次列表、详情、结论提交。"""
from datetime import timedelta

from django.utils.timezone import now

from ..api import ok, err
from ..models import ExecutionLog, ExecutionRound, Strategy
from . import json_resp


def _round_payload(r):
    return {
        "id": r.id, "strategy_id": r.strategy_id, "strategy_name": r.strategy.name,
        "exec_date": r.exec_date.strftime("%Y-%m-%d"),
        "build_start_at": _fmt(r.build_start_at), "build_end_at": _fmt(r.build_end_at),
        "smoke_start_at": _fmt(r.smoke_start_at), "smoke_end_at": _fmt(r.smoke_end_at),
        "conclusion": r.conclusion, "note": r.note, "push_status": r.push_status,
    }


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def executions_view(request):
    qs = ExecutionRound.objects.select_related("strategy", "strategy__branch").order_by("-id")
    if request.user.role == "pm":
        qs = qs.filter(strategy__branch__version__pm_user=request.user)
    return json_resp(ok([_round_payload(r) for r in qs[:200]]))


def round_detail(request, rid):
    r = ExecutionRound.objects.select_related("strategy").filter(id=rid).first()
    if not r:
        return json_resp(err(40401, "轮次不存在"), status=404)
    logs = ExecutionLog.objects.filter(round=r).order_by("id")
    return json_resp(ok({"round": _round_payload(r), "logs": [
        {"id": l.id, "stage": l.stage, "message": l.message,
         "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S")} for l in logs]}))


def conclusion_view(request, rid):
    r = ExecutionRound.objects.filter(id=rid).first()
    if not r:
        return json_resp(err(40401, "轮次不存在"), status=404)
    if request.user.role != "tester":
        return json_resp(err(40301, "仅测试人员可提交结论"), status=403)
    body = request.data
    r.conclusion = body.get("conclusion")
    r.note = body.get("note", r.note or "")
    r.analysis_end_at = now()
    # normal + pass 自动推送
    if r.conclusion == "pass" and r.strategy.push_mode == "normal":
        r.push_start_at = r.analysis_end_at
        r.push_end_at = r.analysis_end_at + timedelta(minutes=20)
        r.push_status = "pushed"
    r.save()
    return json_resp(ok(_round_payload(r)))
```

- [ ] **Step 4: 实现 logs 视图**

创建 `backend/build_protection_service/views/logs.py`：

```python
"""执行日志与变更日志。"""
from ..api import ok
from ..models import ExecutionLog, StrategyChangeLog
from . import json_resp


def execution_logs(request):
    qs = ExecutionLog.objects.select_related("round", "round__strategy").order_by("-id")[:200]
    return json_resp(ok([{"id": l.id, "round_id": l.round_id, "strategy": l.round.strategy.name,
                          "stage": l.stage, "message": l.message,
                          "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S")} for l in qs]))


def change_logs(request):
    qs = StrategyChangeLog.objects.select_related("strategy", "operator").order_by("-id")[:200]
    return json_resp(ok([{"id": l.id, "strategy": l.strategy.name,
                          "operator": l.operator.username if l.operator else "",
                          "change_desc": l.change_desc,
                          "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S")} for l in qs]))
```

- [ ] **Step 5: 挂载路由**

在 `views/urls.py` 追加：

```python
from . import executions, logs

urlpatterns += [
    path("executions", executions.executions_view, name="executions"),
    path("executions/rounds/<int:rid>", executions.round_detail, name="round_detail"),
    path("executions/rounds/<int:rid>/conclusion", executions.conclusion_view, name="round_conclusion"),
    path("logs/execution", logs.execution_logs, name="execution_logs"),
    path("logs/changes", logs.change_logs, name="change_logs"),
]
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service.tests.ExecutionApiTests -v 2`
Expected: PASS（3 个测试）。

- [ ] **Step 7: Commit**

```bash
git add backend/build_protection_service/views/executions.py backend/build_protection_service/views/logs.py backend/build_protection_service/views/urls.py backend/build_protection_service/tests.py
git commit -m "feat(execution): 执行轮次/结论/日志接口"
```

---

### Task 11: 种子数据 + 全量测试通过

**Files:**
- Create: `backend/build_protection_service/management/__init__.py`
- Create: `backend/build_protection_service/management/commands/__init__.py`
- Create: `backend/build_protection_service/management/commands/seed.py`
- Modify: `backend/scripts/prestart.ps1`

- [ ] **Step 1: 写失败测试（种子数据冒烟）**

追加到 `tests.py`：

```python
from django.core.management import call_command


class SeedTests(TestCase):
    def test_seed_creates_admin_and_demo_data(self):
        User.objects.all().delete()
        call_command("seed")
        self.assertTrue(User.objects.filter(username="admin", role="admin").exists())
        self.assertTrue(Version.objects.filter(name="27A").exists())
        self.assertTrue(Strategy.objects.count() >= 1)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend; python manage.py test build_protection_service.tests.SeedTests -v 2`
Expected: FAIL（CommandError: 找不到命令 seed）。

- [ ] **Step 3: 实现 seed 命令**

创建 `backend/build_protection_service/management/__init__.py`、`management/commands/__init__.py`、`management/commands/seed.py`。`seed.py` 内容：

```python
"""种子数据：admin 超管 + 演示用户/版本/分支/模板/策略。"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from ...models import Branch, Strategy, StrategyTemplate, Version

User = get_user_model()


class Command(BaseCommand):
    help = "创建初始超管与演示数据"

    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            username=settings.FIRST_SUPERUSER,
            defaults={"role": "admin", "display_name": "系统管理员"},
        )
        if created:
            admin.set_password(settings.FIRST_SUPERUSER_PASSWORD)
            admin.save()

        if not User.objects.filter(username="pm27a").exists():
            pm27a = User.objects.create_user(username="pm27a", password="123456", role="pm", display_name="27A负责人")
            pm27b = User.objects.create_user(username="pm27b", password="123456", role="pm", display_name="27B负责人")
            User.objects.create_user(username="builder", password="123456", role="builder", display_name="构建人员")
            User.objects.create_user(username="tester", password="123456", role="tester", display_name="测试人员")
            User.objects.create_user(username="integrator", password="123456", role="integrator", display_name="集成人员")

            v27a = Version.objects.create(name="27A", pm_user=pm27a, status="active")
            v27b = Version.objects.create(name="27B", pm_user=pm27b, status="active")
            bm = Branch.objects.create(version=v27a, name="master")
            btr5 = Branch.objects.create(version=v27a, name="TR5")
            bm27b = Branch.objects.create(version=v27b, name="master")

            t_full = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
            t_quick = StrategyTemplate.objects.create(name="午间快速冒烟", smoke_minutes=60, analysis_minutes=30)

            Strategy.objects.create(branch=bm, template=t_full, name="27A-master-晚间全量",
                                    build_start_time="22:00", push_mode="normal", created_by=pm27a)
            Strategy.objects.create(branch=bm, template=t_quick, name="27A-master-午间快速",
                                    build_start_time="12:00", push_mode="normal", created_by=pm27a)
            Strategy.objects.create(branch=btr5, template=t_full, name="27A-TR5-晚间全量",
                                    build_start_time="21:00", push_mode="normal", created_by=pm27a)
            Strategy.objects.create(branch=bm27b, template=t_full, name="27B-master-晚间全量",
                                    build_start_time="22:30", push_start_time="20:00",
                                    push_mode="normal", created_by=pm27b)

        self.stdout.write(self.style.SUCCESS("种子数据创建完成"))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend; python manage.py test build_protection_service -v 2`
Expected: 全部测试（Model/Auth/Timeline/Conflict/Strategy/Plan/Weekly/Admin/Execution/Seed）PASS。

- [ ] **Step 5: 后端启动冒烟**

Run: `cd backend; python manage.py migrate; python manage.py seed; python manage.py runserver 8000`
Expected: 服务启动，无报错。

- [ ] **Step 6: Commit**

```bash
git add backend/build_protection_service/management backend/scripts/prestart.ps1
git commit -m "feat(seed): 种子数据命令与全量测试通过"
```

---

## 前端（Task 12-16）

### Task 12: 前端 api 层扩展（push_start_time + weekly + admin 策略 CRUD）

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/strategy.ts`
- Modify: `frontend/src/api/plan.ts`
- Create: `frontend/src/api/weekly.ts`
- Modify: `frontend/src/api/admin.ts`

- [ ] **Step 1: types.ts 增加 push_start_time 与 weekly 类型**

在 `frontend/src/api/types.ts` 的 `StrategyItem` 接口中 `push_mode` 字段后追加：

```ts
  push_start_time?: string | null; // 推送固定时间 HH:MM（可空，空则结论后动态推导）
```

在文件末尾追加 weekly 相关类型：

```ts
/** 周视图单日 */
export interface WeeklyDay {
  date: string; // "YYYY-MM-DD"
  weekday: number; // 1-7（周一=1）
  label: string; // "周一"
}

/** 周视图策略条目 */
export interface WeeklyStrategy {
  id: number;
  name: string;
  branch_id: number;
  branch_name: string;
  build_start_time: string; // "HH:mm"
  push_start_time?: string | null;
  push_mode: string;
  template_name: string;
  enabled: boolean;
}

/** 周视图分支分组 */
export interface WeeklyBranch {
  branch_id: number;
  branch_name: string;
  strategies: WeeklyStrategy[];
}

/** 周视图数据 */
export interface WeeklyData {
  week_start: string; // "YYYY-MM-DD"（周一）
  week_number: number; // 今年第几周
  days: WeeklyDay[]; // 7 天
  version_id: number;
  version_name: string;
  branches: WeeklyBranch[];
}
```

- [ ] **Step 2: strategy.ts 的 StrategyForm 增加 push_start_time**

在 `frontend/src/api/strategy.ts` 的 `StrategyForm` 接口 `push_mode` 后追加：

```ts
  push_start_time?: string | null;
```

- [ ] **Step 3: plan.ts 的 PlanStrategy 增加 push_start_time**

在 `frontend/src/api/plan.ts` 的 `PlanStrategy` 接口 `build_start_time` 后追加：

```ts
  push_start_time?: string | null;
```

- [ ] **Step 4: 新建 weekly.ts**

创建 `frontend/src/api/weekly.ts`：

```ts
// 周视图 API 模块
// 契约基准：设计文档 7.2 GET /api/weekly?week=...&version_id=...
import http from "@/api/http";
import type { WeeklyData } from "@/api/types";

/** 获取周视图数据 */
export function getWeekly(params: {
  week?: string; // "YYYY-MM-DD"（该周任一天，后端归一化到周一）
  version_id?: number;
}): Promise<WeeklyData> {
  return http.get("/weekly", { params });
}
```

- [ ] **Step 5: admin.ts 增加策略完整 CRUD**

在 `frontend/src/api/admin.ts` 的 `adminApi` 对象末尾（`updateConfig` 之后）追加策略管理方法（前缀仍 /api/admin，管理员可操作任意版本策略）：

```ts
  // ---- 策略管理（管理员全量 CRUD，写入管理操作日志） ----
  getAdminStrategies: (params?: {
    version_id?: number;
    branch_id?: number;
  }): Promise<import("@/api/types").StrategyItem[]> =>
    http.get("/admin/strategies", { params }),
  createAdminStrategy: (d: import("./strategy").StrategyForm): Promise<import("@/api/types").StrategyItem> =>
    http.post("/admin/strategies", d),
  updateAdminStrategy: (
    id: number,
    d: import("./strategy").StrategyForm
  ): Promise<import("@/api/types").StrategyItem> =>
    http.patch(`/admin/strategies/${id}`, d),
  toggleAdminStrategy: (id: number, enabled: boolean): Promise<import("@/api/types").StrategyItem> =>
    http.patch(`/admin/strategies/${id}/toggle`, null, { params: { enabled } }),
  deleteAdminStrategy: (id: number): Promise<void> =>
    http.delete(`/admin/strategies/${id}`)
```

- [ ] **Step 6: 前端类型检查**

Run: `cd frontend; npx vue-tsc --noEmit`
Expected: 无新增类型错误（tsc 通过或仅既有警告）。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/strategy.ts frontend/src/api/plan.ts frontend/src/api/weekly.ts frontend/src/api/admin.ts
git commit -m "feat(api): 前端 api 层扩展 push_start_time 与 weekly、admin 策略 CRUD"
```

---

### Task 13: 版本计划页优化（详情面板 + 修复控制台报错）

**Files:**
- Modify: `frontend/src/views/plan/index.vue`

目标：点击甘图任意阶段色块，其下方展开详情面板（参考全景页样式）；修复现有控制台报错（空 timeline / 空 push / phaseKey 解析）。

- [ ] **Step 1: 修复控制台报错（空 timeline / 空 push 健壮性）**

在 `frontend/src/views/plan/index.vue` 的 `script` 中，将 `buildRows` 内对 `tl` 的处理改为安全访问，并新增 `selectedStrategy` 状态。替换 `// ---- 数据 ----` 区块下的 `const rows = ref<GanttRow[]>([]);` 之后追加：

```ts
// 点击选中的策略详情（点击色块展示）
const selectedStrategy = ref<import("@/api/plan").PlanStrategy | null>(null);
const selectedStrategyName = ref("");
const selectedVersionName = ref("");
const executions = ref<import("@/api/types").RoundItem[]>([]);
const detailLoading = ref(false);
```

将 `buildRows` 函数中 `const tl = s.timeline; if (tl) {` 的色块构建逻辑改为对空 push 安全处理（`tl.push` 为 null 时跳过推送色块，但保留其它阶段色块）；阶段色块额外携带 `strategyName` 与 `stage` 供详情点击回查。在 `buildRows` 中 `phases.push(` 的每个阶段对象里追加 `strategyName: s.name`。

- [ ] **Step 2: 实现点击色块展示详情**

在 `plan/index.vue` 的 `script` 追加 `onBarSelect` 方法（替代/补充 `onRowClick`，不再仅限 PM）：

```ts
/** 点击任意色块：展示策略详情（配置 + 时间线 + 执行历史） */
async function onBarSelect(row: GanttRow, bar: import("@infectoone/vue-ganttastic").GanttBarObject) {
  const id = Number((bar?.phaseKey || "").split("-")[0]);
  if (!id) return;
  // 从 planData 定位该策略
  for (const v of planData.value) {
    for (const b of v.branches) {
      const s = b.strategies.find(x => x.id === id);
      if (s) {
        selectedVersionName.value = v.version_name;
        selectedStrategyName.value = s.name;
        selectedStrategy.value = s;
        await loadDetailExecutions(id);
        return;
      }
    }
  }
}

/** 加载选中策略近 7 天执行历史 */
async function loadDetailExecutions(strategyId: number) {
  detailLoading.value = true;
  try {
    const { getExecutions } = await import("@/api/panorama");
    executions.value = await getExecutions({
      strategy_id: strategyId,
      from: dayjs().subtract(6, "day").format("YYYY-MM-DD"),
      to: dayjs().format("YYYY-MM-DD")
    });
  } finally {
    detailLoading.value = false;
  }
}
```

将模板中 `<GanttGanttastic ... @click-row="onRowClick" />` 改为同时绑定新事件：`@click-row="onBarSelect"`（保留 `onRowClick` 的 PM 跳转逻辑，在其内部先调用 `onBarSelect`，再判断 PM 跳转）。

- [ ] **Step 3: 追加详情面板模板**

在 `plan/index.vue` 的模板中，`<GanttGanttastic>` 容器之后、`</div>` 之前追加详情面板：

```html
    <!-- 策略详情面板 -->
    <div v-if="selectedStrategy" class="detail-panel">
      <div class="detail-head">
        <span class="detail-title">策略详情：{{ selectedStrategyName }}</span>
        <span class="detail-sub">{{ selectedVersionName }} / {{ selectedStrategy.branch_name }}</span>
        <el-button size="small" text @click="selectedStrategy = null; executions = []">关闭</el-button>
      </div>
      <el-descriptions :column="3" size="small" border class="detail-desc">
        <el-descriptions-item label="构建开始">{{ selectedStrategy.build_start_time }}</el-descriptions-item>
        <el-descriptions-item label="推送时间">{{ selectedStrategy.push_start_time || "结论后推导" }}</el-descriptions-item>
        <el-descriptions-item label="推送模式">
          {{ selectedStrategy.push_mode === "sync" ? "同步推送冒烟" : "正常流程推送" }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="detail-sec-title">时间线</div>
      <div v-if="selectedStrategy.timeline" class="detail-timeline">
        <span v-for="p in detailPhases" :key="p.stage" class="dt-item">
          <i class="dt-dot" :style="{ background: p.color }"></i>
          {{ p.label }}：{{ p.text }}
        </span>
      </div>
      <div v-else class="detail-empty">暂无时间线数据</div>
      <div class="detail-sec-title">执行历史（近 7 天）</div>
      <el-table :data="executions" v-loading="detailLoading" size="small" style="width: 100%">
        <el-table-column prop="exec_date" label="日期" width="110" />
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-tag :type="row.conclusion === 'pass' ? 'success' : row.conclusion === 'fail' ? 'danger' : 'info'" size="small">
              {{ row.conclusion === "pass" ? "通过" : row.conclusion === "fail" ? "不通过" : "待录" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送" width="90">
          <template #default="{ row }">{{ pushStatusMap[row.push_status] || row.push_status }}</template>
        </el-table-column>
        <el-table-column prop="conclusion_note" label="备注" min-width="140">
          <template #default="{ row }">{{ row.conclusion_note || "-" }}</template>
        </el-table-column>
      </el-table>
    </div>
```

- [ ] **Step 4: 追加详情面板 script 逻辑与样式**

在 `plan/index.vue` 的 `script` 末尾追加 `detailPhases` 计算属性与 `pushStatusMap`：

```ts
const pushStatusMap: Record<string, string> = {
  pending: "待推送",
  running: "推送中",
  success: "成功",
  failed: "失败",
  skipped: "跳过"
};

/** 详情面板时间线（对空 push 容错） */
const detailPhases = computed(() => {
  const tl = selectedStrategy.value?.timeline;
  if (!tl) return [];
  const list = [
    { stage: "push", label: "推送", t: tl.push },
    { stage: "build", label: "构建", t: tl.build },
    { stage: "smoke", label: "冒烟", t: tl.smoke },
    { stage: "analysis", label: "分析", t: tl.analysis }
  ].filter(x => x.t);
  return list.map(x => ({
    stage: x.stage,
    label: x.label,
    text: `${formatTime(x.t.start)} ~ ${formatTime(x.t.end, "HH:mm")}`,
    color: STAGE_COLORS[x.stage]
  }));
});
```

在 `plan/index.vue` 的 `import` 中补充 `formatTime`（从 `@/utils/business`）、`computed`（若未引入）。在 `<style scoped>` 末尾追加：

```css
.detail-panel {
  margin-top: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.detail-title {
  color: #303133;
  font-weight: 600;
}
.detail-sub {
  color: #909399;
  font-size: 13px;
}
.detail-desc {
  margin-bottom: 12px;
}
.detail-sec-title {
  color: #303133;
  font-weight: 600;
  margin: 12px 0 8px;
}
.detail-timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #909399;
  font-size: 12px;
}
.dt-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dt-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}
.detail-empty {
  color: #909399;
  font-size: 12px;
  padding: 8px 0;
}
```

- [ ] **Step 5: 前端编译验证**

Run: `cd frontend; npm run build`
Expected: 构建成功，无类型/编译错误。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/plan/index.vue
git commit -m "feat(plan): 版本计划页点击色块展示详情面板并修复空数据报错"
```

---

### Task 14: 周视图页面（需求2）

**Files:**
- Create: `frontend/src/views/weekly/index.vue`
- Modify: `frontend/src/router/asyncRoutes.ts`

布局四行：① 当前周信息 + 本月周列表下拉 + 版本选择按钮；② 当前版本分支标签；③ 核心网格（列=周一~周日，各分支策略按 build_start_time 从凌晨排序，按分支配色）；④ 图例。用自研 CSS Grid 实现，数据来自 `GET /api/weekly`。

- [ ] **Step 1: 创建周视图页面**

创建 `frontend/src/views/weekly/index.vue`：

```vue
<template>
  <div class="weekly-page">
    <!-- 第一行：周信息 + 周列表 + 版本选择 -->
    <div class="row-1">
      <div class="week-info">
        今年第 <b>{{ weekNumber }}</b> 周，{{ weekRangeText }}
      </div>
      <el-select v-model="selectedWeek" placeholder="本月周列表" style="width: 200px" @change="load">
        <el-option v-for="w in monthWeeks" :key="w.value" :label="w.label" :value="w.value" />
      </el-select>
      <el-select v-model="versionId" placeholder="选择版本" clearable style="width: 160px" @change="load">
        <el-option v-for="v in versionOptions" :key="v.id" :label="v.name" :value="v.id" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="load">查询</el-button>
    </div>

    <!-- 第二行：当前版本分支列表 -->
    <div class="row-2">
      <span class="row2-label">版本分支：</span>
      <el-tag v-for="b in branches" :key="b.branch_id" size="small" class="branch-tag" :style="{ background: branchColor(b.branch_name), color: '#fff', border: 'none' }">
        {{ b.branch_name }}
      </el-tag>
      <el-empty v-if="!loading && branches.length === 0" :image-size="40" description="暂无分支" />
    </div>

    <!-- 第三行：核心网格（列=周一~周日） -->
    <div class="row-3" v-loading="loading">
      <div class="grid-head">
        <div class="grid-corner">分支 / 时间</div>
        <div v-for="d in weekDays" :key="d.date" class="grid-col-head">
          <div class="col-weekday">{{ d.label }}</div>
          <div class="col-date">{{ d.date.slice(5) }}</div>
        </div>
      </div>
      <div v-for="b in branches" :key="b.branch_id" class="grid-row">
        <div class="grid-branch">{{ b.branch_name }}</div>
        <div v-for="d in weekDays" :key="d.date" class="grid-cell">
          <div
            v-for="s in dayStrategies(b, d.date)"
            :key="s.id"
            class="strategy-chip"
            :style="{ background: branchColor(b.branch_name) }"
            @click="selectStrategy(s, b)"
          >
            <span class="chip-name">{{ s.name }}</span>
            <span class="chip-time">{{ s.build_start_time }}</span>
          </div>
        </div>
      </div>
      <el-empty v-if="!loading && branches.length === 0" description="该周暂无策略配置" />
    </div>

    <!-- 第四行：图例 -->
    <div class="row-4">
      <span class="row4-label">图例：</span>
      <span v-for="b in branches" :key="b.branch_id" class="legend-item">
        <i class="legend-dot" :style="{ background: branchColor(b.branch_name) }"></i>
        {{ b.branch_name }}
      </span>
    </div>

    <!-- 策略详情抽屉（点击网格色块） -->
    <el-drawer v-model="drawerVisible" title="策略详情" size="400px">
      <template v-if="selectedStrategy">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="策略">{{ selectedStrategy.name }}</el-descriptions-item>
          <el-descriptions-item label="分支">{{ selectedStrategy.branch_name }}</el-descriptions-item>
          <el-descriptions-item label="模板">{{ selectedStrategy.template_name }}</el-descriptions-item>
          <el-descriptions-item label="构建开始">{{ selectedStrategy.build_start_time }}</el-descriptions-item>
          <el-descriptions-item label="推送时间">{{ selectedStrategy.push_start_time || "结论后推导" }}</el-descriptions-item>
          <el-descriptions-item label="推送模式">{{ selectedStrategy.push_mode === "sync" ? "同步推送冒烟" : "正常流程推送" }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
// 周视图页面：列=周一~周日，行=指定版本各分支策略按 build_start_time 排序
// 需求2：展示策略配置排布，按分支配色；自研 CSS Grid，不依赖 ganttastic
import { ref, reactive, computed, onMounted } from "vue";
import { getWeekly } from "@/api/weekly";
import type { WeeklyData, WeeklyBranch, WeeklyStrategy } from "@/api/types";
import { dayjs } from "@/utils/business";

defineOptions({ name: "WeeklyIndex" });

const loading = ref(false);
const data = ref<WeeklyData | null>(null);
const versionId = ref<number | undefined>(undefined);
const selectedWeek = ref("");

// 版本选项：从当前周视图数据提取（亦可在切换周时保持）
const versionOptions = computed(() => {
  const v = data.value;
  return v ? [{ id: v.version_id, name: v.version_name }] : [];
});

const weekNumber = computed(() => data.value?.week_number ?? 0);
const weekDays = computed(() => data.value?.days ?? []);
const branches = computed(() => data.value?.branches ?? []);
const weekRangeText = computed(() => {
  const ws = data.value?.week_start;
  if (!ws) return "";
  const start = dayjs(ws);
  return `${start.format("MM月DD日")} - ${start.add(6, "day").format("MM月DD日")}`;
});

// 本月周列表（第1~4周，不足4周按实际）
const monthWeeks = computed(() => {
  const now = dayjs();
  const first = now.startOf("month").startOf("week").add(1, "day"); // 横向 sloppy，后修正
  const result: Array<{ value: string; label: string }> = [];
  // 以当月1号所在周为第1周，取4个周一
  const startOfMonth = now.startOf("month");
  const firstMonday = startOfMonth.day() === 0 ? startOfMonth.add(1, "day") : startOfMonth.day(1);
  for (let i = 0; i < 4; i++) {
    const monday = firstMonday.add(i * 7, "day");
    if (monday.month() !== startOfMonth.month() && i > 0) break;
    result.push({
      value: monday.format("YYYY-MM-DD"),
      label: `第${i + 1}周（${monday.format("MM.DD")} - ${monday.add(6, "day").format("MM.DD")}）`
    });
  }
  return result;
});

// 分支配色：固定色板按索引取色
const BRANCH_PALETTE = ["#3b82f6", "#8b5cf6", "#f59e0b", "#10b981", "#ef4444", "#06b6d4"];
function branchColor(name: string) {
  const idx = branches.value.findIndex(b => b.branch_name === name);
  return BRANCH_PALETTE[(idx + 1) % BRANCH_PALETTE.length];
}

/** 某分支在指定日期的策略（按 build_start_time 从凌晨排序） */
function dayStrategies(b: WeeklyBranch, date: string) {
  return b.strategies
    .filter(s => s.enabled)
    .slice()
    .sort((a, c) => a.build_start_time.localeCompare(c.build_start_time));
}

// 策略详情抽屉
const drawerVisible = ref(false);
const selectedStrategy = ref<WeeklyStrategy | null>(null);
function selectStrategy(s: WeeklyStrategy, _b: WeeklyBranch) {
  selectedStrategy.value = s;
  drawerVisible.value = true;
}

async function load() {
  loading.value = true;
  try {
    data.value = await getWeekly({
      week: selectedWeek.value || undefined,
      version_id: versionId.value
    });
    if (!selectedWeek.value && data.value) {
      selectedWeek.value = data.value.week_start;
    }
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.weekly-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.row-1 {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
}
.week-info {
  color: #303133;
  font-size: 14px;
}
.row-2 {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 16px;
}
.row2-label {
  color: #909399;
  font-size: 13px;
}
.row-3 {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.grid-head,
.grid-row {
  display: grid;
  grid-template-columns: 140px repeat(7, 1fr);
}
.grid-head {
  background: #f5f7fa;
  border-bottom: 1px solid #e5e7eb;
}
.grid-corner,
.grid-col-head {
  padding: 8px;
  text-align: center;
  color: #303133;
  font-size: 13px;
  border-right: 1px solid #e5e7eb;
}
.grid-col-head:last-child {
  border-right: none;
}
.col-weekday {
  font-weight: 600;
}
.col-date {
  color: #909399;
  font-size: 12px;
}
.grid-branch {
  padding: 8px;
  color: #303133;
  font-weight: 600;
  font-size: 13px;
  border-right: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
}
.grid-cell {
  min-height: 60px;
  padding: 6px;
  border-right: 1px solid #ebeef5;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.grid-cell:last-child {
  border-right: none;
}
.strategy-chip {
  color: #fff;
  border-radius: 4px;
  padding: 4px 6px;
  cursor: pointer;
  font-size: 12px;
  line-height: 1.4;
  transition: filter 0.2s;
}
.strategy-chip:hover {
  filter: brightness(1.1);
}
.chip-name {
  display: block;
  font-weight: 500;
}
.chip-time {
  display: block;
  opacity: 0.9;
  font-size: 11px;
}
.row-4 {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 16px;
  color: #909399;
  font-size: 12px;
}
.row4-label {
  color: #303133;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  display: inline-block;
}
.branch-tag + .branch-tag {
  margin-left: 4px;
}
</style>
```

> 说明：Step 1 中 `monthWeeks` 的 `first` 变量为冗余占位，实施时删除该行即可（不影响逻辑）。

- [ ] **Step 2: 新增路由菜单**

在 `frontend/src/router/asyncRoutes.ts` 中，在 `/plan` 路由块之后新增周视图路由（rank 与 plan 相邻，放在 plan 之后）：

```ts
  {
    path: "/weekly",
    name: "Weekly",
    component: Layout,
    redirect: "/weekly/index",
    meta: {
      icon: "ep/date",
      title: "周视图",
      rank: 2
    },
    children: [
      {
        path: "/weekly/index",
        name: "WeeklyIndex",
        component: () => import("@/views/weekly/index.vue"),
        meta: {
          title: "周视图",
          roles: ALL_ROLES
        }
      }
    ]
  },
```

> 说明：插入后请将后续 `rank`（execution/panorama/version-view/strategy/system/logs）依次 +1，避免菜单排序冲突。

- [ ] **Step 3: 前端编译验证**

Run: `cd frontend; npm run build`
Expected: 构建成功，无类型/编译错误。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/weekly/index.vue frontend/src/router/asyncRoutes.ts
git commit -m "feat(weekly): 新增周视图页面与路由菜单"
```

---

### Task 15: 系统管理策略配置 Tab（需求3）

**Files:**
- Modify: `frontend/src/views/admin/index.vue`

在系统管理页新增“策略配置”Tab，管理员可对 strategy 表完整 CRUD（不受 PM 只配置本版本限制），复用策略编辑表单（含 push_start_time），保存仍执行互斥+阶段冲突校验，删除前确认。

- [ ] **Step 1: 引入策略 API 与类型**

在 `frontend/src/views/admin/index.vue` 的 `script` 中补充导入：

```ts
import { adminApi } from "@/api/admin";
import { previewStrategy } from "@/api/strategy";
import type {
  VersionItem,
  UserInfo,
  TemplateItem,
  GlobalConfig,
  StrategyItem
} from "@/api/types";
```

- [ ] **Step 2: 新增策略管理状态与方法**

在 `frontend/src/views/admin/index.vue` 的 `script` 中追加（放在 Tab4 关键配置之后）：

```ts
// ============ Tab5 策略配置（管理员全量 CRUD） ============
const adminStrategies = ref<StrategyItem[]>([]);
const adminVersionId = ref<number | undefined>(undefined);
const adminBranchId = ref<number | undefined>(undefined);
const adminStrategyDialog = ref(false);
const adminStrategyForm = reactive({
  branch_id: 0,
  template_id: 0,
  name: "",
  build_start_time: "22:00",
  push_start_time: "" as string,
  push_mode: "normal",
  enabled: true
});
const adminEditingId = ref<number | null>(null);
const adminPreview = ref<PreviewResult | null>(null);

async function loadAdminStrategies() {
  adminStrategies.value = await adminApi.getAdminStrategies({
    version_id: adminVersionId.value,
    branch_id: adminBranchId.value
  });
}

function openAdminStrategy(s?: StrategyItem) {
  adminStrategyDialog.value = true;
  if (s) {
    adminEditingId.value = s.id;
    adminStrategyForm.branch_id = s.branch_id;
    adminStrategyForm.template_id = s.template_id;
    adminStrategyForm.name = s.name;
    adminStrategyForm.build_start_time = s.build_start_time;
    adminStrategyForm.push_start_time = s.push_start_time || "";
    adminStrategyForm.push_mode = s.push_mode;
    adminStrategyForm.enabled = s.enabled;
  } else {
    adminEditingId.value = null;
    adminStrategyForm.branch_id = 0;
    adminStrategyForm.template_id = 0;
    adminStrategyForm.name = "";
    adminStrategyForm.build_start_time = "22:00";
    adminStrategyForm.push_start_time = "";
    adminStrategyForm.push_mode = "normal";
    adminStrategyForm.enabled = true;
  }
  scheduleAdminPreview();
}

let adminPreviewTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleAdminPreview() {
  if (adminPreviewTimer) clearTimeout(adminPreviewTimer);
  adminPreviewTimer = setTimeout(runAdminPreview, 400);
}
async function runAdminPreview() {
  if (!adminStrategyForm.branch_id || !adminStrategyForm.template_id) return;
  try {
    adminPreview.value = await previewStrategy({
      branch_id: adminStrategyForm.branch_id,
      template_id: adminStrategyForm.template_id,
      name: adminStrategyForm.name,
      build_start_time: adminStrategyForm.build_start_time,
      push_start_time: adminStrategyForm.push_start_time || null,
      push_mode: adminStrategyForm.push_mode,
      enabled: adminStrategyForm.enabled
    });
  } catch {
    adminPreview.value = null;
  }
}

async function saveAdminStrategy() {
  if (adminPreview.value?.conflict) {
    ElMessageBox.alert(adminPreview.value.conflict.message || "存在时间冲突", "策略时间冲突", {
      type: "error",
      confirmButtonText: "知道了"
    });
    return;
  }
  const payload = {
    branch_id: adminStrategyForm.branch_id,
    template_id: adminStrategyForm.template_id,
    name: adminStrategyForm.name,
    build_start_time: adminStrategyForm.build_start_time,
    push_start_time: adminStrategyForm.push_start_time || null,
    push_mode: adminStrategyForm.push_mode,
    enabled: adminStrategyForm.enabled
  };
  if (adminEditingId.value) {
    await adminApi.updateAdminStrategy(adminEditingId.value, payload);
    ElMessage.success("策略已更新");
  } else {
    await adminApi.createAdminStrategy(payload);
    ElMessage.success("策略已创建");
  }
  adminStrategyDialog.value = false;
  loadAdminStrategies();
}

async function toggleAdminStrategy(s: StrategyItem) {
  await adminApi.toggleAdminStrategy(s.id, s.enabled);
  ElMessage.success(s.enabled ? "策略已启用" : "策略已停用");
  loadAdminStrategies();
}

async function deleteAdminStrategy(s: StrategyItem) {
  await ElMessageBox.confirm(
    `确认删除策略「${s.name}」？将级联清理其关联执行数据。`,
    "删除策略",
    { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" }
  );
  await adminApi.deleteAdminStrategy(s.id);
  ElMessage.success("策略已删除");
  loadAdminStrategies();
}
```

> 说明：需在 `script` 顶部补充 `import type { PreviewResult } from "@/api/strategy";`，并把 `activeTab` 默认值保持 `"versions"`。

- [ ] **Step 3: 新增模板 Tab**

在 `frontend/src/views/admin/index.vue` 模板的 `<el-tabs>` 中，`Tab4 关键配置` 之后新增 `Tab5 策略配置`：

```html
      <!-- Tab5 策略配置（管理员全量） -->
      <el-tab-pane label="策略配置" name="strategies">
        <div class="toolbar">
          <el-select v-model="adminVersionId" placeholder="全部版本" clearable style="width: 160px" @change="onAdminVersionChange">
            <el-option v-for="v in versions" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
          <el-select v-model="adminBranchId" placeholder="全部分支" clearable style="width: 160px" @change="loadAdminStrategies">
            <el-option v-for="b in adminBranchOptions" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
          <el-button type="primary" size="small" @click="loadAdminStrategies">查询</el-button>
          <el-button type="primary" size="small" @click="openAdminStrategy()">新建策略</el-button>
        </div>
        <el-table :data="adminStrategies" v-loading="loading" style="width: 100%">
          <el-table-column prop="name" label="策略名称" min-width="180" />
          <el-table-column prop="version_name" label="版本" width="90" />
          <el-table-column prop="branch_name" label="分支" width="100" />
          <el-table-column prop="template_name" label="模板" width="120" />
          <el-table-column prop="build_start_time" label="构建开始" width="100" />
          <el-table-column label="推送" width="110">
            <template #default="{ row }">{{ row.push_start_time || "结论后推导" }}</template>
          </el-table-column>
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" @change="toggleAdminStrategy(row)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openAdminStrategy(row)">编辑</el-button>
              <el-button type="danger" link size="small" @click="deleteAdminStrategy(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
```

- [ ] **Step 4: 新增分支选项计算与策略编辑弹窗**

在 `script` 中追加 `adminBranchOptions` 计算属性与 `onAdminVersionChange`：

```ts
const adminBranchOptions = computed(() => {
  if (!adminVersionId.value) return [];
  const v = versions.value.find(x => x.id === adminVersionId.value);
  return (v?.branches || []).map(b => ({ id: b.id, name: b.name }));
});
function onAdminVersionChange() {
  adminBranchId.value = undefined;
  loadAdminStrategies();
}
```

在模板 `</el-tabs>` 之后、`</div>` 之前追加策略编辑弹窗（含 push_start_time 时间选择器）：

```html
    <!-- 策略编辑弹窗（管理员） -->
    <el-dialog v-model="adminStrategyDialog" :title="adminEditingId ? '编辑策略' : '新建策略'" width="480px">
      <el-form :model="adminStrategyForm" label-width="110px">
        <el-form-item label="策略分支">
          <el-select v-model="adminStrategyForm.branch_id" style="width: 100%" @change="scheduleAdminPreview">
            <el-option v-for="b in adminBranchOptions" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略模板">
          <el-select v-model="adminStrategyForm.template_id" style="width: 100%" @change="scheduleAdminPreview">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略名称">
          <el-input v-model="adminStrategyForm.name" placeholder="策略名称" />
        </el-form-item>
        <el-form-item label="构建开始时间">
          <el-time-picker v-model="adminStrategyForm.build_start_time" value-format="HH:mm" format="HH:mm" style="width: 160px" @change="scheduleAdminPreview" />
        </el-form-item>
        <el-form-item label="推送时间（可空）">
          <el-time-picker v-model="adminStrategyForm.push_start_time" value-format="HH:mm" format="HH:mm" placeholder="留空=结论后推导" clearable style="width: 160px" @change="scheduleAdminPreview" />
        </el-form-item>
        <el-form-item label="推送模式">
          <el-radio-group v-model="adminStrategyForm.push_mode" @change="scheduleAdminPreview">
            <el-radio value="normal">正常流程推送</el-radio>
            <el-radio value="sync">同步推送冒烟</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="adminStrategyForm.enabled" />
        </el-form-item>
        <el-form-item v-if="adminPreview?.conflict" label="冲突">
          <span class="preview-conflict">{{ adminPreview.conflict.message || "存在时间冲突" }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adminStrategyDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!!adminPreview?.conflict" @click="saveAdminStrategy">保存</el-button>
      </template>
    </el-dialog>
```

在 `<style scoped>` 追加：

```css
.preview-conflict {
  color: #ef4444;
  font-size: 13px;
}
```

- [ ] **Step 5: onMounted 加载时同时加载策略**

在 `frontend/src/views/admin/index.vue` 的 `onMounted` 中追加 `loadAdminStrategies()`：

```ts
onMounted(async () => {
  await Promise.all([loadVersions(), loadUsers(), loadTemplates(), loadConfig(), loadAdminStrategies()]);
});
```

- [ ] **Step 6: 前端编译验证**

Run: `cd frontend; npm run build`
Expected: 构建成功，无类型/编译错误。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/admin/index.vue
git commit -m "feat(admin): 系统管理新增策略配置 Tab，管理员全量 CRUD"
```

---

### Task 16: 策略表单 push_start_time + 甘特图优化（需求4）

**Files:**
- Modify: `frontend/src/views/strategy/index.vue`
- Modify: `frontend/src/components/gantt/GanttGanttastic.vue`

需求4：推送时间可在任意时间节点设置，与其他策略重叠不标红；甘特图始终展示推送色块（有值固定区间，空值推导/隐藏）。

- [ ] **Step 1: 策略表单增加 push_start_time 字段**

在 `frontend/src/views/strategy/index.vue` 的 `script` 中，将 `form` 的 reactive 初始化增加 `push_start_time`：

```ts
const form = reactive<StrategyForm>({
  branch_id: 0,
  template_id: 0,
  name: "",
  build_start_time: "22:00",
  push_start_time: "" as string,
  push_mode: "normal",
  enabled: true
});
```

在 `startEdit` 中补充 `form.push_start_time = s.push_start_time || "";`，在 `startNew` 中补充 `form.push_start_time = "";`。

在模板 `推送模式` 表单项之后追加（紧邻启用开关之前）：

```html
        <el-form-item label="推送时间（可空）">
          <el-time-picker
            v-model="form.push_start_time"
            value-format="HH:mm"
            format="HH:mm"
            placeholder="留空=结论后推导"
            clearable
            style="width: 160px"
            @change="schedulePreview"
          />
          <span class="form-tip">（设置后固定在该时间推送，可与其它策略重叠）</span>
        </el-form-item>
```

- [ ] **Step 2: 预览请求携带 push_start_time**

在 `frontend/src/views/strategy/index.vue` 的 `runPreview` 中，请求体补充 `push_start_time`：

```ts
    preview.value = await previewStrategy({
      ...form,
      build_start_time: form.build_start_time,
      push_start_time: form.push_start_time || null
    });
```

在 `onSave` 的 `createStrategy`/`updateStrategy` 调用前，将 `{ ...form }` 中 `push_start_time` 空串归一为 null：

```ts
  const payload = {
    ...form,
    push_start_time: form.push_start_time || null
  };
  if (isEditing.value) {
    await updateStrategy(editingId.value as number, { ...payload });
  } else {
    await createStrategy({ ...payload });
  }
```

- [ ] **Step 3: 甘特图推送色块始终展示且不因重叠标红**

在 `frontend/src/views/plan/index.vue` 的 `buildRows` 中，推送色块逻辑已存在（`if (tl.push)`）。确认推送色块的 `conflict` 仅用于“构建阶段互斥”，推送阶段不继承冲突标记。将推送色块构建改为：

```ts
          if (tl.push) {
            phases.push({
              key: `${s.id}-push`,
              stage: "push",
              start: tl.push.start,
              end: tl.push.end,
              conflict: false, // 推送可重叠，不标红
              versionName: v.version_name,
              strategyName: s.name
            });
          }
```

> 若后端 `tl.push` 在 normal 模式无结论时返回 null，则推送色块在无数据日不展示（符合规格“空值只在有结论时出现”）；有固定 push_start_time 时后端始终返回区间。

- [ ] **Step 4: 前端编译验证**

Run: `cd frontend; npm run build`
Expected: 构建成功，无类型/编译错误。

- [ ] **Step 5: 联调冒烟**

Run: 启动后端 `cd backend; python manage.py runserver 8000` 与前端 `cd frontend; npm run dev`
Expected: 登录 → 版本计划页点击色块出详情 → 周视图显示四行排布 → 系统管理策略配置可增删改 → 策略表单可配推送时间 → 甘特图推送色块正常展示。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/strategy/index.vue frontend/src/views/plan/index.vue frontend/src/components/gantt/GanttGanttastic.vue
git commit -m "feat(strategy): 推送时间任意化与甘特图推送色块优化"
```
```