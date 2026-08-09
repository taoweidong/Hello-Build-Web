from sqlmodel import Session

from app import crud
from app.models import User
from app.ports.auth_provider import AuthProviderPort


class LocalAuthAdapter(AuthProviderPort):
    def __init__(self, session: Session):
        self.session = session

    def authenticate(self, username: str, password: str) -> User | None:
        return crud.authenticate(
            session=self.session, username=username, password=password
        )
