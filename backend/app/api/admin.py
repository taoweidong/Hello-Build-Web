from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..security import get_current_user, hash_password
from ..errors import ok, raise_forbidden, raise_param
from ..models.user import User
from ..models.version import Version
from ..models.branch import Branch
from ..models.strategy import StrategyTemplate, Strategy
from ..models.audit import AdminOpLog, SecurityLog
from ..config import settings

router = APIRouter()

def _require_admin(user: User):
    if user.role != "admin":
        raise_forbidden("仅管理员可执行该操作")

def _admin_log(db, user, action, target_type, target_id=None, detail=None):
    db.add(AdminOpLog(operator=user.id, action=action, target_type=target_type,
                      target_id=target_id, detail=detail))

# ---- 版本分支 ----
class VersionReq(BaseModel):
    name: str
    pm_user_id: int | None = None
    status: str = "active"

@router.get("/versions")
def list_versions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    vs = db.query(Version).all()
    return ok([{"id": v.id, "name": v.name, "pm_user_id": v.pm_user_id,
                "pm_name": db.get(User, v.pm_user_id).display_name if v.pm_user_id else None,
                "status": v.status,
                "branches": [{"id": b.id, "name": b.name} for b in v.branches]} for v in vs])

@router.post("/versions")
def create_version(req: VersionReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    if req.pm_user_id and db.query(Version).filter(Version.pm_user_id == req.pm_user_id).first():
        raise_param("该 PM 已绑定其他版本")
    v = Version(name=req.name, pm_user_id=req.pm_user_id, status=req.status)
    db.add(v); db.commit(); db.refresh(v)
    _admin_log(db, user, "create_version", "version", v.id, v.name); db.commit()
    return ok({"id": v.id})

@router.patch("/versions/{vid}")
def update_version(vid: int, req: VersionReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    v = db.get(Version, vid)
    if not v: raise_param("版本不存在")
    if req.pm_user_id and req.pm_user_id != v.pm_user_id:
        if db.query(Version).filter(Version.pm_user_id == req.pm_user_id).first():
            raise_param("该 PM 已绑定其他版本")
    v.name = req.name; v.pm_user_id = req.pm_user_id; v.status = req.status
    _admin_log(db, user, "update_version", "version", vid, f"name={req.name} pm={req.pm_user_id}"); db.commit()
    return ok({"id": vid})

@router.post("/versions/{vid}/branches")
def add_branch(vid: int, branch_name: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    b = Branch(version_id=vid, name=branch_name)
    existing = db.query(Branch).filter(Branch.version_id == vid, Branch.name == branch_name).first()
    if existing: raise_param("该版本已存在此分支")
    db.add(b); db.commit(); db.refresh(b)
    _admin_log(db, user, "add_branch", "branch", b.id, branch_name); db.commit()
    return ok({"id": b.id})

# ---- 用户管理 ----
class UserReq(BaseModel):
    username: str
    password: str = ""
    display_name: str
    role: str
    is_active: bool = True

@router.get("/users")
def list_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    us = db.query(User).all()
    return ok([{"id": u.id, "username": u.username, "display_name": u.display_name,
                "role": u.role, "is_active": u.is_active} for u in us])

@router.post("/users")
def create_user(req: UserReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    if db.query(User).filter(User.username == req.username).first():
        raise_param("用户名已存在")
    u = User(username=req.username, password_hash=hash_password(req.password or "123456"),
             display_name=req.display_name, role=req.role, is_active=req.is_active)
    db.add(u); db.commit(); db.refresh(u)
    _admin_log(db, user, "create_user", "user", u.id, req.username); db.commit()
    return ok({"id": u.id})

@router.patch("/users/{uid}")
def update_user(uid: int, req: UserReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    u = db.get(User, uid)
    if not u: raise_param("用户不存在")
    if req.password:
        u.password_hash = hash_password(req.password)
    u.display_name = req.display_name; u.role = req.role; u.is_active = req.is_active
    _admin_log(db, user, "update_user", "user", uid, req.username); db.commit()
    return ok({"id": uid})

# ---- 模板管理 ----
class TemplateReq(BaseModel):
    name: str
    smoke_minutes: int
    analysis_minutes: int
    description: str = ""

@router.get("/templates")
def list_templates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok([{"id": t.id, "name": t.name, "smoke_minutes": t.smoke_minutes,
                "analysis_minutes": t.analysis_minutes, "description": t.description}
               for t in db.query(StrategyTemplate).all()])

@router.post("/templates")
def create_template(req: TemplateReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    t = StrategyTemplate(name=req.name, smoke_minutes=req.smoke_minutes,
                         analysis_minutes=req.analysis_minutes, description=req.description, created_by=user.id)
    db.add(t); db.commit(); db.refresh(t)
    _admin_log(db, user, "create_template", "template", t.id, req.name); db.commit()
    return ok({"id": t.id})

@router.patch("/templates/{tid}")
def update_template(tid: int, req: TemplateReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    t = db.get(StrategyTemplate, tid)
    if not t: raise_param("模板不存在")
    t.name = req.name; t.smoke_minutes = req.smoke_minutes
    t.analysis_minutes = req.analysis_minutes; t.description = req.description
    _admin_log(db, user, "update_template", "template", tid, req.name); db.commit()
    return ok({"id": tid})

@router.delete("/templates/{tid}")
def delete_template(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    if db.query(Strategy).filter(Strategy.template_id == tid).first():
        raise_param("该模板已被策略引用，无法删除")
    t = db.get(StrategyTemplate, tid)
    db.delete(t); db.commit()
    _admin_log(db, user, "delete_template", "template", tid); db.commit()
    return ok({"id": tid})

# ---- 关键配置 ----
class ConfigReq(BaseModel):
    build_minutes: int
    push_minutes: int
    sync_buffer_minutes: int

@router.get("/config")
def get_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok({"build_minutes": settings.build_minutes, "push_minutes": settings.push_minutes,
               "sync_buffer_minutes": settings.sync_buffer_minutes})

@router.put("/config")
def update_config(req: ConfigReq, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    settings.build_minutes = req.build_minutes
    settings.push_minutes = req.push_minutes
    settings.sync_buffer_minutes = req.sync_buffer_minutes
    _admin_log(db, user, "update_config", "config", None, str(req)); db.commit()
    return ok()

# ---- 管理日志（/api/admin/logs/*）----
@router.get("/logs/operations")
def op_logs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    return ok([{"id": l.id, "operator": db.get(User, l.operator).display_name if l.operator and db.get(User, l.operator) else str(l.operator),
                "action": l.action, "target_type": l.target_type,
                "target_id": l.target_id, "detail": l.detail, "at": l.at.isoformat()}
               for l in db.query(AdminOpLog).order_by(AdminOpLog.at.desc()).limit(200).all()])

@router.get("/logs/security")
def security_logs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    return ok([{"id": l.id, "user_id": l.user_id,
                "username": db.get(User, l.user_id).display_name if l.user_id and db.get(User, l.user_id) else None,
                "event": l.event, "ip": l.ip,
                "at": l.at.isoformat()}
               for l in db.query(SecurityLog).order_by(SecurityLog.at.desc()).limit(200).all()])