import logging
from ..ports.push import PushPort

logger = logging.getLogger("mock.push")

class MockPushAdapter(PushPort):
    def __init__(self, fail_rate: float = 0.0):
        self.fail_rate = fail_rate
    def push(self, round_id: int, mode: str) -> bool:
        # 本期 mock：打印留痕，可配置失败率模拟失败流转
        import random
        ok = random.random() >= self.fail_rate
        logger.info("[MockPush] round=%s mode=%s result=%s", round_id, mode, "success" if ok else "failed")
        return ok