from abc import ABC, abstractmethod

class NotifyPort(ABC):
    @abstractmethod
    def send(self, channel: str, receiver: str, title: str, content: str) -> None:
        ...