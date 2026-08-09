from sqlmodel import Session

from app import crud


def test_authenticate_success(db: Session):
    user = crud.authenticate(session=db, username="admin", password="123456")
    assert user is not None
    assert user.role == "admin"


def test_authenticate_wrong_password(db: Session):
    assert crud.authenticate(session=db, username="admin", password="wrong") is None


def test_authenticate_unknown_user(db: Session):
    # 用户不存在时走 DUMMY_HASH 恒定耗时分支，返回 None
    assert crud.authenticate(session=db, username="no-such-user", password="123456") is None


def test_get_user_by_username(db: Session):
    user = crud.get_user_by_username(session=db, username="pm27a")
    assert user is not None
    assert user.display_name == "27A项目经理"


def test_get_pm_bound_version(db: Session):
    user = crud.get_user_by_username(session=db, username="pm27a")
    assert user is not None
    version = crud.get_pm_bound_version(session=db, user_id=user.id)
    assert version is not None
    assert version.name == "27A"
