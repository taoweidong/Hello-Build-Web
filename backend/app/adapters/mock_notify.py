import logging
from ..ports.notify import NotifyPort
logger = logging.getLogger("mock.notify")

class MockNotifyAdapter(NotifyPort):
    def send(self, channel: str, receiver: str, title: str, content: str) -> None:
        logger.info("[MockNotify] channel=%s to=%s title=%s content=%s", channel, receiver, title, content)