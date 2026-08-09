import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models import (
    AdminOpLog,
    Branch,
    ExecutionLog,
    ExecutionRound,
    Strategy,
    StrategyChangeLog,
    StrategyTemplate,
    User,
    Version,
)
from app.services.timeline import build_timeline

logger = logging.getLogger(__name__)


# 用户不存在时用于恒定耗时比对的假哈希（防时序攻击，对齐模板；为随机密码的真实 bcrypt 哈希）
DUMMY_HASH = "$2b$12$9zdSwifaR6O/iTogYDpb.uw4vxoUZsdi1olrEqkyQv6H6mH3TXbF6"


def get_user_by_username(*, session: Session, username: str) -> User | None:
    statement = select(User).where(User.username == username)
    return session.exec(statement).first()


def create_user(
    *,
    session: Session,
    username: str,
    password: str,
    display_name: str,
    role: str,
    is_active: bool = True,
) -> User:
    db_obj = User(
        username=username,
        password_hash=get_password_hash(password),
        display_name=display_name,
        role=role,
        is_active=is_active,
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def authenticate(*, session: Session, username: str, password: str) -> User | None:
    db_user = get_user_by_username(session=session, username=username)
    if not db_user:
        # 用户不存在时也执行一次校验，保证响应耗时相近（防时序攻击）
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, db_user.password_hash):
        return None
    return db_user


def get_pm_bound_version(*, session: Session, user_id: int) -> Version | None:
    """PM 绑定的版本（一对一）"""
    return session.exec(select(Version).where(Version.pm_user_id == user_id)).first()


# ------------------------------- 种子数据 -------------------------------


def _seed_core(session: Session) -> None:
    """主数据：用户 / 版本 / 分支 / 模板 / 策略 / 近 7 天执行轮次"""
    pw = get_password_hash("123456")
    # 首位管理员（对齐模板 FIRST_SUPERUSER，由配置控制）
    admin = User(username=settings.FIRST_SUPERUSER,
                 password_hash=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
                 display_name="系统管理员", role="admin")
    pm1 = User(username="pm27a", password_hash=pw, display_name="27A项目经理", role="pm")
    pm2 = User(username="pm27b", password_hash=pw, display_name="27B项目经理", role="pm")
    pm3 = User(username="pm26b", password_hash=pw, display_name="26B项目经理", role="pm")
    builder = User(username="builder", password_hash=pw, display_name="构建人员", role="builder")
    tester = User(username="tester", password_hash=pw, display_name="防护网测试", role="tester")
    integrator = User(username="integrator", password_hash=pw, display_name="集成人员", role="integrator")
    session.add_all([admin, pm1, pm2, pm3, builder, tester, integrator])
    session.flush()
    # 版本 + PM 一对一
    v27a = Version(name="27A", pm_user_id=pm1.id, status="active")
    v27b = Version(name="27B", pm_user_id=pm2.id, status="active")
    v26b = Version(name="26B", pm_user_id=pm3.id, status="active")
    session.add_all([v27a, v27b, v26b])
    session.flush()
    # 分支
    b27a1 = Branch(version_id=v27a.id, name="master")
    b27a2 = Branch(version_id=v27a.id, name="TR5")
    b27b1 = Branch(version_id=v27b.id, name="master")
    b26b1 = Branch(version_id=v26b.id, name="TR6")
    session.add_all([b27a1, b27a2, b27b1, b26b1])
    session.flush()
    # 模板
    t_evening = StrategyTemplate(
        name="晚间全量冒烟", smoke_minutes=8 * 60, analysis_minutes=2 * 60,
        description="晚间构建+8H冒烟+2H分析", created_by=admin.id)
    t_noon = StrategyTemplate(
        name="午间快速冒烟", smoke_minutes=2 * 60, analysis_minutes=60,
        description="午间2H冒烟+1H分析", created_by=admin.id)
    t_1630 = StrategyTemplate(
        name="16_30定点冒烟", smoke_minutes=60, analysis_minutes=30,
        description="16:30定点1H冒烟+30min分析", created_by=admin.id)
    session.add_all([t_evening, t_noon, t_1630])
    session.flush()
    # 策略
    s1 = Strategy(branch_id=b27a1.id, template_id=t_evening.id, name="27A-master晚间全量",
                  build_start_time="22:00", push_mode="sync", enabled=True, created_by=pm1.id)
    s2 = Strategy(branch_id=b27a2.id, template_id=t_noon.id, name="27A-TR5午间快速",
                  build_start_time="12:00", push_mode="normal", enabled=True, created_by=pm1.id)
    s3 = Strategy(branch_id=b27b1.id, template_id=t_1630.id, name="27B-master定点冒烟",
                  build_start_time="16:30", push_mode="normal", enabled=True, created_by=pm2.id)
    s4 = Strategy(branch_id=b26b1.id, template_id=t_evening.id, name="26B-TR6晚间全量",
                  build_start_time="22:00", push_mode="sync", enabled=True, created_by=pm3.id)
    session.add_all([s1, s2, s3, s4])
    session.flush()
    # 近 7 天执行轮次
    today = datetime.now(UTC).replace(tzinfo=None).date()
    for s in [s1, s2, s3, s4]:
        t = session.get(StrategyTemplate, s.template_id)
        assert t is not None
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
            session.add(r)
            session.flush()
            if passed:
                session.add(ExecutionLog(round_id=r.id, stage="conclusion",
                                         event="conclusion_submit", detail="seed pass"))


def _seed_audit_logs(session: Session) -> None:
    """审计日志：策略变更日志 + 管理操作日志（幂等补全，仅当表为空时插入）"""
    today = datetime.now(UTC).replace(tzinfo=None).date()
    if session.exec(select(StrategyChangeLog)).first() is None:
        changes = [
            (1, 2, "build_start_time", "21:00", "22:00", 3),
            (1, 2, "push_mode", "normal", "sync", 2),
            (2, 2, "name", "27A-TR5上午构建", "27A-TR5午间快速", 4),
            (3, 3, "enabled", "False", "True", 5),
            (3, 3, "build_start_time", "17:00", "16:30", 1),
            (4, 4, "push_mode", "normal", "sync", 2),
        ]
        for sid, op, field, old, new, days in changes:
            session.add(StrategyChangeLog(
                strategy_id=sid, operator=op, field=field, old_value=old, new_value=new,
                at=datetime.combine(today - timedelta(days=days), datetime.min.time())))
    if session.exec(select(AdminOpLog)).first() is None:
        ops = [
            ("create_version", "version", 1, "27A", 6),
            ("create_user", "user", 5, "builder", 6),
            ("create_template", "template", 1, "晚间全量冒烟", 5),
            ("add_branch", "branch", 4, "TR6", 5),
            ("update_config", "config", None, "build_minutes=30 push_minutes=20 sync_buffer_minutes=20", 3),
            ("create_version", "version", 3, "26B", 2),
        ]
        for action, target_type, target_id, detail, days in ops:
            session.add(AdminOpLog(
                operator=1, action=action, target_type=target_type,
                target_id=target_id, detail=detail,
                at=datetime.combine(today - timedelta(days=days), datetime.min.time())))


def seed_demo_data(*, session: Session) -> None:
    """业务演示种子数据（幂等：用户表为空时才写入主数据）"""
    if session.exec(select(User)).first() is None:
        _seed_core(session)
        logger.info("seed core done")
    _seed_audit_logs(session)
    session.commit()
