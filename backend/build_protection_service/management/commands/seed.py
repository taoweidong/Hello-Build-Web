"""种子数据：admin 超管 + 演示用户/版本/分支/模板/策略 + 时段抢占仿真实演示。"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import (
    BorrowFlow,
    Branch,
    SlotBooking,
    SlotTemplate,
    Strategy,
    StrategyTemplate,
    Version,
)

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

        # 守卫锚点：Version 27A 是演示数据的根实体，它存在即代表演示数据已建立。
        # 以根实体而非单一人名为锚，可避免"pm27a 存在但 27A 被删"时跳过补全，
        # 以及"pm27a 被删但 27A 仍在"时对 Version 唯一约束触发 IntegrityError。
        if not Version.objects.filter(name="27A").exists():
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

        # ---- 补充演示策略：多分支/多时段/同步推送，让周视图与日视图时段饱满 ----
        self._seed_extra_strategies()
        # ---- 26B 版本演示（独立 PM 与两条分支）----
        self._seed_version_26b()
        # ---- 27B/26B 演示数据补全：三个版本均有三分支多时段的饱满策略 ----
        self._seed_version_27b_full()
        self._seed_version_26b_full()
        # ---- 借用电子流演示：一条待审批 + 一条已驳回 ----
        self._seed_borrow_flows()

        # ---- 时段抢占演示：模板 + 仿真实抢占记录（幂等）----
        if not SlotTemplate.objects.filter(name="上午窗口").exists():
            SlotTemplate.objects.create(
                name="上午窗口", start_time="08:00", end_time="12:00",
                weekdays="1,2,3,4,5", color="#67c23a", sort_order=1,
            )
            SlotTemplate.objects.create(
                name="下午窗口", start_time="14:00", end_time="18:00",
                weekdays="1,2,3,4,5", color="#409eff", sort_order=2,
            )
            SlotTemplate.objects.create(
                name="夜间回归", start_time="19:00", end_time="22:00",
                color="#e6a23c", sort_order=3,
            )
            SlotTemplate.objects.create(
                name="凌晨维护窗口", start_time="05:00", end_time="07:00",
                color="#909399", sort_order=0,
            )
        self._seed_slot_bookings()

        self.stdout.write(self.style.SUCCESS("种子数据创建完成"))

    def _seed_extra_strategies(self):
        """补充演示策略：多分支/多时段/同步推送（幂等锚点：27A-master-早间回归）。

        同版本构建时段互不重叠（与资源互斥规则一致）；同步推送模式的推送
        固定时段按设计允许与冒烟重叠（推送不参与冲突检测）。
        """
        if Strategy.objects.filter(name="27A-master-早间回归").exists():
            return
        v27a = Version.objects.filter(name="27A").first()
        if v27a is None:
            return
        t_full = StrategyTemplate.objects.filter(name="晚间全量冒烟").first()
        t_quick = StrategyTemplate.objects.filter(name="午间快速冒烟").first()
        if t_full is None or t_quick is None:
            return
        t_sync, _ = StrategyTemplate.objects.get_or_create(
            name="同步推送冒烟",
            defaults={
                "smoke_minutes": 90,
                "analysis_minutes": 30,
                "description": "同步推送模式：推送占用固定时段，与冒烟并行",
            },
        )
        pm27a = User.objects.filter(username="pm27a").first()
        master27a = Branch.objects.filter(version=v27a, name="master").first()
        if master27a is None:
            # 缺失即补建（R4-B15/B4-15，对齐 tr527a/tr627a 守卫）：此前 master
            # 被删时 get_or_create(branch=None) 撞 NOT NULL 约束 IntegrityError，
            # 整个 seed 命令中断
            master27a = Branch.objects.create(version=v27a, name="master")
        tr527a = Branch.objects.filter(version=v27a, name="TR5").first()
        if tr527a is None:
            tr527a = Branch.objects.create(version=v27a, name="TR5")
        tr627a = Branch.objects.filter(version=v27a, name="TR6").first()
        if tr627a is None:
            tr627a = Branch.objects.create(version=v27a, name="TR6", description="TR6 维护分支")

        plan = [
            (master27a, "27A-master-早间回归", t_sync, "06:30", "sync", "08:00"),
            (tr527a, "27A-TR5-午间快速", t_quick, "12:30", "normal", None),
            (tr527a, "27A-TR5-夜间补测", t_quick, "02:00", "normal", None),
            (tr627a, "27A-TR6-午间快速", t_quick, "13:00", "normal", None),
            (tr627a, "27A-TR6-同步推送验证", t_sync, "09:30", "sync", "11:00"),
            (tr627a, "27A-TR6-晚间全量", t_full, "23:00", "normal", None),
        ]
        v27b = Version.objects.filter(name="27B").first()
        master27b = Branch.objects.filter(version=v27b, name="master").first() if v27b else None
        if master27b:
            plan.append((master27b, "27B-master-早间快速", t_quick, "07:00", "normal", None))

        for branch, name, template, build, mode, push in plan:
            Strategy.objects.get_or_create(
                branch=branch,
                name=name,
                defaults={
                    "template": template,
                    "build_start_time": build,
                    "push_mode": mode,
                    "push_start_time": push,
                    "created_by": pm27a,
                },
            )

    def _seed_version_26b(self):
        """26B 版本演示：独立 PM、两条分支、三条策略（锚点 Version 26B）。"""
        if Version.objects.filter(name="26B").exists():
            return
        pm26b, created = User.objects.get_or_create(
            username="pm26b",
            defaults={"role": "pm", "display_name": "26B负责人"},
        )
        if created:
            pm26b.set_password("123456")
            pm26b.save()
        v26b = Version.objects.create(name="26B", pm_user=pm26b, status="active")
        bm = Branch.objects.create(version=v26b, name="master")
        bt = Branch.objects.create(version=v26b, name="TR5")
        t_full = StrategyTemplate.objects.filter(name="晚间全量冒烟").first()
        t_quick = StrategyTemplate.objects.filter(name="午间快速冒烟").first()
        t_sync = StrategyTemplate.objects.filter(name="同步推送冒烟").first()
        if t_full:
            Strategy.objects.create(branch=bm, template=t_full, name="26B-master-晚间全量",
                                    build_start_time="23:30", push_mode="normal", created_by=pm26b)
        if t_sync:
            Strategy.objects.create(branch=bm, template=t_sync, name="26B-master-同步推送",
                                    build_start_time="08:30", push_start_time="10:30",
                                    push_mode="sync", created_by=pm26b)
        if t_quick:
            Strategy.objects.create(branch=bt, template=t_quick, name="26B-TR5-午间快速",
                                    build_start_time="12:45", push_mode="normal", created_by=pm26b)

    def _seed_version_27b_full(self):
        """27B 版本演示补全：三条分支、七条策略，覆盖凌晨/早/午/晚时段。

        幂等：分支按 (version, name) 兜底创建，策略逐条 get_or_create；
        同版本构建时段互不重叠（与资源互斥规则一致）。
        """
        v27b = Version.objects.filter(name="27B").first()
        if v27b is None:
            return
        t_full = StrategyTemplate.objects.filter(name="晚间全量冒烟").first()
        t_quick = StrategyTemplate.objects.filter(name="午间快速冒烟").first()
        t_sync = StrategyTemplate.objects.filter(name="同步推送冒烟").first()
        if t_full is None or t_quick is None:
            return
        pm27b, created = User.objects.get_or_create(
            username="pm27b",
            defaults={"role": "pm", "display_name": "27B负责人"},
        )
        if created:
            pm27b.set_password("123456")
            pm27b.save()

        def branch_of(name, description=None):
            existed = Branch.objects.filter(version=v27b, name=name).first()
            if existed:
                return existed
            return Branch.objects.create(
                version=v27b, name=name, description=description or "演示分支"
            )

        plan = [
            (branch_of("master"), "27B-master-早间快速", t_quick, "07:00", "normal", None),
            (branch_of("master"), "27B-master-午间快速", t_quick, "12:10", "normal", None),
            (branch_of("master"), "27B-master-晚间全量", t_full, "22:30", "normal", None),
            (branch_of("TR5"), "27B-TR5-午间快速", t_quick, "12:40", "normal", None),
            (branch_of("TR5"), "27B-TR5-晚间全量", t_full, "21:30", "normal", None),
            (branch_of("TR6", "TR6 维护分支"), "27B-TR6-同步推送验证", t_sync, "09:40", "sync", "11:20"),
            (branch_of("TR6", "TR6 维护分支"), "27B-TR6-晚间全量", t_full, "23:10", "normal", None),
        ]
        for branch, name, template, build, mode, push in plan:
            if template is None:
                continue
            Strategy.objects.get_or_create(
                branch=branch,
                name=name,
                defaults={
                    "template": template,
                    "build_start_time": build,
                    "push_mode": mode,
                    "push_start_time": push,
                    "created_by": pm27b,
                },
            )

    def _seed_version_26b_full(self):
        """26B 版本演示补全：补 TR6 分支与早/午/晚策略（幂等，逐条 get_or_create）。"""
        v26b = Version.objects.filter(name="26B").first()
        if v26b is None:
            return
        t_full = StrategyTemplate.objects.filter(name="晚间全量冒烟").first()
        t_quick = StrategyTemplate.objects.filter(name="午间快速冒烟").first()
        t_sync = StrategyTemplate.objects.filter(name="同步推送冒烟").first()
        if t_full is None or t_quick is None:
            return
        pm26b = User.objects.filter(username="pm26b").first()

        def branch_of(name, description=None):
            existed = Branch.objects.filter(version=v26b, name=name).first()
            if existed:
                return existed
            return Branch.objects.create(
                version=v26b, name=name, description=description or "演示分支"
            )

        plan = [
            (branch_of("master"), "26B-master-早间回归", t_sync, "06:40", "sync", "08:20"),
            (branch_of("TR5"), "26B-TR5-夜间补测", t_quick, "02:20", "normal", None),
            (branch_of("TR5"), "26B-TR5-晚间全量", t_full, "21:45", "normal", None),
            (branch_of("TR6", "TR6 维护分支"), "26B-TR6-午间快速", t_quick, "13:20", "normal", None),
        ]
        for branch, name, template, build, mode, push in plan:
            if template is None:
                continue
            Strategy.objects.get_or_create(
                branch=branch,
                name=name,
                defaults={
                    "template": template,
                    "build_start_time": build,
                    "push_mode": mode,
                    "push_start_time": push,
                    "created_by": pm26b,
                },
            )

    def _seed_borrow_flows(self):
        """借用电子流演示（幂等，按 借用人+策略+状态 锚点）：
        - pm26b 借用 27A-master-早间回归（同步推送冒烟模板）到 26B/master（15:00），
          待审批（审批人 = 27A 负责人）——时段与 26B 既有安排无冲突，可通过并实际建策略；
        - builder 曾借用 27A-master-早间回归 被驳回（时间与既有安排冲突，样例留痕）。
        """
        from django.utils import timezone as tz

        src_strategy = Strategy.objects.filter(name="27A-master-早间回归").first()
        pm26b = User.objects.filter(username="pm26b").first()
        builder = User.objects.filter(username="builder").first()
        target_tr5_26b = Branch.objects.filter(version__name="26B", name="TR5").first()
        target_master_26b = Branch.objects.filter(version__name="26B", name="master").first()
        reject_src = Strategy.objects.filter(name="27A-master-早间回归").first()
        if not all([src_strategy, pm26b, builder, target_tr5_26b, target_master_26b, reject_src]):
            return
        if not BorrowFlow.objects.filter(
            strategy=src_strategy, borrower=pm26b, status="pending"
        ).exists():
            BorrowFlow.objects.create(
                strategy=src_strategy,
                borrower=pm26b,
                target_branch=target_master_26b,
                new_build_time="15:00",
                reason="26B 午后空闲时段复用 27A 早间回归流程做同步推送演练",
            )
        if not BorrowFlow.objects.filter(
            strategy=reject_src, borrower=builder, status="rejected"
        ).exists():
            BorrowFlow.objects.create(
                strategy=reject_src,
                borrower=builder,
                target_branch=target_master_26b,
                new_build_time="07:00",
                reason="构建机空闲时段练习早间构建",
                status="rejected",
                approver=User.objects.filter(username="pm27a").first(),
                handle_comment="早间时段已被 26B 早间回归占用，且构建机需专职 27A 任务",
                handled_at=tz.now(),
            )

    def _seed_slot_bookings(self):
        """仿真实抢占记录：本月起约两周内多用户多窗口轮转抢占 + 历史释放样例。

        幂等性（R3-B8）：轮转记录以 (date, template) 为锚 get_or_create，status
        只放 defaults 不进 lookup——此前 status 在 lookup 里，首跑末尾释放的历史
        记录第二跑 lookup miss 被重建为 reserved（released+reserved 双记录，
        2026-10-13 评估 B-P2-5）；释放样例仅在已释放记录少于 3 条时，将最早的
        历史 reserved 记录补标为 released。
        """
        templates = {t.name: t for t in SlotTemplate.objects.all()}
        if "上午窗口" not in templates:
            return
        versions = list(Version.objects.filter(name__in=["27A", "27B", "26B"]).order_by("id"))
        if not versions:
            return
        users = {
            u.username: u
            for u in User.objects.filter(
                username__in=["admin", "pm27a", "pm27b", "pm26b", "builder", "tester", "integrator"]
            )
        }
        today = timezone.localdate()
        first = today.replace(day=1)

        # 轮转池：(时段模板, 抢占人, 用途模板)
        rotation = [
            ("上午窗口", "builder", "{v} master 每日构建窗口"),
            ("下午窗口", "tester", "{v} 防护网冒烟执行"),
            ("夜间回归", "pm27a", "{v} TR 分支回归验证"),
            ("上午窗口", "tester", "{v} 冒烟用例补测"),
            ("下午窗口", "builder", "{v} 构建重试与补数"),
            ("夜间回归", "admin", "{v} 全量回归统一调度"),
        ]

        def pick_version(idx):
            return versions[idx % len(versions)]

        def weekday_ok(tpl, d):
            return not tpl.weekdays or str(d.isoweekday()) in tpl.weekdays.split(",")

        i = 0
        d = first
        while d <= today + timedelta(days=13):
            weekday = d.isoweekday()
            if weekday <= 5:
                picks = [rotation[i % 6], rotation[(i + 2) % 6]]
            else:
                picks = [rotation[(i + 2) % 6] if weekday == 6 else rotation[i % 6]]
            for tpl_name, username, purpose_tpl in picks:
                tpl = templates[tpl_name]
                if not tpl.enabled or not weekday_ok(tpl, d):
                    continue
                user = users.get(username)
                version = pick_version(i)
                branch = Branch.objects.filter(version=version).first()
                if not user or not branch:
                    continue
                SlotBooking.objects.get_or_create(
                    date=d,
                    template=tpl,
                    defaults={
                        "start_snapshot": tpl.start_time,
                        "end_snapshot": tpl.end_time,
                        "status": "reserved",
                        "user": user,
                        "purpose": purpose_tpl.format(v=version.name),
                        "version": version,
                        "branch": branch,
                    },
                )
            # 每月固定几天安排凌晨维护（如 3/10/17/24/31 号）
            if d.day % 7 == 3 and "凌晨维护窗口" in templates:
                tpl = templates["凌晨维护窗口"]
                user = users.get("integrator")
                version = pick_version(i)
                branch = Branch.objects.filter(version=version).first()
                if user and branch and weekday_ok(tpl, d):
                    SlotBooking.objects.get_or_create(
                        date=d,
                        template=tpl,
                        defaults={
                            "start_snapshot": tpl.start_time,
                            "end_snapshot": tpl.end_time,
                            "status": "reserved",
                            "user": user,
                            "purpose": f"{version.name} 依赖库升级维护窗口",
                            "version": version,
                            "branch": branch,
                        },
                    )
            i += 1
            d += timedelta(days=1)

        # 历史释放样例：已释放记录不足 3 条时，将最早的历史 reserved 补标 released
        reasons = ["任务提前完成，释放让位晚间全量", "与全量回归冲突，协调让位", "构建计划调整，让位紧急回归"]
        released_count = SlotBooking.objects.filter(status="released").count()
        if released_count < len(reasons):
            past_reserved = SlotBooking.objects.filter(
                status="reserved", date__lt=today
            ).order_by("date", "id")[: len(reasons) - released_count]
            for idx, b in enumerate(past_reserved):
                b.status = "released"
                b.released_at = timezone.now()
                b.release_reason = reasons[(released_count + idx) % len(reasons)]
                b.save(update_fields=["status", "released_at", "release_reason"])
