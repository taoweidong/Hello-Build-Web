from abc import ABC, abstractmethod

class AuthProviderPort(ABC):
    @abstractmethod
    def authenticate(self, username: str, password: str):
        """返回用户对象或 None"""
        ...