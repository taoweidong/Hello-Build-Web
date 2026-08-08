from sqlalchemy.orm import Session
from ..database import SessionLocal, Base, engine
from ..security import hash_password
from ..models.user import User
from ..models.version import Version
from ..models.branch import Branch
from ..models.strategy import StrategyTemplate, Strategy
from ..models.execution import ExecutionRound
from ..models.audit import ExecutionLog
from ..services.timeline import build_timeline
from ..config import settings
from datetime import datetime, date as date_mod, timedelta

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if db.query(User).count() > 0:
        db.close(); print("seed skip (已有数据)")
        return
    # 用户（5 角色）
    pw = hash_password("123456")
    admin = User(username="admin", password_hash=pw, display_name="系统管理员", role="admin")
    pm1 = User(username="pm27a", password_hash=pw, display_name="27A项目经理", role="pm")
    pm2 = User(username="pm27b", password_hash=pw, display_name="27B项目经理", role="pm")
    pm3 = User(username="pm26b", password_hash=pw, display_name="26B项目经理", role="pm")
    builder = User(username="builder", password_hash=pw, display_name="构建人员", role="builder")
    tester = User(username="tester", password_hash=pw, display_name="防护网测试", role="tester")
    integrator = User(username="integrator", password_hash=pw, display_name="集成人员", role="integrator")
    db.add_all([admin, pm1, pm2, pm3, builder, tester, integrator]); db.flush()
    # 版本 + PM 一对一
    v27a = Version(name="27A", pm_user_id=pm1.id, status="active")
    v27b = Version(name="27B", pm_user_id=pm2.id, status="active")
    v26b = Version(name="26B", pm_user_id=pm3.id, status="active")
    db.add_all([v27a, v27b, v26b]); db.flush()
    # 分支
    b27a1 = Branch(version_id=v27a.id, name="master")
    b27a2 = Branch(version_id=v27a.id, name="TR5")
    b27b1 = Branch(version_id=v27b.id, name="master")
    b26b1 = Branch(version_id=v26b.id, name="TR6")
    db.add_all([b27a1, b27a2, b27b1, b26b1]); db.flush()
    # 模板
    t_evening = StrategyTemplate(name="晚间全量冒烟", smoke_minutes=8*60, analysis_minutes=2*60,
                                 description="晚间构建+8H冒烟+2H分析", created_by=admin.id)
    t_noon = StrategyTemplate(name="午间快速冒烟", smoke_minutes=2*60, analysis_minutes=60,
                              description="午间2H冒烟+1H分析", created_by=admin.id)
    t_1630 = StrategyTemplate(name="16_30定点冒烟", smoke_minutes=60, analysis_minutes=30,
                              description="16:30定点1H冒烟+30min分析", created_by=admin.id)
    db.add_all([t_evening, t_noon, t_1630]); db.flush()
    # 策略
    s1 = Strategy(branch_id=b27a1.id, template_id=t_evening.id, name="27A-master晚间全量",
                  build_start_time="22:00", push_mode="sync", enabled=True, created_by=pm1.id)
    s2 = Strategy(branch_id=b27a2.id, template_id=t_noon.id, name="27A-TR5午间快速",
                  build_start_time="12:00", push_mode="normal", enabled=True, created_by=pm1.id)
    s3 = Strategy(branch_id=b27b1.id, template_id=t_1630.id, name="27B-master定点冒烟",
                  build_start_time="16:30", push_mode="normal", enabled=True, created_by=pm2.id)
    s4 = Strategy(branch_id=b26b1.id, template_id=t_evening.id, name="26B-TR6晚间全量",
                  build_start_time="22:00", push_mode="sync", enabled=True, created_by=pm3.id)
    db.add_all([s1, s2, s3, s4]); db.flush()
    # 近 7 天执行轮次
    today = date_mod.today()
    for s in [s1, s2, s3, s4]:
        t = db.get(StrategyTemplate, s.template_id)
        for i in range(7):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            tl = build_timeline(d, s.build_start_time, t.smoke_minutes, t.analysis_minutes,
                                settings.build_minutes, settings.push_minutes,
                                settings.sync_buffer_minutes, s.push_mode)
            passed = i >= 2
            r = ExecutionRound(
                strategy_id=s.id, exec_date=d,
                build_start=tl["build"]["start"], build_end=tl["build"]["end"],
                smoke_start=tl["smoke"]["start"], smoke_end=tl["smoke"]["end"],
                analysis_start=tl["analysis"]["start"], analysis_end=tl["analysis"]["end"],
                conclusion="pass" if passed else "pending",
                push_start=tl["push"]["start"] if tl["push"] else None,
                push_end=tl["push"]["end"] if tl["push"] else None,
                push_status="success" if (s.push_mode == "sync" and passed) else "not_triggered",
            )
            db.add(r)
            db.flush()
            if passed:
                db.add(ExecutionLog(round_id=r.id, stage="conclusion", event="conclusion_submit",
                                    detail="seed pass"))
    db.commit()
    db.close()
    print("seed done")