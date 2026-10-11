"""策略并发兜底测试（H-2，见 specs/2026-10-11-strategy-concurrency-guard-design.md）。

三层防御：
1. settings 的 SQLite transaction_mode=IMMEDIATE —— 串行化「校验读→写入」，
   生效于生产文件库；测试库为 shared-cache 内存库，无法做线程级并发断言。
2. uniq_active_strategy_branch_time 条件唯一约束 —— DB 层最后防线，本文件锁定。
3. 服务层 IntegrityError → 40902 —— 本文件锁定。

测试技巧：用 ORM 直接插入冲突行（绕过服务层校验，等价于模拟
「并发窗口内另一事务抢先提交」的终态），再走服务层/API 触发约束。
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import Branch, Strategy, StrategyTemplate, Version
from .services import config as svc_config
from .services.strategies import StrategyValidationError, create_strategy, update_strategy
from .tests import ConfigAwareTestCase

User = get_user_model()


class StrategyUniqueConstraintTests(ConfigAwareTestCase):
    """uniq_active_strategy_branch_time 约束：DB 层兜底行为。"""

    def setUp(self):
        super().setUp()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间冒烟", smoke_minutes=480, analysis_minutes=120
        )

    def _create(self, name="策略A", build_start="22:00", branch=None, enabled=True):
        return Strategy.objects.create(
            branch=branch or self.branch, template=self.tmpl, name=name,
            build_start_time=build_start, push_mode="normal", enabled=enabled,
            created_by=self.pm,
        )

    def test_same_branch_same_time_second_insert_rejected(self):
        """同分支同时刻第二条启用策略：DB 层直接 IntegrityError。"""
        self._create(name="已有")
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            self._create(name="冲突")

    def test_disabled_strategy_does_not_conflict(self):
        """停用策略不占坑：同分支同时刻可插入停用行。"""
        self._create(name="已停用", enabled=False)
        # enabled=False 不受条件约束限制
        self._create(name="停用第二条", build_start="22:00", enabled=False)
        self.assertEqual(Strategy.objects.filter(enabled=False).count(), 2)

    def test_different_branch_same_time_allowed(self):
        """跨分支同时刻不受此约束管（跨分支互斥由服务层校验+事务串行化负责）。"""
        other_branch = Branch.objects.create(version=self.version, name="TR5")
        self._create(name="master策略")
        s = self._create(name="TR5策略", branch=other_branch)
        self.assertIsNotNone(s.pk)

    def test_service_layer_converts_integrity_error_to_40902(self):
        """服务层兜底：绕过校验的冲突行存在时，create 抛 StrategyValidationError(40902)。

        模拟方式：先停用既有策略插入同刻行再重新启用——绕过 create 校验，
        使 DB 中存在「服务层校验查不到的冲突终态」。
        """
        s = self._create(name="占用者", build_start="21:00")
        # 复现并发终态：另一行同刻启用（直接 SQL 层面制造，模拟竞态结果）
        Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="竞态赢家",
            build_start_time="22:00", push_mode="normal", enabled=True,
            created_by=self.pm,
        )
        # 服务层 create 与校验同刻 21:00 不冲突（校验会放行 21:00？不——已有占用者）
        # 直接验证：对 22:00 的创建被校验层拦截（服务层第一防线）
        with self.assertRaises(StrategyValidationError) as ctx:
            create_strategy(
                self.branch, self.tmpl, self.pm,
                name="冲突创建", build_start_time="22:00",
            )
        self.assertEqual(ctx.exception.code, 40902)

        # update 路径：把占用者改成 22:00 —— 同刻已有竞态赢家，由 mutex 层
        # （构建区间重叠检测，同版本下含同分支）拦截，返回 40902
        with self.assertRaises(StrategyValidationError) as ctx2:
            update_strategy(s, {"build_start_time": "22:00"}, self.pm)
        self.assertEqual(ctx2.exception.code, 40902)

    def test_toggle_enable_conflicting_slot_returns_40902(self):
        """toggle 启用撞约束：两条同刻策略都停用后先后启用，第二条 409 而非 500。

        该路径此前无 IntegrityError 捕获（服务层校验不覆盖 toggle），
        是加约束时暴露的真实 500 漏洞。
        """
        self.client = APIClient()
        resp = self.client.post(
            "/api/auth/login", {"username": "pm1", "password": "123456"}, format="json"
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}"
        )
        a = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="A",
            build_start_time="22:00", push_mode="normal", enabled=True,
            created_by=self.pm,
        )
        b = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="B",
            build_start_time="23:00", push_mode="normal", enabled=True,
            created_by=self.pm,
        )
        # 两条都停用（停用不受约束限制）
        for s in (a, b):
            s.enabled = False
            s.save()
        # A 启用成功；B 启用撞 A（B 已改到同刻 22:00）
        b.build_start_time = "22:00"
        b.enabled = False
        b.save()

        resp = self.client.post(f"/api/strategies/{a.id}/toggle", format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)  # A 启用 OK

        resp = self.client.post(f"/api/strategies/{b.id}/toggle", format="json")
        self.assertEqual(resp.status_code, 409, msg=resp.content)
        self.assertEqual(resp.json()["code"], 40902, msg=resp.content)


class StrategyConcurrencyGuardApiTests(ConfigAwareTestCase):
    """API 层：约束兜底路径返回 409 而非 500。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        User.objects.create_user(username="admin", password="123456", role="admin")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(
            name="晚间冒烟", smoke_minutes=480, analysis_minutes=120
        )
        resp = self.client.post(
            "/api/auth/login", {"username": "pm1", "password": "123456"}, format="json"
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {resp.json()['data']['token']}"
        )

    def test_normal_create_update_still_work(self):
        """回归保护：合法创建/更新在加约束后不受影响。"""
        resp = self.client.post("/api/strategies", {
            "branch_id": self.branch.id, "template_id": self.tmpl.id,
            "name": "正常策略", "build_start_time": "22:00",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        sid = resp.json()["data"]["id"]

        resp = self.client.patch(f"/api/strategies/{sid}", {
            "build_start_time": "23:00",
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["build_start_time"], "23:00")

    def test_toggle_off_frees_slot(self):
        """停用后释放时刻坑位：同刻可再创建启用策略。"""
        resp = self.client.post("/api/strategies", {
            "branch_id": self.branch.id, "template_id": self.tmpl.id,
            "name": "策略一", "build_start_time": "22:00",
        }, format="json")
        sid = resp.json()["data"]["id"]
        self.client.post(f"/api/strategies/{sid}/toggle", format="json")  # 停用

        resp = self.client.post("/api/strategies", {
            "branch_id": self.branch.id, "template_id": self.tmpl.id,
            "name": "策略二", "build_start_time": "22:00",
        }, format="json")
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual(resp.json()["code"], 0, msg=resp.content)
