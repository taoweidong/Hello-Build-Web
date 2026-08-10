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

        self.stdout.write(self.style.SUCCESS("种子数据创建完成"))
