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