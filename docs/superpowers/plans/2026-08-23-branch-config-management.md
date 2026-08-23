# 分支配置管理模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Django + Vue3 系统中新增「分支配置」单页管理模块：分支/工程关联、启动参数、分支级授权（VIEWER/OPERATOR/ADMIN）、实例状态模拟启停（5 秒轮询）。

**Architecture:** 后端复用现有 `Branch` 表并扩展字段，新增 Project/BranchProject/StartupConfig/BranchPermission/Instance 五张表；视图层 DRF ViewSet + @action（与 reports 模块同范式），聚合配置由服务层手工组装；前端新增一级菜单单页（左列表右详情，三 Tab），API 封装在 `src/api/branchConfig.ts`，实例状态组件内 setInterval 5s 轮询。

**Tech Stack:** Django 5 + DRF + SQLite / Vue 3 + Element Plus + pure-admin-thin / 统一响应契约 `{code, message, data}`。

---

## 0. 执行者必读上下文

**项目结构**：
- 后端 app `backend/build_protection_service/`：模型按领域拆分 `models/others.py`（User/Version/Branch 等）与 `models/report.py`；本模块新增 `models/branch_config.py`。
- 后端测试：Django TestCase 风格（见 `tests.py`），运行命令（在 `backend/` 下）`python manage.py test build_protection_service -v 2`；测试文件 `tests_branch_config.py`。
- 前端：Vue3 + TypeScript，API 封装在 `src/api/*.ts` 并以 `src/api/http.ts`（Axios 拦截器）为基座；页面在 `src/views/`，业务路由静态注册于 `src/router/asyncRoutes.ts`。

**与本任务相关的事实**：
- `views/__init__.py` 提供 `authed_user(request) -> (user, error_resp)`、`json_resp(payload, status=200)`（`ensure_ascii=False`）。
- `api.py` 提供 `ok(data=None, message="ok")`、`err(code, message)`。
- DRF 全局 `IsAuthenticated` 只放行；每个 ViewSet 均需 `permission_classes = [AllowAny]` 并手动 `authed_user` 校验（见 `views/reports.py` 注释原因：未认证时 DRF 返回无 code 的 401，破坏契约）。
- 错误码：40100 未认证、40301 无权限、40401 不存在、42201 参数非法、40902 实体重名（前端 ElMessage 提示）、新增 40903 重复关联/重复授权/重复启动（前端落入 else 分支 ElMessage 提示）。
- 前端 `http.ts` 对 40901 有「策略时间冲突」专用弹框，因此**分支/工程重名一律用 40902**，不使用 40901。
- 时间字段序列化格式统一 `"%Y-%m-%dT%H:%M:%S"`。
- 新建分支对话框的版本下拉复用 `getPlan()`（`src/api/plan.ts`，所有角色可访问），取 `version_id/version_name`。
- 提交信息用简体中文；模型字段中文 verbose_name；注释简体中文。

**文件结构映射**：

| 文件 | 职责 | 操作 |
|---|---|---|
| `backend/.../models/others.py` | Branch 扩展 `repository_url`/`description` | 修改 |
| `backend/.../models/branch_config.py` | Project/BranchProject/StartupConfig/BranchPermission/Instance | 新建 |
| `backend/.../models/__init__.py` | 统一导出新模型 | 修改 |
| `backend/.../services/branch_config.py` | 角色解析、实例状态机、聚合组装 | 新建 |
| `backend/.../serializers/branch_config.py` | StartupConfig 写入序列化器 | 新建 |
| `backend/.../views/branch_config.py` | 三个 ViewSet + users_all/projects_view 函数视图 | 新建 |
| `backend/.../views/urls.py` | 注册 15 条路由 | 修改 |
| `backend/.../tests_branch_config.py` | 模型/服务/API 三组测试 | 新建 |
| `frontend/src/api/branchConfig.ts` | 全部接口封装 + TS 类型 | 新建 |
| `frontend/src/router/asyncRoutes.ts` | 一级菜单「分支配置」rank 10 | 修改 |
| `frontend/src/views/branch-config/index.vue` | 单页骨架：左列表 + 权限面板 + Tab 容器 + 轮询 | 新建 |
| `frontend/src/views/branch-config/components/ProjectsPanel.vue` | Tab① 工程关联表格 | 新建 |
| `frontend/src/views/branch-config/components/StartupConfigForm.vue` | Tab② 启动参数表单 | 新建 |
| `frontend/src/views/branch-config/components/InstancesPanel.vue` | Tab③ 运行状态 + 启停按钮 | 新建 |

---

## Task 1: 后端模型层（Branch 扩展 + 五张新表 + 迁移）

**Files:**
- Modify: `backend/build_protection_service/models/others.py`
- Create: `backend/build_protection_service/models/branch_config.py`
- Modify: `backend/build_protection_service/models/__init__.py`

- [ ] **Step 1: 扩展 Branch 模型**

在 `models/others.py` 的 `Branch` 类 `name` 字段后追加两字段：

```python
    name = models.CharField("分支名", max_length=100)
    repository_url = models.CharField("仓库地址", max_length=255, blank=True, default="")
    description = models.TextField("描述", blank=True, default="")
```

- [ ] **Step 2: 创建 models/branch_config.py**

```python
"""分支配置领域模型：工程库 / 分支-工程关联 / 启动配置 / 分支授权 / 运行实例。"""
from django.db import models


class Project(models.Model):
    """工程库：独立实体，分支通过 BranchProject 关联。"""

    name = models.CharField("工程名", max_length=100, unique=True)
    repository_url = models.CharField("仓库地址", max_length=255, blank=True, default="")
    description = models.TextField("描述", blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "工程"
        verbose_name_plural = "工程"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class BranchProject(models.Model):
    """分支↔工程关联：唯一约束 + 启用标记。"""

    branch = models.ForeignKey(
        "Branch", on_delete=models.CASCADE, related_name="branch_projects"
    )
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="branch_projects"
    )
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "分支工程关联"
        verbose_name_plural = "分支工程关联"
        unique_together = ("branch", "project")
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.branch}/{self.project}"


class StartupConfig(models.Model):
    """启动配置：每条分支工程关联一份（OneToOne）。"""

    branch_project = models.OneToOneField(
        BranchProject, on_delete=models.CASCADE, related_name="startup_config"
    )
    command = models.CharField("启动命令", max_length=255, blank=True, default="")
    args = models.JSONField("参数", default=list, blank=True)
    env_vars = models.JSONField("环境变量", default=dict, blank=True)
    working_directory = models.CharField("工作目录", max_length=255, blank=True, default="")
    timeout_seconds = models.PositiveIntegerField("启动超时(秒)", default=60)
    auto_restart = models.BooleanField("自动重启", default=False)
    raw_json = models.TextField("原始配置JSON", blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "启动配置"
        verbose_name_plural = "启动配置"

    def __str__(self) -> str:
        return f"config#{self.branch_project_id}"


class BranchPermission(models.Model):
    """分支级授权：VIEWER/OPERATOR/ADMIN，分支+用户唯一。"""

    ROLE_CHOICES = (
        ("VIEWER", "查看者"),
        ("OPERATOR", "操作者"),
        ("ADMIN", "管理员"),
    )

    branch = models.ForeignKey(
        Branch if False else "Branch",  # noqa: F821 占位防误用，见下
        on_delete=models.CASCADE, related_name="permissions"
    )
    user = models.ForeignKey(
        "User", on_delete=models.CASCADE, related_name="branch_permissions"
    )
    role = models.CharField("角色", max_length=10, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "分支授权"
        verbose_name_plural = "分支授权"
        unique_together = ("branch", "user")

    def __str__(self) -> str:
        return f"{self.branch}/{self.user}/{self.role}"


class Instance(models.Model):
    """运行实例：纯状态机模拟（STARTING/RUNNING/STOPPED/ERROR）。"""

    STATUS_CHOICES = (
        ("STARTING", "启动中"),
        ("RUNNING", "运行中"),
        ("STOPPED", "已停止"),
        ("ERROR", "异常"),
    )

    branch_project = models.ForeignKey(
        BranchProject, on_delete=models.CASCADE, related_name="instances"
    )
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default="STOPPED")
    pid = models.IntegerField("进程号", null=True, blank=True)
    started_at = models.DateTimeField("启动时间", null=True, blank=True)
    stopped_at = models.DateTimeField("停止时间", null=True, blank=True)
    last_heartbeat_at = models.DateTimeField("最近心跳", null=True, blank=True)
    exit_code = models.IntegerField("退出码", null=True, blank=True)
    log_tail = models.TextField("日志尾部", blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "运行实例"
        verbose_name_plural = "运行实例"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"instance#{self.id}-{self.status}"
```

注意：`BranchPermission.branch` 外键目标字符串写 `"Branch"` 即可（非注释里那段），上方代码中的占位写法仅为提示——**实际代码请直接使用**：

```python
    branch = models.ForeignKey(
        "Branch", on_delete=models.CASCADE, related_name="permissions"
    )
```

（Django 模型若与外键目标同文件则可省略引号；跨文件引用必须用字符串类名。）

- [ ] **Step 3: models/__init__.py 统一导出**

修改 `models/__init__.py`：

```python
from .branch_config import (
    BranchPermission,
    BranchProject,
    Instance,
    Project,
    StartupConfig,
)
```

并在 `__all__` 尾部追加 `"BranchPermission", "BranchProject", "Instance", "Project", "StartupConfig",`。

- [ ] **Step 4: 生成并执行迁移**

在 `backend/` 目录运行：

```bash
python manage.py makemigrations build_protection_service
python manage.py migrate
```

Expected: 生成 `migrations/0006_*.py`（Branch 加两字段 + 五表），migrate 输出 `OK`。

- [ ] **Step 5: 回归既有测试**

```bash
python manage.py test build_protection_service -v 1
```

Expected: 全部 PASS（现有 776 行测试不受影响）。

- [ ] **Step 6: Commit**

```bash
git add backend/build_protection_service/models
git commit -m "feat: 分支配置新增工程/授权/启动配置/实例数据模型"
```

---

## Task 2: 模型约束测试

**Files:**
- Create: `backend/build_protection_service/tests_branch_config.py`

- [ ] **Step 1: 创建测试文件（模型约束 + 共享夹具）**

```python
"""分支配置模块测试：模型约束 / 服务 / API 三层。"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    Branch,
    BranchPermission,
    BranchProject,
    Instance,
    Project,
    StartupConfig,
    Version,
)

User = get_user_model()


def _auth(client, user):
    """登录并携带 token，失败会抛异常暴露契约问题。"""
    resp = client.post(
        "/api/auth/login", {"username": user.username, "password": "123456"}, format="json"
    )
    token = resp.json()["data"]["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


class BranchConfigFixture(TestCase):
    """共享夹具：admin/pm/builder 用户 + 版本/分支/工程/关联/启动配置。"""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin1", password="123456", role="admin"
        )
        self.pm = User.objects.create_user(
            username="pm1", password="123456", role="pm"
        )
        self.builder = User.objects.create_user(
            username="bob", password="123456", role="builder"
        )
        self.viewer = User.objects.create_user(
            username="viewer", password="123456", role="tester"
        )
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(
            version=self.version,
            name="master",
            repository_url="https://git.local/27A.git",
            description="主干分支",
        )
        self.project = Project.objects.create(name="GatewayEngine")
        self.bp = BranchProject.objects.create(branch=self.branch, project=self.project)
        self.config = StartupConfig.objects.create(
            branch_project=self.bp,
            command="python manage.py runserver",
            args=["0.0.0.0:8000"],
            env_vars={"PORT": "8000"},
            timeout_seconds=60,
            auto_restart=False,
        )
        self.client = APIClient()


class BranchConfigModelTests(BranchConfigFixture):
    def test_branch_extension_fields(self):
        self.assertEqual(self.branch.repository_url, "https://git.local/27A.git")
        self.assertEqual(self.branch.description, "主干分支")

    def test_branch_project_unique(self):
        with self.assertRaises(IntegrityError):
            BranchProject.objects.create(branch=self.branch, project=self.project)

    def test_branch_permission_unique(self):
        BranchPermission.objects.create(
            branch=self.branch, user=self.builder, role="OPERATOR"
        )
        with self.assertRaises(IntegrityError):
            BranchPermission.objects.create(
                branch=self.branch, user=self.builder, role="ADMIN"
            )

    def test_project_name_unique(self):
        with self.assertRaises(IntegrityError):
            Project.objects.create(name="GatewayEngine")

    def test_branch_delete_cascade(self):
        Instance.objects.create(branch_project=self.bp, status="RUNNING", pid=32001)
        BranchPermission.objects.create(
            branch=self.branch, user=self.builder, role="OPERATOR"
        )
        self.branch.delete()
        self.assertEqual(BranchProject.objects.count(), 0)
        self.assertEqual(StartupConfig.objects.count(), 0)
        self.assertEqual(Instance.objects.count(), 0)
        self.assertEqual(BranchPermission.objects.count(), 0)
        self.assertEqual(Project.objects.count(), 1)  # 工程库不受影响
```

- [ ] **Step 2: 运行测试**

```bash
python manage.py test build_protection_service.tests_branch_config -v 2
```

Expected: 5 个用例全部 PASS。

- [ ] **Step 3: Commit**

```bash
git add backend/build_protection_service/tests_branch_config.py
git commit -m "test: 分支配置模型唯一约束与级联删除测试"
```

---

## Task 3: 服务层（角色解析 / 实例状态机 / 聚合组装）

**Files:**
- Create: `backend/build_protection_service/services/branch_config.py`
- Modify: `backend/build_protection_service/tests_branch_config.py`

- [ ] **Step 1: 写服务层测试（追加到 tests_branch_config.py）**

在文件末尾追加：

```python
from .services.branch_config import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    advance,
    build_branch_config,
    latest_instance,
    resolve_role,
    start_instance,
    stop_instance,
)


class BranchConfigServiceTests(BranchConfigFixture):
    def test_resolve_role_admin_is_admin(self):
        self.assertEqual(resolve_role(self.branch, self.admin), ROLE_ADMIN)

    def test_resolve_role_unauthorized_defaults_viewer(self):
        # 未授权记录的用户默认只读
        self.assertEqual(resolve_role(self.branch, self.builder), ROLE_VIEWER)

    def test_resolve_role_from_permission(self):
        BranchPermission.objects.create(
            branch=self.branch, user=self.builder, role="OPERATOR"
        )
        self.assertEqual(resolve_role(self.branch, self.builder), ROLE_OPERATOR)

    def test_start_creates_starting_instance(self):
        inst = start_instance(self.bp, "bob")
        self.assertIsNotNone(inst)
        self.assertEqual(inst.status, "STARTING")
        self.assertIsNotNone(inst.pid)
        self.assertGreaterEqual(inst.pid, 32000)
        self.assertLessEqual(inst.pid, 49999)

    def test_start_duplicate_returns_none(self):
        start_instance(self.bp, "bob")
        self.assertIsNone(start_instance(self.bp, "bob"))

    def test_advance_promotes_starting_to_running_after_threshold(self):
        inst = start_instance(self.bp, "bob")
        inst.started_at = timezone.now() - timedelta(seconds=5)
        inst.save(update_fields=["started_at"])
        advance(inst)
        inst.refresh_from_db()
        self.assertEqual(inst.status, "RUNNING")
        self.assertIsNotNone(inst.last_heartbeat_at)

    def test_advance_keeps_starting_before_threshold(self):
        inst = start_instance(self.bp, "bob")
        advance(inst)  # 刚启动，未到 2s 阈值
        inst.refresh_from_db()
        self.assertEqual(inst.status, "STARTING")

    def test_stop_transitions_to_stopped(self):
        inst = start_instance(self.bp, "bob")
        got = stop_instance(self.bp, "alice")
        self.assertIsNotNone(got)
        got.refresh_from_db()
        self.assertEqual(got.status, "STOPPED")
        self.assertIsNotNone(got.stopped_at)
        self.assertEqual(got.exit_code, 0)

    def test_stop_without_instance_is_idempotent(self):
        self.assertIsNone(stop_instance(self.bp, "alice"))

    def test_latest_instance_orders_by_id_desc(self):
        old = Instance.objects.create(
            branch_project=self.bp, status="STOPPED", pid=32000
        )
        new = Instance.objects.create(
            branch_project=self.bp, status="RUNNING", pid=32001
        )
        self.assertEqual(latest_instance(self.bp).id, new.id)
        self.assertNotEqual(latest_instance(self.bp).id, old.id)

    def test_build_config_respects_my_role_and_sections(self):
        BranchPermission.objects.create(
            branch=self.branch, user=self.builder, role="ADMIN"
        )
        data = build_branch_config(self.branch, self.builder)
        self.assertEqual(data["my_role"], ROLE_ADMIN)
        self.assertEqual(data["branch"]["version_name"], "27A")
        self.assertEqual(len(data["branch_projects"]), 1)
        bp = data["branch_projects"][0]
        self.assertEqual(bp["project"]["name"], "GatewayEngine")
        self.assertEqual(bp["startup_config"]["command"], "python manage.py runserver")
        self.assertIn("permissions", data)
        self.assertIn("available_users", data)
        self.assertIn("available_projects", data)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test build_protection_service.tests_branch_config.BranchConfigServiceTests -v 2
```

Expected: FAIL（`ModuleNotFoundError: No module named ...services.branch_config`）。

- [ ] **Step 3: 实现 services/branch_config.py**

```python
"""分支配置服务：角色解析、实例状态机模拟、聚合配置组装。

纯模拟约定：
- start 创建 STARTING 实例（随机 pid 32000-49999）；
- STARTING 距 started_at 超过 START_READY_SECONDS 秒后，在下一次读取时被推进为 RUNNING；
- stop 仅对 STARTING/RUNNING 生效，置 STOPPED 并记录 stopped_at/exit_code=0；
- ERROR 状态本期仅保留枚举，不做自动判定。
"""
import json
import logging
import random
from typing import Dict, List, Optional, Sequence

from django.contrib.auth import get_user_model
from django.utils import timezone

from ..models import Branch, BranchPermission, BranchProject, Instance, Project, StartupConfig

logger = logging.getLogger("build_protection_service")

User = get_user_model()

ROLE_VIEWER = "VIEWER"
ROLE_OPERATOR = "OPERATOR"
ROLE_ADMIN = "ADMIN"
ROLE_VALID = (ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN)

START_READY_SECONDS = 2
_FMT = "%Y-%m-%dT%H:%M:%S"


# ---------- 角色解析 ----------

def resolve_role(branch: Branch, user) -> str:
    """计算用户对分支的有效角色：系统 admin 恒为 ADMIN，无授权默认 VIEWER。"""
    if getattr(user, "role", "") == "admin":
        return ROLE_ADMIN
    perm = BranchPermission.objects.filter(branch=branch, user=user).first()
    return perm.role if perm else ROLE_VIEWER


# ---------- 实例状态机 ----------

def advance(instance: Instance) -> None:
    """按时间推进：STARTING 超阈值 → RUNNING；RUNNING 刷新心跳。"""
    now = timezone.now()
    if instance.status == "STARTING" and instance.started_at:
        if (now - instance.started_at).total_seconds() > START_READY_SECONDS:
            instance.status = "RUNNING"
            instance.last_heartbeat_at = now
            instance.save(update_fields=["status", "last_heartbeat_at", "updated_at"])
            return
    if instance.status == "RUNNING":
        instance.last_heartbeat_at = now
        instance.save(update_fields=["last_heartbeat_at", "updated_at"])


def start_instance(branch_project: BranchProject, actor: str) -> Optional[Instance]:
    """启动模拟：存在运行中实例返回 None（由视图层转 40903），否则创建 STARTING。"""
    running = Instance.objects.filter(
        branch_project=branch_project, status__in=("STARTING", "RUNNING")
    ).exists()
    if running:
        return None
    now = timezone.now()
    pid = random.randint(32000, 49999)
    inst = Instance.objects.create(
        branch_project=branch_project,
        status="STARTING",
        pid=pid,
        started_at=now,
        last_heartbeat_at=now,
        log_tail=f"[{actor}] 发起启动 pid={pid}",
    )
    logger.info(
        "[branch-instance][simulate] start bp=%s pid=%s actor=%s",
        branch_project.id, pid, actor,
    )
    return inst


def stop_instance(branch_project: BranchProject, actor: str) -> Optional[Instance]:
    """停止模拟：仅 STARTING/RUNNING 生效；无实例或已停止幂等返回当前实例。"""
    inst = Instance.objects.filter(branch_project=branch_project).order_by("-id").first()
    if inst is None or inst.status not in ("STARTING", "RUNNING"):
        return inst
    now = timezone.now()
    inst.status = "STOPPED"
    inst.stopped_at = now
    inst.exit_code = 0
    inst.log_tail = (inst.log_tail + f"\n[{actor}] 发起停止").strip()
    inst.save(update_fields=["status", "stopped_at", "exit_code", "log_tail", "updated_at"])
    logger.info(
        "[branch-instance][simulate] stop bp=%s pid=%s actor=%s",
        branch_project.id, inst.pid, actor,
    )
    return inst


def latest_instance(branch_project: BranchProject) -> Optional[Instance]:
    """取每个关联的最新实例（按 id 倒序第一个）。"""
    return Instance.objects.filter(branch_project=branch_project).order_by("-id").first()


# ---------- 序列化辅助 ----------

def _dt(value) -> Optional[str]:
    return value.strftime(_FMT) if value else None


def serialize_instance(inst: Instance) -> Dict:
    return {
        "id": inst.id,
        "status": inst.status,
        "pid": inst.pid,
        "started_at": _dt(inst.started_at),
        "stopped_at": _dt(inst.stopped_at),
        "last_heartbeat_at": _dt(inst.last_heartbeat_at),
        "exit_code": inst.exit_code,
        "log_tail": inst.log_tail,
    }


def serialize_config(conf: StartupConfig) -> Dict:
    return {
        "command": conf.command,
        "args": conf.args,
        "env_vars": conf.env_vars,
        "working_directory": conf.working_directory,
        "timeout_seconds": conf.timeout_seconds,
        "auto_restart": conf.auto_restart,
        "raw_json": conf.raw_json,
        "updated_at": _dt(conf.updated_at),
    }


def serialize_branch(branch: Branch) -> Dict:
    return {
        "id": branch.id,
        "version_id": branch.version_id,
        "version_name": branch.version.name,
        "name": branch.name,
        "repository_url": branch.repository_url,
        "description": branch.description,
    }


def serialize_project(project: Project) -> Dict:
    return {
        "id": project.id,
        "name": project.name,
        "repository_url": project.repository_url,
        "description": project.description,
    }


# ---------- 聚合配置 ----------

def build_branch_config(branch: Branch, user) -> Dict:
    """组装聚合配置：分支 + 工程关联（含启动配置与最新实例）+ 授权 + 可用用户/工程。"""
    items: List[Dict] = []
    for bp in branch.branch_projects.select_related("project").all():
        adv = latest_instance(bp)
        if adv:
            advance(adv)
        conf = getattr(bp, "startup_config", None)
        items.append(
            {
                "id": bp.id,
                "enabled": bp.enabled,
                "project": serialize_project(bp.project),
                "startup_config": serialize_config(conf) if conf else None,
                "latest_instance": serialize_instance(adv) if adv else None,
            }
        )
    perms = BranchPermission.objects.filter(branch=branch).select_related("user").order_by("id")
    return {
        "branch": serialize_branch(branch),
        "branch_projects": items,
        "permissions": [
            {"id": p.id, "user_id": p.user_id, "username": p.user.username, "role": p.role}
            for p in perms
        ],
        "my_role": resolve_role(branch, user),
        "available_users": [
            {"id": u.id, "username": u.username, "role": u.role}
            for u in User.objects.filter(is_active=True).order_by("id")
        ],
        "available_projects": [
            {"id": p.id, "name": p.name} for p in Project.objects.all().order_by("id")
        ],
    }


def dump_raw_config(instance: Instance) -> str:
    """生成 raw_json 原始配置 JSON（供序列化器写入）。"""
    return json.dumps(
        {
            "command": instance.command,
            "args": instance.args,
            "env_vars": instance.env_vars,
            "working_directory": instance.working_directory,
            "timeout_seconds": instance.timeout_seconds,
            "auto_restart": instance.auto_restart,
        },
        ensure_ascii=False,
    )
```

（`Sequence` 导入若无使用可移除；保持导入与实际用法一致。）

- [ ] **Step 4: 运行测试**

```bash
python manage.py test build_protection_service.tests_branch_config.BranchConfigServiceTests -v 2
```

Expected: 12 个用例全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/build_protection_service/services backend/build_protection_service/tests_branch_config.py
git commit -m "feat: 分支配置服务层（角色解析/实例状态机/聚合组装）"
```

---

## Task 4: 启动配置序列化器

**Files:**
- Create: `backend/build_protection_service/serializers/branch_config.py`

- [ ] **Step 1: 创建序列化器**

```python
"""启动配置序列化器：分支工程关联的启动参数写入（env_vars 值统一转字符串）。"""
import json

from rest_framework import serializers

from ..models import StartupConfig
from ..services.branch_config import dump_raw_config


class StartupConfigSerializer(serializers.ModelSerializer):
    """启动参数写入：字段可选（partial 更新），原始配置 JSON 只读回显。"""

    command = serializers.CharField(allow_blank=True, required=False, max_length=255)
    args = serializers.ListField(
        child=serializers.CharField(allow_blank=True), required=False
    )
    env_vars = serializers.DictField(
        child=serializers.JSONField(), required=False
    )
    working_directory = serializers.CharField(allow_blank=True, required=False, max_length=255)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=3600, required=False)
    auto_restart = serializers.BooleanField(required=False)
    raw_json = serializers.CharField(read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%dT%H:%M:%S", read_only=True)

    class Meta:
        model = StartupConfig
        fields = [
            "command",
            "args",
            "env_vars",
            "working_directory",
            "timeout_seconds",
            "auto_restart",
            "raw_json",
            "updated_at",
        ]

    def validate_env_vars(self, value: dict) -> dict:
        """环境变量值统一转字符串（兼容数字/布尔）。"""
        return {str(k): str(v) for k, v in (value or {}).items()}

    def update(self, instance: StartupConfig, validated_data: dict) -> StartupConfig:
        instance.command = validated_data.get("command", instance.command)
        instance.args = list(validated_data.get("args", instance.args or []))
        instance.env_vars = dict(validated_data.get("env_vars", instance.env_vars or {}))
        instance.working_directory = validated_data.get(
            "working_directory", instance.working_directory
        )
        instance.timeout_seconds = validated_data.get(
            "timeout_seconds", instance.timeout_seconds
        )
        instance.auto_restart = validated_data.get(
            "auto_restart", instance.auto_restart
        )
        instance.raw_json = dump_raw_config(instance)
        instance.save()
        return instance
```

- [ ] **Step 2: 验证导入与快速冒烟**

```bash
python -c "from build_protection_service.serializers.branch_config import StartupConfigSerializer; print('ok')"
```

Expected: 输出 `ok`。

- [ ] **Step 3: Commit**

```bash
git add backend/build_protection_service/serializers
git commit -m "feat: 启动配置序列化器（env_vars 归一化与 raw_json 回显）"
```

---

## Task 5: 视图层（三个 ViewSet + 两个函数视图）

**Files:**
- Create: `backend/build_protection_service/views/branch_config.py`

- [ ] **Step 1: 创建视图文件**

```python
"""分支配置视图：分支/工程关联/授权/实例（DRF ViewSet + action，聚合服务层组装）。

认证与错误码约定同 reports 模块：ViewSet 置 AllowAny，authed_user 手动校验；
统一响应 {code, message, data}；重名用 40902，重复关联/授权/启动用 40903。
"""
import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from ..api import err, ok
from ..models import (
    Branch,
    BranchPermission,
    BranchProject,
    Project,
    StartupConfig,
    Version,
)
from ..serializers.branch_config import StartupConfigSerializer
from ..services.branch_config import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VALID,
    advance,
    build_branch_config,
    latest_instance,
    resolve_role,
    serialize_branch,
    serialize_config,
    serialize_instance,
    serialize_project,
    start_instance as svc_start,
    stop_instance as svc_stop,
)
from . import authed_user, json_resp, parse_body

logger = logging.getLogger("build_protection_service")

User = get_user_model()


def _first_error(errors: dict) -> str:
    """取 serializer 错误第一条消息用于统一提示。"""
    for value in errors.values():
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str) and value:
            return value
    return "参数校验失败"


def _branch_or_none(pk) -> Branch:
    return Branch.objects.select_related("version").filter(pk=pk).first()


def _bp_or_none(pk) -> BranchProject:
    return BranchProject.objects.select_related("project", "branch__version").filter(pk=pk).first()


def _branch_required(branch):
    """分支不存在返回 (None, 404 响应)。"""
    if branch is None:
        return None, json_resp(err(40401, "分支不存在"), status=404)
    return branch, None


def _bp_required(bp):
    if bp is None:
        return None, json_resp(err(40401, "工程关联不存在"), status=404)
    return bp, None


def _require_role(user, branch, *roles):
    """角色门槛：有效角色不在 roles 内则返回 40301 响应。"""
    if resolve_role(branch, user) not in roles:
        return json_resp(err(40301, "无权限执行该操作"), status=403)
    return None


def _serialize_perm(perm) -> dict:
    return {
        "id": perm.id,
        "user_id": perm.user_id,
        "username": perm.user.username,
        "role": perm.role,
    }


class BranchViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """分支主视图：列表/创建/删除 + 聚合配置/添加工程/授权/实例轮询 action。"""

    queryset = Branch.objects.select_related("version").all()
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def list(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        qs = self.get_queryset().order_by("version__id", "id")
        return json_resp(ok([serialize_branch(b) for b in qs]))

    def create(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        body = request.data or {}
        version_id = body.get("version_id")
        version = Version.objects.filter(id=version_id).first() if version_id else None
        if version is None:
            return json_resp(err(42201, "版本必选且存在"), status=422)
        name = (body.get("name") or "").strip()
        if not name:
            return json_resp(err(42201, "分支名必填"), status=422)
        if Branch.objects.filter(version=version, name=name).exists():
            return json_resp(err(40902, "该版本下分支已存在"), status=409)
        try:
            branch = Branch.objects.create(
                version=version,
                name=name,
                repository_url=(body.get("repository_url") or "").strip(),
                description=(body.get("description") or "").strip(),
            )
        except IntegrityError:
            return json_resp(err(40902, "该版本下分支已存在"), status=409)
        return json_resp(ok(serialize_branch(branch)))

    def destroy(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(kwargs.get("pk")))
        if resp_err:
            return resp_err
        perr = _require_role(user, branch, ROLE_ADMIN)
        if perr:
            return perr
        branch_name = f"{branch.version.name}/{branch.name}"
        branch.delete()  # 级联清理工程关联/启动配置/授权/实例
        logger.info("[branch-config] delete branch=%s actor=%s", branch_name, user.username)
        return json_resp(ok(message="分支已删除"))

    @action(detail=True, methods=["get"])
    def config(self, request, pk=None):
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(pk))
        if resp_err:
            return resp_err
        return json_resp(ok(build_branch_config(branch, user)))

    @action(detail=True, methods=["post"])
    def projects(self, request, pk=None):
        """添加工程关联：ADMIN；重复关联 40903。"""
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, branch, ROLE_ADMIN)
        if perr:
            return perr
        body = request.data or {}
        project = Project.objects.filter(id=body.get("project_id")).first()
        if project is None:
            return json_resp(err(42201, "工程不存在"), status=422)
        if BranchProject.objects.filter(branch=branch, project=project).exists():
            return json_resp(err(40903, "该工程已关联此分支"), status=409)
        bp = BranchProject.objects.create(
            branch=branch, project=project, enabled=bool(body.get("enabled", True))
        )
        # 关联创建默认启动配置，保证前端 Tab② 可编辑
        StartupConfig.objects.create(branch_project=bp)
        return json_resp(
            ok(
                {
                    "id": bp.id,
                    "enabled": bp.enabled,
                    "project": serialize_project(project),
                    "startup_config": None,
                    "latest_instance": None,
                }
            )
        )

    @action(detail=True, methods=["post"])
    def permissions(self, request, pk=None):
        """添加/更新授权（幂等 upsert）：ADMIN；角色非法 42201。"""
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, branch, ROLE_ADMIN)
        if perr:
            return perr
        body = request.data or {}
        target = User.objects.filter(id=body.get("user_id")).first()
        if target is None:
            return json_resp(err(42201, "授权用户不存在"), status=422)
        role = body.get("role")
        if role not in ROLE_VALID:
            return json_resp(err(42201, "角色必须为 VIEWER/OPERATOR/ADMIN"), status=422)
        perm, _ = BranchPermission.objects.update_or_create(
            branch=branch, user=target, defaults={"role": role}
        )
        return json_resp(ok(_serialize_perm(perm)))

    @action(detail=True, methods=["get"])
    def instances(self, request, pk=None):
        """实例轮询：返回此分支全部关联工程的最新实例（读取时推进状态）。"""
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(pk))
        if resp_err:
            return resp_err
        rows = []
        for bp in branch.branch_projects.select_related("project").all():
            inst = latest_instance(bp)
            if inst:
                advance(inst)
            rows.append(
                {
                    "branch_project_id": bp.id,
                    "project_id": bp.project_id,
                    "project_name": bp.project.name,
                    "instance": serialize_instance(inst) if inst else None,
                }
            )
        return json_resp(ok(rows))


class BranchProjectViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """工程关联：删除 + 启动参数更新 + 启停模拟。"""

    queryset = BranchProject.objects.all()
    permission_classes = [AllowAny]
    http_method_names = ["delete", "put", "post", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        bp, resp_err = _bp_required(_bp_or_none(kwargs.get("pk")))
        if resp_err:
            return resp_err
        perr = _require_role(user, bp.branch, ROLE_ADMIN)
        if perr:
            return perr
        bp.delete()  # 级联删除启动配置与实例
        return json_resp(ok(message="工程关联已移除"))

    @action(detail=True, methods=["put"])
    def config(self, request, pk=None):
        """更新启动参数（partial）：ADMIN。"""
        user, error = authed_user(request)
        if error:
            return error
        bp, resp_err = _bp_required(_bp_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, bp.branch, ROLE_ADMIN)
        if perr:
            return perr
        conf = getattr(bp, "startup_config", None)
        if conf is None:
            conf = StartupConfig.objects.create(branch_project=bp)
        serializer = StartupConfigSerializer(conf, data=request.data, partial=True)
        if not serializer.is_valid():
            return json_resp(err(42201, _first_error(serializer.errors)), status=422)
        conf = serializer.save()
        return json_resp(ok(serialize_config(conf)))

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """启动模拟（OPERATOR 及以上）：重复启动 40903。"""
        user, error = authed_user(request)
        if error:
            return error
        bp, resp_err = _bp_required(_bp_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, bp.branch, ROLE_OPERATOR, ROLE_ADMIN)
        if perr:
            return perr
        inst = svc_start(bp, user.username)
        if inst is None:
            return json_resp(err(40903, "实例已在运行"), status=409)
        return json_resp(ok(serialize_instance(inst)))

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        """停止模拟（OPERATOR 及以上）：幂等。"""
        user, error = authed_user(request)
        if error:
            return error
        bp, resp_err = _bp_required(_bp_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, bp.branch, ROLE_OPERATOR, ROLE_ADMIN)
        if perr:
            return perr
        inst = svc_stop(bp, user.username)
        return json_resp(ok(serialize_instance(inst) if inst else None))


class BranchPermissionViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """分支授权管理：删除（ADMIN）。"""

    queryset = BranchPermission.objects.select_related("branch", "user").all()
    permission_classes = [AllowAny]
    http_method_names = ["delete", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        perm = self.get_queryset().filter(pk=kwargs.get("pk")).first()
        if perm is None:
            return json_resp(err(40401, "授权记录不存在"), status=404)
        perr = _require_role(user, perm.branch, ROLE_ADMIN)
        if perr:
            return perr
        perm.delete()
        return json_resp(ok(message="授权已移除"))


# ---------- 轻量辅助视图 ----------

def users_all(request):
    """可用授权用户列表（启用用户）：登录可访问。"""
    user, resp = authed_user(request)
    if resp:
        return resp
    qs = User.objects.filter(is_active=True).order_by("id")
    return json_resp(
        ok(
            [
                {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role}
                for u in qs
            ]
        )
    )


def projects_view(request):
    """工程库列表/创建：登录可访问；重名 40902。"""
    user, resp = authed_user(request)
    if resp:
        return resp
    if request.method == "GET":
        qs = Project.objects.all().order_by("id")
        return json_resp(ok([serialize_project(p) for p in qs]))
    if request.method == "POST":
        body = parse_body(request)
        name = (body.get("name") or "").strip()
        if not name:
            return json_resp(err(42201, "工程名必填"), status=422)
        if Project.objects.filter(name=name).exists():
            return json_resp(err(40902, "工程名已存在"), status=409)
        try:
            project = Project.objects.create(
                name=name,
                repository_url=(body.get("repository_url") or "").strip(),
                description=(body.get("description") or "").strip(),
            )
        except IntegrityError:
            return json_resp(err(40902, "工程名已存在"), status=409)
        return json_resp(ok(serialize_project(project)))
    return json_resp(err(42201, "不支持的请求方法"), status=422)
```

- [ ] **Step 2: 验证导入**

```bash
python -c "import build_protection_service.views.branch_config; print('ok')"
```

Expected: 输出 `ok`（无 ImportError）。

- [ ] **Step 3: Commit**

```bash
git add backend/build_protection_service/views/branch_config.py
git commit -m "feat: 分支配置视图层（分支/工程/授权/实例启停端点）"
```

---

## Task 6: 路由注册 + API 集成测试 + 回归

**Files:**
- Modify: `backend/build_protection_service/views/urls.py`
- Modify: `backend/build_protection_service/tests_branch_config.py`

- [ ] **Step 1: 注册路由**

在 `views/urls.py` 中：import 区新增 `from . import branch_config`（注意保持现有 import 分组），`urlpatterns` 尾部追加：

```python
    # 分支配置：分支/工程关联/启动参数/授权/实例（DRF ViewSet + 轻量视图）
    path("branches", branch_config.BranchViewSet.as_view({"get": "list", "post": "create"}), name="branches"),
    path("branches/<int:pk>", branch_config.BranchViewSet.as_view({"delete": "destroy"}), name="branch_detail"),
    path("branches/<int:pk>/config", branch_config.BranchViewSet.as_view({"get": "config"}), name="branch_config"),
    path("branches/<int:pk>/projects", branch_config.BranchViewSet.as_view({"post": "projects"}), name="branch_projects"),
    path("branches/<int:pk>/permissions", branch_config.BranchViewSet.as_view({"post": "permissions"}), name="branch_permissions"),
    path("branches/<int:pk>/instances", branch_config.BranchViewSet.as_view({"get": "instances"}), name="branch_instances"),
    path("branch-projects/<int:pk>", branch_config.BranchProjectViewSet.as_view({"delete": "destroy"}), name="branch_project"),
    path("branch-projects/<int:pk>/config", branch_config.BranchProjectViewSet.as_view({"put": "config"}), name="branch_project_config"),
    path("branch-projects/<int:pk>/start", branch_config.BranchProjectViewSet.as_view({"post": "start"}), name="branch_project_start"),
    path("branch-projects/<int:pk>/stop", branch_config.BranchProjectViewSet.as_view({"post": "stop"}), name="branch_project_stop"),
    path("branch-permissions/<int:pk>", branch_config.BranchPermissionViewSet.as_view({"delete": "destroy"}), name="branch_permission"),
    path("users/all", branch_config.users_all, name="users_all"),
    path("projects", branch_config.projects_view, name="projects"),
```

同时更新文件顶部 import：`from . import admin` 下方保持现状，在 `from . import executions, login, logs, plan, reports, strategies, weekly` 后追加 `from . import branch_config`。

- [ ] **Step 2: 写 API 集成测试（追加到 tests_branch_config.py）**

```python
class BranchConfigApiTests(BranchConfigFixture):
    """全接口集成：认证、聚合结构、权限矩阵、重复冲突、状态流转。"""

    def test_unauthorized_returns_40100(self):
        resp = self.client.get("/api/branches")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)

    def test_list_branches_and_create(self):
        _auth(self.client, self.builder)
        resp = self.client.get("/api/branches")
        self.assertEqual(resp.status_code, 200)
        first = resp.json()["data"][0]
        self.assertEqual(first["version_name"], "27A")
        self.assertEqual(first["name"], "master")
        self.assertEqual(first["repository_url"], "https://git.local/27A.git")

        resp = self.client.post(
            "/api/branches",
            {"version_id": self.version.id, "name": "TR5", "repository_url": "https://git.local/tr5.git"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "TR5")

    def test_create_branch_duplicate_40902_and_blank_42201(self):
        _auth(self.client, self.builder)
        resp = self.client.post(
            "/api/branches", {"version_id": self.version.id, "name": "master"}, format="json"
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        resp = self.client.post(
            "/api/branches", {"version_id": self.version.id, "name": "  "}, format="json"
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        resp = self.client.post("/api/branches", {"name": "x"}, format="json")
        self.assertEqual(resp.status_code, 422)

    def test_config_aggregation(self):
        _auth(self.client, self.builder)
        resp = self.client.get(f"/api/branches/{self.branch.id}/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["my_role"], "VIEWER")  # 未授权默认只读
        self.assertEqual(data["branch"]["name"], "master")
        self.assertEqual(data["branch_projects"][0]["project"]["name"], "GatewayEngine")
        self.assertEqual(
            data["branch_projects"][0]["startup_config"]["command"], "python manage.py runserver"
        )
        self.assertGreaterEqual(len(data["available_users"]), 4)
        self.assertGreaterEqual(len(data["available_projects"]), 1)

    def test_add_project_and_duplicate_40903(self):
        _auth(self.client, self.admin)
        project2 = Project.objects.create(name="WebPortal")
        resp = self.client.post(
            f"/api/branches/{self.branch.id}/projects",
            {"project_id": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)
        resp = self.client.post(
            f"/api/branches/{self.branch.id}/projects",
            {"project_id": project2.id, "enabled": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["project"]["name"], "WebPortal")

    def test_permission_write_requires_admin(self):
        _auth(self.client, self.viewer)
        resp = self.client.post(
            f"/api/branches/{self.branch.id}/projects",
            {"project_id": self.project.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)

    def test_update_startup_config(self):
        _auth(self.client, self.admin)
        resp = self.client.put(
            f"/api/branch-projects/{self.bp.id}/config",
            {"command": "node server.js", "timeout_seconds": 120},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["command"], "node server.js")
        self.assertEqual(data["timeout_seconds"], 120)
        # partial 更新保留旧字段
        self.assertEqual(data["args"], ["0.0.0.0:8000"])
        self.assertEqual(data["env_vars"], {"PORT": "8000"})
        self.assertIn("node server.js", data["raw_json"])

    def test_start_stop_flow_and_batch_instances(self):
        _auth(self.client, self.admin)
        resp = self.client.post(f"/api/branch-projects/{self.bp.id}/start")
        self.assertEqual(resp.status_code, 200)
        inst = resp.json()["data"]
        self.assertEqual(inst["status"], "STARTING")
        self.assertIsNotNone(inst["pid"])

        # 重复启动 → 40903
        resp = self.client.post(f"/api/branch-projects/{self.bp.id}/start")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40903)

        # 模拟推进：把 started_at 拨回 5 秒，轮询接口应返回 RUNNING
        Instance.objects.filter(id=inst["id"]).update(
            started_at=timezone.now() - timedelta(seconds=5)
        )
        resp = self.client.get(f"/api/branches/{self.branch.id}/instances")
        self.assertEqual(resp.status_code, 200)
        row = resp.json()["data"][0]
        self.assertEqual(row["branch_project_id"], self.bp.id)
        self.assertEqual(row["project_name"], "GatewayEngine")
        self.assertEqual(row["instance"]["status"], "RUNNING")

        # 停止 → STOPPED
        resp = self.client.post(f"/api/branch-projects/{self.bp.id}/stop")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "STOPPED")
        self.assertEqual(resp.json()["data"]["exit_code"], 0)

    def test_operator_can_start_viewer_cannot(self):
        BranchPermission.objects.create(
            branch=self.branch, user=self.builder, role="OPERATOR"
        )
        _auth(self.client, self.builder)
        resp = self.client.post(f"/api/branch-projects/{self.bp.id}/start")
        self.assertEqual(resp.status_code, 200)
        _auth(self.client, self.viewer)  # 无授权默认 VIEWER
        resp = self.client.post(f"/api/branch-projects/{self.bp.id}/start")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(f"/api/branch-projects/{self.bp.id}/stop")
        self.assertEqual(resp.status_code, 403)

    def test_permission_crud(self):
        _auth(self.client, self.admin)
        resp = self.client.post(
            f"/api/branches/{self.branch.id}/permissions",
            {"user_id": self.builder.id, "role": "OPERATOR"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        perm_id = resp.json()["data"]["id"]
        self.assertEqual(resp.json()["data"]["role"], "OPERATOR")
        # 重复授权 upsert 不报错
        resp = self.client.post(
            f"/api/branches/{self.branch.id}/permissions",
            {"user_id": self.builder.id, "role": "ADMIN"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        # 非法角色 42201
        resp = self.client.post(
            f"/api/branches/{self.branch.id}/permissions",
            {"user_id": self.builder.id, "role": "SUPER"},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)
        # 删除授权：VIEWER 删除被拒
        resp = self.client.delete(f"/api/branch-permissions/{perm_id}")
        # 注意：viewer 用户此前Fixture中无授权，admin 直接删即可
        self.assertEqual(resp.status_code, 200)
        # 再删一次 404
        resp = self.client.delete(f"/api/branch-permissions/{perm_id}")
        self.assertEqual(resp.status_code, 404)

    def test_branch_delete_requires_admin_role(self):
        _auth(self.client, self.builder)
        resp = self.client.delete(f"/api/branches/{self.branch.id}")
        self.assertEqual(resp.status_code, 403)
        _auth(self.client, self.viewer)
        BranchPermission.objects.create(
            branch=self.branch, user=self.viewer, role="ADMIN"
        )
        resp = self.client.delete(f"/api/branches/{self.branch.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 0)
        self.assertEqual(BranchProject.objects.count(), 0)

    def test_projects_view_and_users_all(self):
        _auth(self.client, self.admin)
        resp = self.client.post(
            "/api/projects", {"name": "WebPortal", "repository_url": "https://git.local/wp.git"}
        )
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post("/api/projects", {"name": "WebPortal"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        resp = self.client.get("/api/projects")
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get("/api/users/all")
        self.assertGreaterEqual(len(resp.json()["data"]), 4)
```

- [ ] **Step 3: 运行全部测试**

```bash
python manage.py test build_protection_service -v 2
```

Expected: 全部 PASS（原有测试 + 新增模型/服务/API 用例）。

- [ ] **Step 4: Commit**

```bash
git add backend/build_protection_service/views/urls.py backend/build_protection_service/tests_branch_config.py
git commit -m "feat: 分支配置路由注册与 API 集成测试"
```

---

## Task 7: 前端 API 封装

**Files:**
- Create: `frontend/src/api/branchConfig.ts`

- [ ] **Step 1: 创建 API 封装**

```typescript
// 分支配置 API 模块
// 契约：统一响应 { code, message, data }；写接口权限门槛由后端校验
import http from "@/api/http";

/** 分支角色（与后端 BranchPermission.ROLE_CHOICES 一致） */
export type BranchRole = "VIEWER" | "OPERATOR" | "ADMIN";

/** 实例状态（与后端 Instance.STATUS_CHOICES 一致） */
export type InstanceStatus = "STARTING" | "RUNNING" | "STOPPED" | "ERROR";

export interface BranchItem {
  id: number;
  version_id: number;
  version_name: string;
  name: string;
  repository_url: string;
  description: string;
}

export interface ProjectItem {
  id: number;
  name: string;
  repository_url: string;
  description: string;
}

export interface StartupConfigItem {
  command: string;
  args: string[];
  env_vars: Record<string, string>;
  working_directory: string;
  timeout_seconds: number;
  auto_restart: boolean;
  raw_json: string;
  updated_at?: string;
}

export interface InstanceItem {
  id: number;
  status: InstanceStatus;
  pid: number | null;
  started_at: string | null;
  stopped_at: string | null;
  last_heartbeat_at: string | null;
  exit_code: number | null;
  log_tail: string;
}

export interface BranchProjectItem {
  id: number;
  enabled: boolean;
  project: ProjectItem;
  startup_config: StartupConfigItem | null;
  latest_instance: InstanceItem | null;
}

export interface PermissionItem {
  id: number;
  user_id: number;
  username: string;
  role: BranchRole;
}

export interface UserOption {
  id: number;
  username: string;
  display_name: string;
  role: string;
}

/** 聚合配置响应：GET /branches/{id}/config */
export interface BranchConfigResponse {
  branch: BranchItem;
  branch_projects: BranchProjectItem[];
  permissions: PermissionItem[];
  my_role: BranchRole;
  available_users: UserOption[];
  available_projects: { id: number; name: string }[];
}

/** 实例轮询行：GET /branches/{id}/instances */
export interface InstanceRow {
  branch_project_id: number;
  project_id: number;
  project_name: string;
  instance: InstanceItem | null;
}

// ---- 分支 ----
export function getBranches(): Promise<BranchItem[]> {
  return http.get("/branches");
}
export function createBranch(data: {
  version_id: number;
  name: string;
  repository_url?: string;
  description?: string;
}): Promise<BranchItem> {
  return http.post("/branches", data);
}
export function deleteBranch(id: number): Promise<null> {
  return http.delete(`/branches/${id}`);
}
export function getBranchConfig(id: number): Promise<BranchConfigResponse> {
  return http.get(`/branches/${id}/config`);
}

// ---- 工程关联与启动参数 ----
export function addBranchProject(
  branchId: number,
  data: { project_id: number; enabled?: boolean }
): Promise<BranchProjectItem> {
  return http.post(`/branches/${branchId}/projects`, data);
}
export function removeBranchProject(bpId: number): Promise<null> {
  return http.delete(`/branch-projects/${bpId}`);
}
export function updateStartupConfig(
  bpId: number,
  data: Partial<Omit<StartupConfigItem, "raw_json" | "updated_at">>
): Promise<StartupConfigItem> {
  return http.put(`/branch-projects/${bpId}/config`, data);
}

// ---- 授权 ----
export function addBranchPermission(
  branchId: number,
  data: { user_id: number; role: BranchRole }
): Promise<PermissionItem> {
  return http.post(`/branches/${branchId}/permissions`, data);
}
export function removeBranchPermission(permId: number): Promise<null> {
  return http.delete(`/branch-permissions/${permId}`);
}
export function getUsersAll(): Promise<UserOption[]> {
  return http.get("/users/all");
}

// ---- 工程库 ----
export function getProjects(): Promise<ProjectItem[]> {
  return http.get("/projects");
}
export function createProject(data: {
  name: string;
  repository_url?: string;
  description?: string;
}): Promise<ProjectItem> {
  return http.post("/projects", data);
}

// ---- 实例 ----
export function getBranchInstances(branchId: number): Promise<InstanceRow[]> {
  return http.get(`/branches/${branchId}/instances`);
}
export function startBranchProject(bpId: number): Promise<InstanceItem> {
  return http.post(`/branch-projects/${bpId}/start`);
}
export function stopBranchProject(bpId: number): Promise<InstanceItem | null> {
  return http.post(`/branch-projects/${bpId}/stop`);
}
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无新增类型错误（可行时）或至少 API 文件无错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/branchConfig.ts
git commit -m "feat: 前端分支配置 API 封装与类型定义"
```

---

## Task 8: 前端菜单路由

**Files:**
- Modify: `frontend/src/router/asyncRoutes.ts`

- [ ] **Step 1: 注册一级菜单（日志中心之后，rank 10）**

在 `asyncRoutes` 数组 `logs` 项**之后**插入：

```typescript
  {
    path: "/branch-config",
    name: "BranchConfig",
    component: Layout,
    redirect: "/branch-config/index",
    meta: {
      icon: "ep/connection",
      title: "分支配置",
      rank: 10
    },
    children: [
      {
        path: "/branch-config/index",
        name: "BranchConfigIndex",
        component: () => import("@/views/branch-config/index.vue"),
        meta: {
          title: "分支配置",
          roles: ALL_ROLES
        }
      }
    ]
  }
```

注意：`ep/connection` 属于 Element Plus 图标集（`@element-plus/icons-vue` 已在基座注册）。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/asyncRoutes.ts
git commit -m "feat: 新增分支配置一级菜单路由"
```

---

## Task 9: 前端页面（单页四组件）

**Files:**
- Create: `frontend/src/views/branch-config/index.vue`
- Create: `frontend/src/views/branch-config/components/ProjectsPanel.vue`
- Create: `frontend/src/views/branch-config/components/StartupConfigForm.vue`
- Create: `frontend/src/views/branch-config/components/InstancesPanel.vue`

- [ ] **Step 1: 创建 ProjectsPanel.vue（Tab① 工程关联）**

```vue
<template>
  <div>
    <div class="panel-toolbar">
      <el-button
        type="primary"
        size="small"
        :disabled="myRole !== 'ADMIN'"
        @click="dialogVisible = true"
      >
        ＋ 添加工程
      </el-button>
    </div>
    <el-table :data="items" size="small" border>
      <el-table-column label="工程名" prop="project.name" min-width="140" />
      <el-table-column label="仓库地址" prop="project.repository_url" min-width="200" show-overflow-tooltip />
      <el-table-column label="启用" width="90">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? "已启用" : "已停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            text
            type="primary"
            :disabled="myRole !== 'ADMIN'"
            @click="$emit('edit-config', row)"
          >
            编辑参数
          </el-button>
          <el-button
            size="small"
            text
            type="success"
            :disabled="myRole === 'VIEWER'"
            @click="$emit('start', row.id)"
          >
            启动
          </el-button>
          <el-button
            size="small"
            text
            type="warning"
            :disabled="myRole === 'VIEWER'"
            @click="$emit('stop', row.id)"
          >
            停止
          </el-button>
          <el-button
            size="small"
            text
            type="danger"
            :disabled="myRole !== 'ADMIN'"
            @click="$emit('remove', row.id)"
          >
            移除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="添加工程" width="420px">
      <el-select
        v-model="selectedProjectId"
        filterable
        placeholder="从工程库选择"
        style="width: 100%"
      >
        <el-option
          v-for="p in availableProjects"
          :key="p.id"
          :label="p.name"
          :value="p.id"
          :disabled="linkedIds.includes(p.id)"
        />
      </el-select>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="confirmAdd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import type { BranchRole, BranchProjectItem } from "@/api/branchConfig";

defineProps<{
  items: BranchProjectItem[];
  myRole: BranchRole;
  availableProjects: { id: number; name: string }[];
  adding: boolean;
}>();

const emit = defineEmits<{
  (e: "add", projectId: number): void;
  (e: "remove", bpId: number): void;
  (e: "edit-config", bp: BranchProjectItem): void;
  (e: "start", bpId: number): void;
  (e: "stop", bpId: number): void;
}>();

const dialogVisible = ref(false);
const selectedProjectId = ref<number | null>(null);
const adding = ref(false);

const linkedIds = computed(() => props.items.map(i => i.project.id));

const props = defineProps<{
  items: BranchProjectItem[];
  myRole: BranchRole;
  availableProjects: { id: number; name: string }[];
}>();

function confirmAdd() {
  if (!selectedProjectId.value) {
    ElMessage.warning("请选择工程");
    return;
  }
  emit("add", selectedProjectId.value);
  dialogVisible.value = false;
  selectedProjectId.value = null;
}
</script>
```

注意：组件内 `defineProps` 只能声明一次，请将上面两处合并为**单一** `defineProps` 声明（保留注释说明），`adding` 状态由父组件通过 props 传入或子组件本地管理二选一——**推荐**：父组件持有 loading 状态，子组件只声明：

```typescript
const props = defineProps<{
  items: BranchProjectItem[];
  myRole: BranchRole;
  availableProjects: { id: number; name: string }[];
  adding: boolean;
}>();
```

- [ ] **Step 2: 创建 StartupConfigForm.vue（Tab② 启动参数）**

```vue
<template>
  <div v-if="bp">
    <el-form label-width="120px" size="small" :disabled="myRole !== 'ADMIN'">
      <el-form-item label="启动命令">
        <el-input v-model="form.command" placeholder="如 python manage.py runserver" />
      </el-form-item>
      <el-form-item label="参数">
        <div v-for="(arg, idx) in form.args" :key="idx" class="kv-row">
          <el-input v-model="form.args[idx]" placeholder="参数值" />
          <el-button text type="danger" @click="form.args.splice(idx, 1)">删除</el-button>
        </div>
        <el-button size="small" text type="primary" @click="form.args.push('')">＋ 添加参数</el-button>
      </el-form-item>
      <el-form-item label="环境变量">
        <div v-for="(key, idx) in envKeys" :key="idx" class="kv-row">
          <el-input v-model="envKeys[idx]" placeholder="KEY" style="width: 40%" />
          <el-input v-model="form.env_vars[envKeys[idx]] ?? ''" placeholder="VALUE" style="width: 40%" @update:model-value="v => bindEnv(idx, v)" />
          <el-button text type="danger" @click="removeEnv(idx)">删除</el-button>
        </div>
        <el-button size="small" text type="primary" @click="addEnv">＋ 添加变量</el-button>
      </el-form-item>
      <el-form-item label="工作目录">
        <el-input v-model="form.working_directory" placeholder="绝对路径，可空" />
      </el-form-item>
      <el-form-item label="启动超时(秒)">
        <el-input-number v-model="form.timeout_seconds" :min="1" :max="3600" />
      </el-form-item>
      <el-form-item label="自动重启">
        <el-switch v-model="form.auto_restart" />
      </el-form-item>
      <el-form-item v-if="form.raw_json" label="原始配置">
        <pre class="raw-json">{{ form.raw_json }}</pre>
      </el-form-item>
      <el-form-item v-if="myRole === 'ADMIN'">
        <el-button type="primary" :loading="saving" @click="$emit('save', form)">保存参数</el-button>
      </el-form-item>
    </el-form>
  </div>
  <el-empty v-else description="请先选择要编辑的工程" />
</template>

<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import type { BranchRole, BranchProjectItem, StartupConfigItem } from "@/api/branchConfig";

const props = defineProps<{
  bp: BranchProjectItem | null;
  myRole: BranchRole;
  saving: boolean;
}>();

const emit = defineEmits<{ (e: "save", form: StartupConfigItem): void }>();

const form = reactive<StartupConfigItem>({
  command: "",
  args: [],
  env_vars: {},
  working_directory: "",
  timeout_seconds: 60,
  auto_restart: false,
  raw_json: ""
});

watch(
  () => props.bp,
  bp => {
    const conf = bp?.startup_config;
    form.command = conf?.command ?? "";
    form.args = [...(conf?.args ?? [])];
    form.env_vars = { ...(conf?.env_vars ?? {}) };
    form.working_directory = conf?.working_directory ?? "";
    form.timeout_seconds = conf?.timeout_seconds ?? 60;
    form.auto_restart = conf?.auto_restart ?? false;
    form.raw_json = conf?.raw_json ?? "";
  },
  { immediate: true }
);

/** 环境变量键列表（与 form.env_vars 同步） */
const envKeys = computed(() => Object.keys(form.env_vars));

/** 环境变量行标注：key 自身可编辑，value 同步回对象 */
function bindEnv(idx: number, value: string) {
  const key = envKeys.value[idx];
  form.env_vars[key] = value;
}
function addEnv() {
  form.env_vars[""] = "";
}
function removeEnv(idx: number) {
  const key = envKeys.value[idx];
  delete form.env_vars[key];
}
</script>

<style scoped>
.kv-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  align-items: center;
}
.raw-json {
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
```

- [ ] **Step 3: 创建 InstancesPanel.vue（Tab③ 运行状态）**

```vue
<template>
  <el-table :data="rows" size="small" border>
    <el-table-column label="工程名" prop="project_name" min-width="140" />
    <el-table-column label="状态" width="100">
      <template #default="{ row }">
        <el-tag v-if="row.instance" :type="statusType(row.instance.status)" size="small">
          {{ statusLabel(row.instance.status) }}
        </el-tag>
        <el-tag v-else type="info" size="small">未启动</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="PID" width="90">
      <template #default="{ row }">{{ row.instance?.pid ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="启动时间" width="170">
      <template #default="{ row }">{{ row.instance?.started_at ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="停止时间" width="170">
      <template #default="{ row }">{{ row.instance?.stopped_at ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="最近心跳" width="170">
      <template #default="{ row }">{{ row.instance?.last_heartbeat_at ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="日志尾部" min-width="200" show-overflow-tooltip>
      <template #default="{ row }">{{ row.instance?.log_tail ?? "-" }}</template>
    </el-table-column>
    <el-table-column label="操作" width="160" fixed="right">
      <template #default="{ row }">
        <el-button
          size="small"
          text
          type="success"
          :disabled="myRole === 'VIEWER' || row.instance?.status === 'RUNNING' || row.instance?.status === 'STARTING' || startingId === row.branch_project_id"
          :loading="startingId === row.branch_project_id"
          @click="$emit('start', row.branch_project_id)"
        >
          启动
        </el-button>
        <el-button
          size="small"
          text
          type="warning"
          :disabled="myRole === 'VIEWER' || !row.instance || row.instance.status === 'STOPPED' || stoppingId === row.branch_project_id"
          :loading="stoppingId === row.branch_project_id"
          @click="$emit('stop', row.branch_project_id)"
        >
          停止
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { BranchRole, InstanceRow, InstanceStatus } from "@/api/branchConfig";

defineProps<{
  rows: InstanceRow[];
  myRole: BranchRole;
  startingId: number | null;
  stoppingId: number | null;
}>();

defineEmits<{
  (e: "start", bpId: number): void;
  (e: "stop", bpId: number): void;
}>();

const STATUS_LABEL: Record<InstanceStatus, string> = {
  STARTING: "启动中",
  RUNNING: "运行中",
  STOPPED: "已停止",
  ERROR: "异常"
};

const STATUS_TYPE: Record<InstanceStatus, "primary" | "success" | "info" | "danger"> = {
  STARTING: "primary",
  RUNNING: "success",
  STOPPED: "info",
  ERROR: "danger"
};

function statusLabel(s: InstanceStatus): string {
  return STATUS_LABEL[s] ?? s;
}
function statusType(s: InstanceStatus): "primary" | "success" | "info" | "danger" {
  return STATUS_TYPE[s] ?? "info";
}
</script>
```

- [ ] **Step 4: 创建 index.vue（单页骨架 + 左列表 + 权限面板 + 轮询）**

```vue
<template>
  <div class="branch-config">
    <!-- 左侧：分支列表 -->
    <aside class="branch-side">
      <div class="side-toolbar">
        <el-input v-model="keyword" size="small" placeholder="搜索分支" clearable style="flex: 1" />
        <el-button size="small" type="primary" @click="openNewDialog">＋ 新建</el-button>
      </div>
      <div class="branch-list">
        <div
          v-for="b in filteredBranches"
          :key="b.id"
          class="branch-item"
          :class="{ active: b.id === selectedId }"
          @click="selectBranch(b.id)"
        >
          <div class="branch-name">{{ b.version_name }} / {{ b.name }}</div>
          <div v-if="b.repository_url" class="branch-url">{{ b.repository_url }}</div>
        </div>
        <el-empty v-if="!filteredBranches.length" description="暂无分支，点击新建" :image-size="60" />
      </div>
    </aside>

    <!-- 右侧：详情 -->
    <section class="branch-detail">
      <template v-if="config">
        <!-- 权限面板 -->
        <div class="perm-bar">
          <span class="perm-title">权限</span>
          <el-tag
            v-for="p in config.permissions"
            :key="p.id"
            :type="permTagType(p.role)"
            size="small"
            closable
            :closable="config.my_role === 'ADMIN'"
            @close="removePermission(p)"
          >
            {{ p.username }} · {{ permLabel(p.role) }}
          </el-tag>
          <el-button
            v-if="config.my_role === 'ADMIN'"
            size="small"
            text
            type="primary"
            @click="permDialogVisible = true"
          >
            ＋ 添加授权
          </el-button>
          <span class="perm-myrole">我的角色：{{ permLabel(config.my_role) }}</span>
        </div>

        <el-tabs v-model="activeTab" class="detail-tabs">
          <el-tab-pane label="工程关联" name="projects">
            <ProjectsPanel
              :items="config.branch_projects"
              :my-role="config.my_role"
              :available-projects="config.available_projects"
              :adding="addingProject"
              @add="addProject"
              @remove="removeProject"
              @edit-config="editConfig"
              @start="startInstance"
              @stop="stopInstance"
            />
          </el-tab-pane>
          <el-tab-pane label="启动参数" name="config">
            <StartupConfigForm
              :bp="editingBp"
              :my-role="config.my_role"
              :saving="savingConfig"
              @save="saveConfig"
            />
          </el-tab-pane>
          <el-tab-pane label="运行状态" name="instances">
            <InstancesPanel
              :rows="instanceRows"
              :my-role="config.my_role"
              :starting-id="startingId"
              :stopping-id="stoppingId"
              @start="startInstance"
              @stop="stopInstance"
            />
          </el-tab-pane>
        </el-tabs>
      </template>
      <el-empty v-else description="请选择左侧分支" />
    </section>

    <!-- 新建分支 -->
    <el-dialog v-model="newDialogVisible" title="新建分支" width="440px">
      <el-form label-width="80px" size="small">
        <el-form-item label="版本">
          <el-select v-model="newForm.version_id" filterable placeholder="选择版本" style="width: 100%">
            <el-option v-for="v in versionOptions" :key="v.version_id" :label="v.version_name" :value="v.version_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="分支名">
          <el-input v-model="newForm.name" placeholder="如 master / TR5" />
        </el-form-item>
        <el-form-item label="仓库地址">
          <el-input v-model="newForm.repository_url" placeholder="可选，如 https://git.local/27A.git" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingBranch" @click="createBranch">创建</el-button>
      </template>
    </el-dialog>

    <!-- 添加授权 -->
    <el-dialog v-model="permDialogVisible" title="添加授权" width="420px">
      <el-form label-width="60px" size="small">
        <el-form-item label="用户">
          <el-select v-model="permForm.user_id" filterable placeholder="选择用户" style="width: 100%">
            <el-option
              v-for="u in config?.available_users ?? []"
              :key="u.id"
              :label="`${u.username}（${u.display_name || u.role}）`"
              :value="u.id"
              :disabled="grantedUserIds.includes(u.id)"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="permForm.role">
            <el-radio value="VIEWER">查看者</el-radio>
            <el-radio value="OPERATOR">操作者</el-radio>
            <el-radio value="ADMIN">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="permDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPerm" @click="savePermission">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getPlan } from "@/api/plan";
import {
  addBranchPermission,
  addBranchProject,
  createBranch as apiCreateBranch,
  deleteBranch,
  getBranchConfig,
  getBranchInstances,
  removeBranchPermission,
  removeBranchProject,
  startBranchProject,
  stopBranchProject,
  updateStartupConfig,
  type BranchConfigResponse,
  type BranchItem,
  type BranchProjectItem,
  type BranchRole,
  type InstanceRow,
  type PermissionItem,
  type StartupConfigItem
} from "@/api/branchConfig";
import ProjectsPanel from "./components/ProjectsPanel.vue";
import StartupConfigForm from "./components/StartupConfigForm.vue";
import InstancesPanel from "./components/InstancesPanel.vue";

// ---------- 分支列表 ----------
const branches = ref<BranchItem[]>([]);
const selectedId = ref<number | null>(null);
const keyword = ref("");
const config = ref<BranchConfigResponse>();
const loadingConfig = ref(false);

const filteredBranches = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return branches.value;
  return branches.value.filter(
    b => b.name.toLowerCase().includes(kw) || b.version_name.toLowerCase().includes(kw)
  );
});

async function loadBranches() {
  branches.value = await getBranches();
  if (!selectedId.value && branches.value.length) {
    selectedId.value = branches.value[0].id;
  }
  if (!branches.value.length) {
    config.value = undefined;
  }
}

async function selectBranch(id: number) {
  if (selectedId.value === id) return;
  selectedId.value = id;
  await loadConfig();
}

async function loadConfig() {
  if (!selectedId.value) return;
  loadingConfig.value = true;
  try {
    config.value = await getBranchConfig(selectedId.value);
    editingBp.value = config.value.branch_projects[0] ?? null;
    activeTab.value = "projects";
  } finally {
    loadingConfig.value = false;
  }
}

// ---------- 实例轮询（仅当前分支，5s） ----------
const instanceRows = ref<InstanceRow[]>([]);
let pollTimer: number | null = null;

async function pollInstances() {
  if (!selectedId.value) return;
  try {
    instanceRows.value = await getBranchInstances(selectedId.value);
  } catch {
    /* 轮询失败静默，等待下一周期 */
  }
}

watch(selectedId, id => {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
  if (id) {
    pollInstances();
    pollTimer = window.setInterval(pollInstances, 5000);
  }
});

onBeforeUnmount(() => {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
});

// ---------- 新建分支 ----------
const newDialogVisible = ref(false);
const creatingBranch = ref(false);
const newForm = reactive<{ version_id: number | undefined; name: string; repository_url: string }>({
  version_id: undefined,
  name: "",
  repository_url: ""
});
const versionOptions = ref<{ version_id: number; version_name: string }[]>([]);

async function openNewDialog() {
  const today = new Date().toISOString().slice(0, 10);
  try {
    const plan = await getPlan({ date: today });
    versionOptions.value = plan.map(p => ({ version_id: p.version_id, version_name: p.version_name }));
  } catch {
    versionOptions.value = [];
  }
  newForm.version_id = versionOptions.value[0]?.version_id;
  newForm.name = "";
  newForm.repository_url = "";
  newDialogVisible.value = true;
}

async function createBranch() {
  if (!newForm.version_id || !newForm.name.trim()) {
    ElMessage.warning("请选择版本并填写分支名");
    return;
  }
  creatingBranch.value = true;
  try {
    const created = await apiCreateBranch({
      version_id: newForm.version_id,
      name: newForm.name.trim(),
      repository_url: newForm.repository_url.trim() || undefined
    });
    ElMessage.success("分支已创建");
    newDialogVisible.value = false;
    branches.value.push(created);
    selectedId.value = created.id;
    await loadConfig();
  } finally {
    creatingBranch.value = false;
  }
}

// ---------- 工程关联 ----------
const addingProject = ref(false);

async function addProject(projectId: number) {
  if (!selectedId.value) return;
  addingProject.value = true;
  try {
    await addBranchProject(selectedId.value, { project_id: projectId, enabled: true });
    ElMessage.success("工程已关联");
    await loadConfig();
  } finally {
    addingProject.value = false;
  }
}

async function removeProject(bpId: number) {
  try {
    await ElMessageBox.confirm("移除该工程关联？其启动配置与实例记录将一并删除", "提示", {
      type: "warning"
    });
  } catch {
    return; // 用户取消
  }
  await removeBranchProject(bpId);
  ElMessage.success("工程关联已移除");
  await loadConfig();
}

// ---------- 启动参数 ----------
const activeTab = ref("projects");
const editingBp = ref<BranchProjectItem | null>(null);
const savingConfig = ref(false);

function editConfig(bp: BranchProjectItem) {
  editingBp.value = bp;
  activeTab.value = "config";
}

async function saveConfig(form: StartupConfigItem) {
  if (!editingBp.value) return;
  savingConfig.value = true;
  try {
    await updateStartupConfig(editingBp.value.id, {
      command: form.command,
      args: form.args,
      env_vars: form.env_vars,
      working_directory: form.working_directory,
      timeout_seconds: form.timeout_seconds,
      auto_restart: form.auto_restart
    });
    ElMessage.success("启动参数已保存");
    await loadConfig();
  } finally {
    savingConfig.value = false;
  }
}

// ---------- 启停 ----------
const startingId = ref<number | null>(null);
const stoppingId = ref<number | null>(null);

async function startInstance(bpId: number) {
  startingId.value = bpId;
  try {
    const inst = await startBranchProject(bpId);
    ElMessage.success(`已发起启动（pid=${inst.pid}）`);
    await refreshAfterOp();
  } finally {
    startingId.value = null;
  }
}

async function stopInstance(bpId: number) {
  stoppingId.value = bpId;
  try {
    await stopBranchProject(bpId);
    ElMessage.success("已发起停止");
    await refreshAfterOp();
  } finally {
    stoppingId.value = null;
  }
}

async function refreshAfterOp() {
  await loadConfig();
  await pollInstances();
}

// ---------- 授权 ----------
const permDialogVisible = ref(false);
const savingPerm = ref(false);
const permForm = reactive<{ user_id: number | undefined; role: BranchRole }>({
  user_id: undefined,
  role: "OPERATOR"
});

const grantedUserIds = computed(() => (config.value?.permissions ?? []).map(p => p.user_id));

async function openPermDialog() {
  permForm.user_id = undefined;
  permForm.role = "OPERATOR";
  permDialogVisible.value = true;
}

async function savePermission() {
  if (!selectedId.value || !permForm.user_id) {
    ElMessage.warning("请选择用户");
    return;
  }
  savingPerm.value = true;
  try {
    await addBranchPermission(selectedId.value, { user_id: permForm.user_id, role: permForm.role });
    ElMessage.success("授权已保存");
    permDialogVisible.value = false;
    await loadConfig();
  } finally {
    savingPerm.value = false;
  }
}

async function removePermission(perm: PermissionItem) {
  try {
    await ElMessageBox.confirm(`移除用户 ${perm.username} 的授权？`, "提示", { type: "warning" });
  } catch {
    return;
  }
  await removeBranchPermission(perm.id);
  ElMessage.success("授权已移除");
  await loadConfig();
}

// ---------- 权限文案 ----------
const ROLE_LABEL: Record<BranchRole, string> = {
  VIEWER: "查看者",
  OPERATOR: "操作者",
  ADMIN: "管理员"
};
const ROLE_TAG: Record<BranchRole, "info" | "primary" | "warning"> = {
  VIEWER: "info",
  OPERATOR: "primary",
  ADMIN: "warning"
};
function permLabel(r: BranchRole): string {
  return ROLE_LABEL[r] ?? r;
}
function permTagType(r: BranchRole): "info" | "primary" | "warning" {
  return ROLE_TAG[r] ?? "info";
}
</script>

<style scoped>
.branch-config {
  display: flex;
  gap: 12px;
  height: 100%;
  min-height: 520px;
}
.branch-side {
  width: 30%;
  min-width: 220px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #fff;
}
.side-toolbar {
  display: flex;
  gap: 8px;
}
.branch-list {
  flex: 1;
  overflow: auto;
}
.branch-item {
  padding: 8px 10px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid transparent;
}
.branch-item:hover {
  background: var(--el-fill-color-light);
}
.branch-item.active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}
.branch-name {
  font-size: 14px;
  font-weight: 600;
}
.branch-url {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.branch-detail {
  flex: 1;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px;
  background: #fff;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.perm-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.perm-title {
  font-weight: 600;
  font-size: 14px;
}
.perm-myrole {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.detail-tabs {
  flex: 1;
}
</style>
```

- [ ] **Step 5: 类型检查**

```bash
cd frontend && npx vue-tsc --noEmit
```

Expected: 无类型错误。若 `el-radio value` 提示使用 `label` 属性（Element Plus 版本差异），改用 `:label`/`label` 写法使选项值绑定一致（以基座 Element Plus 版本为准，`el-radio` 旧版用 `label` 传值、新版用 `value`+`label`）。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/branch-config
git commit -m "feat: 分支配置单页（左列表右详情 + 权限面板 + 三 Tab）"
```

---

## Task 10: 验证收尾

**Files:** 无新增。

- [ ] **Step 1: 后端全量回归**

```bash
cd backend && python manage.py test build_protection_service -v 2
```

Expected: 全部 PASS（含原有用例与新增约 30 个用例）。

- [ ] **Step 2: 前端类型与构建**

```bash
cd frontend && npx vue-tsc --noEmit && npm run build
```

Expected: 类型检查通过，构建产物生成至 `dist/`。

- [ ] **Step 3: 手动联调清单（先启动后端再启动前端）**

```bash
cd backend && python manage.py runserver 8000
# 新终端：
cd frontend && npm run dev
```

浏览器 `http://localhost:5173/#/branch-config`（端口按 `.env.development`），登录 `admin/123456`，走查：
1. 左列表展示现有分支（27A/master 等），点击选中后右侧渲染聚合数据。
2. 「＋ 新建」选择版本 27A、名称 TR5 → 列表出现新分支。
3. 进入 TR5，Tab① 添加工程（选择 GatewayEngine）→ 行出现；点击「编辑参数」跳 Tab② → 填写命令/参数/环境变量 → 保存成功。
4. Tab③ 点击「启动」→ 状态 STARTING → 5 秒轮询后变 RUNNING；「停止」→ STOPPED。
5. 权限面板「＋ 添加授权」选 bob 角色"操作者"→ 退出登录用 `bob/123456` 登录 → 该分支可见、可启停、无"添加工程/编辑参数/移除"按钮。
6. View（如 viewer 用户）登录 → 启停按钮置灰（403 兜底已在后端测试覆盖）。
7. 搜索框过滤生效；浏览器地址栏输入 `/plan` 等既有路由不受影响。

- [ ] **Step 4: 提交联调修复（如有）与收尾 Commit**

```bash
git add -A
git commit -m "chore: 分支配置联调修复与验证"
```

（若联调无修改，则跳过本步。）

---

## Self-Review 记录（编写时已核对）

- **Spec 覆盖**：模型 6 项 ✓（Task 1-2）、12+ 端点全量 ✓（Task 5-6 路由表）、权限矩阵 ✓（Task 6 用例 + 视图 `_require_role`）、状态机 ✓（Task 3 服务 + Task 6 用例）、聚合结构 ✓（Task 3 `build_branch_config` + Task 6 断言）、`my_role`/轮询 ✓（Task 6 聚合断言 + Task 9 轮询）、错误码 40903 ✓、前端布局 A/权限面板/三 Tab/5s 轮询/新建分支/添加工程/启停 ✓（Task 9）、测试计划 ✓（Task 2/3/6）。
- **类型一致性**：`BranchRole/InstanceStatus/InstanceRow/BranchConfigResponse` 等前端类型与后端序列化字段逐项对应；`my_role` 大写枚举前后端一致。
- **偏离设计文档的两处（有理由）**：① 分支/工程重名用 `40902` 而非 40901——`http.ts` 将 40901 写死为「策略时间冲突」弹框，误用会弹错标题；② 新建分支版本下拉复用 `GET /api/plan`（所有角色可访问）而非仅 admin 的 `/admin/versions`。