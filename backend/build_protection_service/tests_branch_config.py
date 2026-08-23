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