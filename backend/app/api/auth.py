from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..adapters import LocalAuthAdapter
from ..security import create_token, get_current_user
from ..errors import ok, raise_param, raise_unauthorized
from ..models.user import User
from ..models.audit import SecurityLog
from ..models.version import Version

router = APIRouter()

class LoginReq(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    if not req.username or not req.password:
        raise_param("用户名和密码不能为空")
    user = LocalAuthAdapter(db).authenticate(req.username, req.password)
    if not user:
        db.add(SecurityLog(user_id=None, event="login_failed", ip="mock-ip"))
        db.commit()
        raise_unauthorized("用户名或密码错误")
    token = create_token(user.id)
    version = db.query(Version).filter(Version.pm_user_id == user.id).first()
    db.add(SecurityLog(user_id=user.id, event="login", ip="mock-ip"))
    db.commit()
    return ok({"token": token, "user": {
        "id": user.id, "username": user.username, "display_name": user.display_name,
        "role": user.role, "bound_version_id": version.id if version else None,
        "bound_version_name": version.name if version else None,
    }})

@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.add(SecurityLog(user_id=user.id, event="logout", ip="mock-ip"))
    db.commit()
    return ok()

@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    version = db.query(Version).filter(Version.pm_user_id == user.id).first()
    return ok({"id": user.id, "username": user.username, "display_name": user.display_name,
               "role": user.role, "bound_version_id": version.id if version else None,
               "bound_version_name": version.name if version else None})