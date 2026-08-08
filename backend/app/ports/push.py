from abc import ABC, abstractmethod

class PushPort(ABC):
    @abstractmethod
    def push(self, round_id: int, mode: str) -> bool:
        """推送集成仓库。返回是否成功。"""
        ...