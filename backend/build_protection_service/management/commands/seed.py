"""种子数据：admin 超管 + 演示用户/版本/分支/模板/策略 + 时段抢占演示。"""
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import Branch, SlotBooking, SlotTemplate, Strategy, StrategyTemplate, Version

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

        # ---- 时段抢占演示（守卫锚点：模板名「上午窗口」存在即已种过）----
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
            self._seed_slot_bookings()

        self.stdout.write(self.style.SUCCESS("种子数据创建完成"))

    def _seed_slot_bookings(self):
        """为本月起 3 个工作日各抢占上午/下午窗口各一段，供月历页演示。"""
        version = Version.objects.filter(name="27A").first()
        branch = Branch.objects.filter(version=version, name="master").first()
        user = User.objects.filter(username="pm27a").first()
        morning = SlotTemplate.objects.filter(name="上午窗口").first()
        afternoon = SlotTemplate.objects.filter(name="下午窗口").first()
        if not all([version, branch, user, morning, afternoon]):
            return
        today = timezone.localdate()
        first = today.replace(day=1)
        booked = 0
        d = first
        while d <= today + timedelta(days=7) and booked < 3:
            if d.isoweekday() <= 5 and d > today:
                for tpl, purpose in ((morning, "27A master 每日构建窗口"), (afternoon, "27A 防护网冒烟窗口")):
                    SlotBooking.objects.get_or_create(
                        date=d, template=tpl, status="reserved",
                        defaults={
                            "start_snapshot": tpl.start_time, "end_snapshot": tpl.end_time,
                            "user": user, "purpose": purpose,
                            "version": version, "branch": branch,
                        },
                    )
                booked += 1
            d += timedelta(days=1)
