from ..ports.auth_provider import AuthProviderPort
from ..security import verify_password
from ..models.user import User

class LocalAuthAdapter(AuthProviderPort):
    def __init__(self, db_session):
        self.db = db_session
    def authenticate(self, username: str, password: str):
        user = self.db.query(User).filter(User.username == username).first()
        if user and verify_password(password, user.password_hash):
            return user
        return None