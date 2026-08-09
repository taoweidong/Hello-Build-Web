from fastapi import APIRouter
from sqlmodel import Session, select

from app.api.deps import AdminUser, CurrentUser, SessionDep
from app.core.config import settings
from app.core.response import ok, raise_param
from app.core.security import get_password_hash
from app.models import (
    AdminOpLog,
    Branch,
    ConfigUpdate,
    SecurityLog,
    Strategy,
    StrategyTemplate,
    TemplateCreate,
    User,
    UserCreate,
    Version,
    VersionCreate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_log(session: Session, user: User, action: str, target_type: str,
               target_id: int | None = None, detail: str | None = None) -> None:
    session.add(AdminOpLog(operator=user.id, action=action, target_type=target_type,
                           target_id=target_id, detail=detail))


# ---- 版本分支 ----


@router.get("/versions")
def list_versions(session: SessionDep, current_user: CurrentUser):
    vs = session.exec(select(Version)).all()
    return ok([{"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id,
                "pm_name": session.get(User, v.pm_user_id).display_name if v.pm_user_id else None,
                "status": v.status,
                "branches": [{"id": b.id, "name": b.name} for b in v.branches]} for v in vs])


@router.post("/versions")
def create_version(req: VersionCreate, session: SessionDep, admin_user: AdminUser):
    if req.pm_user_id and session.exec(
            select(Version).where(Version.pm_user_id == req.pm_user_id)).first():
        raise_param("该 PM 已绑定其他版本")
    v = Version(name=req.name, pm_user_id=req.pm_user_id, status=req.status)
    session.add(v)
    session.commit()
    session.refresh(v)
    _admin_log(session, admin_user, "create_version", "version", v.id, v.name)
    session.commit()
    return ok({"id": v.id})


@router.patch("/versions/{vid}")
def update_version(vid: int, req: VersionCreate, session: SessionDep, admin_user: AdminUser):
    v = session.get(Version, vid)
    if not v:
        raise_param("版本不存在")
    if req.pm_user_id and req.pm_user_id != v.pm_user_id:
        if session.exec(select(Version).where(Version.pm_user_id == req.pm_user_id)).first():
            raise_param("该 PM 已绑定其他版本")
    v.name = req.name
    v.pm_user_id = req.pm_user_id
    v.status = req.status
    _admin_log(session, admin_user, "update_version", "version", vid,
               f"name={req.name} pm={req.pm_user_id}")
    session.commit()
    return ok({"id": vid})


@router.post("/versions/{vid}/branches")
def add_branch(vid: int, branch_name: str, session: SessionDep, admin_user: AdminUser):
    existing = session.exec(
        select(Branch).where(Branch.version_id == vid, Branch.name == branch_name)
    ).first()
    if existing:
        raise_param("该版本已存在此分支")
    b = Branch(version_id=vid, name=branch_name)
    session.add(b)
    session.commit()
    session.refresh(b)
    _admin_log(session, admin_user, "add_branch", "branch", b.id, branch_name)
    session.commit()
    return ok({"id": b.id})


# ---- 用户管理 ----


@router.get("/users")
def list_users(session: SessionDep, admin_user: AdminUser):
    us = session.exec(select(User)).all()
    return ok([{"id": u.id, "username": u.username, "display_name": u.display_name,
                "role": u.role, "is_active": u.is_active} for u in us])


@router.post("/users")
def create_user(req: UserCreate, session: SessionDep, admin_user: AdminUser):
    if session.exec(select(User).where(User.username == req.username)).first():
        raise_param("用户名已存在")
    u = User(username=req.username,
             password_hash=get_password_hash(req.password or "123456"),
             display_name=req.display_name, role=req.role, is_active=req.is_active)
    session.add(u)
    session.commit()
    session.refresh(u)
    _admin_log(session, admin_user, "create_user", "user", u.id, req.username)
    session.commit()
    return ok({"id": u.id})


@router.patch("/users/{uid}")
def update_user(uid: int, req: UserCreate, session: SessionDep, admin_user: AdminUser):
    u = session.get(User, uid)
    if not u:
        raise_param("用户不存在")
    if req.password:
        u.password_hash = get_password_hash(req.password)
    u.display_name = req.display_name
    u.role = req.role
    u.is_active = req.is_active
    _admin_log(session, admin_user, "update_user", "user", uid, req.username)
    session.commit()
    return ok({"id": uid})


# ---- 模板管理 ----


@router.get("/templates")
def list_templates(session: SessionDep, current_user: CurrentUser):
    return ok([{"id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
                "analysis_minutes": t.analysis_minutes, "description": t.description}
               for t in session.exec(select(StrategyTemplate)).all()])


@router.post("/templates")
def create_template(req: TemplateCreate, session: SessionDep, admin_user: AdminUser):
    t = StrategyTemplate(name=req.name, smoke_minutes=req.smoke_minutes,
                         analysis_minutes=req.analysis_minutes,
                         description=req.description, created_by=admin_user.id)
    session.add(t)
    session.commit()
    session.refresh(t)
    _admin_log(session, admin_user, "create_template", "template", t.id, req.name)
    session.commit()
    return ok({"id": t.id})


@router.patch("/templates/{tid}")
def update_template(tid: int, req: TemplateCreate, session: SessionDep, admin_user: AdminUser):
    t = session.get(StrategyTemplate, tid)
    if not t:
        raise_param("模板不存在")
    t.name = req.name
    t.smoke_minutes = req.smoke_minutes
    t.analysis_minutes = req.analysis_minutes
    t.description = req.description
    _admin_log(session, admin_user, "update_template", "template", tid, req.name)
    session.commit()
    return ok({"id": tid})


@router.delete("/templates/{tid}")
def delete_template(tid: int, session: SessionDep, admin_user: AdminUser):
    if session.exec(select(Strategy).where(Strategy.template_id == tid)).first():
        raise_param("该模板已被策略引用，无法删除")
    t = session.get(StrategyTemplate, tid)
    if t:
        session.delete(t)
        session.commit()
    _admin_log(session, admin_user, "delete_template", "template", tid)
    session.commit()
    return ok({"id": tid})


# ---- 关键配置 ----


@router.get("/config")
def get_config(current_user: CurrentUser):
    return ok({"build_minutes": settings.build_minutes,
               "push_minutes": settings.push_minutes,
               "sync_buffer_minutes": settings.sync_buffer_minutes})


@router.put("/config")
def update_config(req: ConfigUpdate, session: SessionDep, admin_user: AdminUser):
    # 运行时调整全局构建参数（进程内生效）
    settings.BUILD_MINUTES = req.build_minutes
    settings.PUSH_MINUTES = req.push_minutes
    settings.SYNC_BUFFER_MINUTES = req.sync_buffer_minutes
    _admin_log(session, admin_user, "update_config", "config", None, str(req))
    session.commit()
    return ok()


# ---- 管理日志（/api/admin/logs/*）----


@router.get("/logs/operations")
def op_logs(session: SessionDep, admin_user: AdminUser):
    logs = session.exec(
        select(AdminOpLog).order_by(AdminOpLog.at.desc()).limit(200)
    ).all()
    return ok([{"id": log.id,
                "operator": session.get(User, log.operator).display_name
                if log.operator and session.get(User, log.operator) else str(log.operator),
                "action": log.action, "target_type": log.target_type,
                "target_id": log.target_id, "detail": log.detail, "at": log.at.isoformat()}
               for log in logs])


@router.get("/logs/security")
def security_logs(session: SessionDep, admin_user: AdminUser):
    logs = session.exec(
        select(SecurityLog).order_by(SecurityLog.at.desc()).limit(200)
    ).all()
    return ok([{"id": log.id, "user_id": log.user_id,
                "username": session.get(User, log.user_id).display_name
                if log.user_id and session.get(User, log.user_id) else None,
                "event": log.event, "ip": log.ip,
                "at": log.at.isoformat()} for log in logs])
