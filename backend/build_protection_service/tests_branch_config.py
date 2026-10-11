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
        # 删除授权（admin 直接删即可）
        resp = self.client.delete(f"/api/branch-permissions/{perm_id}")
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
            "/api/projects",
            {"name": "WebPortal", "repository_url": "https://git.local/wp.git"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post("/api/projects", {"name": "WebPortal"}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], 40902)
        resp = self.client.get("/api/projects")
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get("/api/users/all")
        self.assertGreaterEqual(len(resp.json()["data"]), 4)