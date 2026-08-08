import logging
from ..ports.scheduler import SchedulerPort
logger = logging.getLogger("mock.scheduler")

class MockSchedulerAdapter(SchedulerPort):
    def start(self): logger.info("[MockScheduler] 调度未启用（本期 mock）")
    def stop(self): pass